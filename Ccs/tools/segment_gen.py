#!/usr/bin/env python3
"""
Utility functions for generating SREC file and segmented image from IASW binary
"""

import crcmod
import io
import os
import struct
import sys


SEG_HEADER_FMT = '>III'
SEG_HEADER_LEN = struct.calcsize(SEG_HEADER_FMT)
SEG_SPARE_LEN = 2
SEG_CRC_LEN = 2

SKIP_BYTES = 65536
SREC_MAX_BYTES_PER_LINE = 250
SREC_BYTES_PER_LINE = 32

MAX_PKT_LEN = 504
S13_OVERHEAD_BYTES = 24

START_ADDR = 0x60040000  # start address of IASW in RAM
MEM_ADDR = 0x40000000  # address where the data is uploaded to
SEGID = 0x200B0101  # ID for data segments, see DBS UM
SEGMENT_LEN = 464  # segment size, including header and CRC

puscrc = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')


def source_to_srec(binary, outfile, memaddr, header=None, bytes_per_line=SREC_BYTES_PER_LINE, skip_bytes=SKIP_BYTES):
    """

    :param binary:
    :param outfile:
    :param memaddr:
    :param header:
    :param bytes_per_line:
    :param skip_bytes:
    :return:
    """

    if bytes_per_line > SREC_MAX_BYTES_PER_LINE:
        raise ValueError("Maximum number of bytes per line is {}!".format(SREC_MAX_BYTES_PER_LINE))

    if isinstance(binary, str):
        binary = open(binary, 'rb').read()

    if not isinstance(binary, bytes):
        raise TypeError

    data = binary[skip_bytes:]

    if header is None:
        fname = outfile.split('/')[-1][-60:]
        header = 'S0{:02X}0000{:}'.format(len(fname.encode('ascii')) + 3, fname.encode('ascii').ljust(24).hex().upper())
        header += '{:02X}'.format(srec_chksum(header[2:]))

    datalen = len(data)
    data = io.BytesIO(data)

    sreclist = []
    terminator = 'S705{:08X}'.format(memaddr)
    terminator += '{:02X}'.format(srec_chksum(terminator[2:]))

    while data.tell() < datalen:
        chunk = data.read(bytes_per_line)
        chunklen = len(chunk)
        line = '{:02X}{:08X}{:}'.format(chunklen + 5, memaddr, chunk.hex().upper())
        # add chksum according to SREC standard
        line = 'S3' + line + '{:02X}'.format(srec_chksum(line))
        sreclist.append(line)
        memaddr += chunklen

    with open(outfile, 'w') as fd:
        fd.write(header + '\n')
        fd.write('\n'.join(sreclist) + '\n')
        fd.write(terminator)

    print('SREC written to file: "{}", skipped first {} bytes.'.format(os.path.abspath(outfile), skip_bytes))

def srec_chksum(x: str):
    """
    SREC line checksum
    """
    return sum(bytes.fromhex(x)) & 0xff ^ 0xff


def srec_to_segments(fname, memaddr, segid, linesperpack=50, max_pkt_size=MAX_PKT_LEN):

    # payload_len = max_pkt_size - S13_OVERHEAD_BYTES - SEG_CRC_LEN - SEG_SPARE_LEN - SEG_HEADER_LEN
    payload_len = SEGMENT_LEN - SEG_CRC_LEN - SEG_SPARE_LEN - SEG_HEADER_LEN

    segments = []

    f = open(fname, 'r').readlines()[1:]
    lines = [p[12:-3] for p in f]
    startaddr = int(f[0][4:12], 16)

    upload_bytes = b''
    linecount = 0
    bcnt = 0
    pcnt = 0

    while linecount < len(f) - 1:

        linepacklist = []
        for n in range(linesperpack):
            if linecount >= (len(lines) - 1):
                break

            if (len(''.join(linepacklist)) + len(lines[linecount])) // 2 > payload_len:  # ensure max_pkt_size
                break

            linepacklist.append(lines[linecount])
            linelength = len(lines[linecount]) // 2
            if int(f[linecount + 1][4:12], 16) != (int(f[linecount][4:12], 16) + linelength):
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)
                break
            else:
                linecount += 1
                newstartaddr = int(f[linecount][4:12], 16)

        linepack = bytes.fromhex(''.join(linepacklist))
        dlen = len(linepack)
        bcnt += dlen
        # segment header, see IWF DBS HW SW ICD
        data = struct.pack(SEG_HEADER_FMT, segid, startaddr, dlen // 4) + linepack + bytes(SEG_SPARE_LEN)
        data = data + puscrc(data).to_bytes(SEG_CRC_LEN, 'big')

        segments.append((memaddr, data))

        # collect all uploaded segments for CRC at the end
        upload_bytes += data
        pcnt += 1

        startaddr = newstartaddr
        memaddr += len(data)

    endsegment = bytes(SEG_HEADER_LEN)
    segments.append((memaddr, endsegment))

    # return total length of uploaded data (without termination segment) and CRC over entire image, including segment headers
    return segments, len(upload_bytes), puscrc(upload_bytes)


def segment_data(data, segid, addr, seglen=SEGMENT_LEN):
    """
    Split data into segments (as defined in IWF DPU HW SW ICD) with segment header and CRC.
    Segment data has to be two-word aligned.

    :param data:
    :param segid:
    :param addr:
    :param seglen:
    :return: list of segments
    """

    if isinstance(data, str):
        data = open(data, 'rb').read()

    if not isinstance(data, bytes):
        raise TypeError

    datalen = len(data)
    if datalen % 4:
        raise ValueError('Data length is not two-word aligned')
    data = io.BytesIO(data)

    segments = []
    segaddr = addr

    while data.tell() < datalen:
        chunk = data.read(seglen - (SEG_HEADER_LEN + SEG_SPARE_LEN + SEG_CRC_LEN))
        chunklen = len(chunk)

        if chunklen % 4:
            raise ValueError('Segment data length is not two-word aligned')

        sdata = struct.pack(SEG_HEADER_FMT, segid, segaddr, chunklen // 4) + chunk + bytes(SEG_SPARE_LEN)
        sdata += puscrc(sdata).to_bytes(SEG_CRC_LEN, 'big')
        segments.append(sdata)
        segaddr += chunklen

    upload_bytes = b''.join(segments)
    # add 12 byte termination segment
    segments.append(bytes(SEG_HEADER_LEN))

    return segments, len(upload_bytes), puscrc(upload_bytes)


def run(binary):

    # generate SREC file
    srec_fn = binary + ".srec"
    source_to_srec(binary, srec_fn, START_ADDR, skip_bytes=SKIP_BYTES)

    # generate segments from SREC file
    segments, ul_size, ul_crc = srec_to_segments(srec_fn, MEM_ADDR, SEGID)

    segdir = os.path.abspath(binary) + "_segments"
    os.makedirs(segdir, exist_ok=True)

    # write segments and meta data
    meta = ["# IDX\tADDR\tCRC"]
    for i, seg in enumerate(segments, 1):
        with open(os.path.join(segdir, 'seg_{:04d}.bin'.format(i)), 'wb') as fd:
            fd.write(seg[1])

        meta.append('{:04d}\t{:08X}\t{:04X}'.format(i, seg[0], int.from_bytes(seg[1][-2:], 'big')))

    with open(os.path.join(segdir, 'segments.dat'), 'w') as fd:
        fd.write('\n'.join(meta))

    print('Segments written to: "{}"'.format(segdir))
    print('{} bytes total, CRC = {:04X}'.format(ul_size, ul_crc))


if __name__ == "__main__":

    binary = sys.argv[1]
    run(binary)
