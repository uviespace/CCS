#!/usr/bin/env python3

"""
Extract telemetry data from NCTRS files as provided by MOC

Author: Marko Mecina
"""

import io
import struct
import sys
import crcmod

CRCFUNC = crcmod.predefined.mkCrcFun('crc-ccitt-false')
trashbytes = 0


def nctrs_to_tmpool(infiles, outfile='merged_NCTRS.tmpool', merge=False, sort=True):
    pckts_list = []
    for nctrs in infiles:
        pckts = convert_nctrs(nctrs)
        if merge:
            pckts_list += pckts
        else:
            with open(nctrs + '.tmpool', 'wb') as fd:
                fd.write(b''.join(pckts))

    if merge:
        if sort:
            pckts_list.sort(key=lambda x: get_cuc(x))
        with open(outfile, 'wb') as fd:
            fd.write(b''.join(pckts_list))

        print('>> TM packets written to {} <<'.format(outfile))


def convert_nctrs(infile):
    fd = open(infile, 'rb')
    flen = len(fd.read())
    fd.seek(0)
    nctrs_list = []

    # read NCTRS entities from bin file
    while fd.tell() < flen:
        pos = fd.tell()
        dlen = fd.read(4)
        while len(dlen) < 4:
            dlen += fd.read(1)
        fd.seek(pos)
        nctrs = fd.read(int.from_bytes(dlen[:4], 'big'))
        nctrs_list.append(nctrs)

    fd.close()
    # print(len(nctrs_list),len(nctrs_list[0]),[len(n) for n in nctrs_list][-3:])

    # remove NCTRS header to get transfer frames
    tframes = [tf[20:] for tf in nctrs_list]

    # read and merge TF data fields
    tfdf = []
    first = True
    for tf in tframes:
        # get first header pointer
        fhp = int.from_bytes(tf[4:6], 'big') & 2047

        # get remainder in front of location pointed to by FHP
        # TF header size is 10 bytes
        rmnd = tf[10:10 + fhp]

        # get application data starting at FHP
        # operational control field is present, error control field is not
        data = tf[10 + fhp:-4]

        # skip remainder if first TF in NCTRS file
        if not first:
            tfdf.append(rmnd)
        tfdf.append(data)

        first = False

    pktstream = b''.join(tfdf)
    pckts = clear_idle_pckts(pktstream)
    print('{} packets extracted from {}'.format(len(pckts), infile))

    return pckts


# get rid of idle packets and optionally restrict to packets that pass CRC
def clear_idle_pckts(pcktstream):
    global trashbytes
    data = io.BytesIO(pcktstream)
    pckts = []

    pkt = True
    while pkt is not None:
        cpos = data.tell()
        pkt = read_pus(data)

        if pkt is None:
            break

        if check_crc is True and (crc_check(pkt) is True or (int.from_bytes(pkt[:2], 'big') & 0x7ff not in (321,322,323,324,332,961,972))):
            data.seek(cpos + 1)
            trashbytes += 1
            continue

        if int.from_bytes(pkt[:2], 'big') & 2047 != 2047:
            pckts.append(pkt)

    return pckts


def crc_check(pkt):
    return bool(CRCFUNC(pkt))


def read_pus(data):
    pos = data.tell()
    pus_size = data.read(6)

    if pus_size == b'':
        return

    while len(pus_size) < 6:
        add = data.read(1)
        if add == b'':
            return
        pus_size += add

    data.seek(pos)

    # packet size is header size (6) + pus size field + 1
    pckt_size = int.from_bytes(pus_size[4:6], 'big') + 7

    return data.read(pckt_size)


def get_cuc(tm):
    try:
        ct, ft = struct.unpack('>IH', tm[10:16])
        ft >>= 1
        return ct + ft / 2 ** 15
    except IndexError:
        return -1.


if __name__ == '__main__':
    nctrs_files = sys.argv[1:]
    if nctrs_files.count('--merge'):
        merge = True
        nctrs_files.remove('--merge')
    else:
        merge = False

    if nctrs_files.count('--sort'):
        sort = True
        nctrs_files.remove('--sort')
    else:
        sort = False

    if nctrs_files.count('--nocrc'):
        check_crc = False
        nctrs_files.remove('--nocrc')
    else:
        check_crc = True

    nctrs_to_tmpool(nctrs_files, merge=merge, sort=sort)
    if trashbytes != 0:
        print('( {} inconsistent bytes were found and discarded! )'.format(trashbytes))

