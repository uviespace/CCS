#!/usr/bin/env python3
"""
Add offset to PUS packet timestamps for data stored in a binary file (SMILE)
"""

import os


def run(fn, toff=None, outfile=None):
    with open(fn, 'rb') as fd:
        pkts = cfl.extract_pus(fd)

    # calculate offset from file's mtime and last packet timestamp if toff is not given
    if toff is None:
        print('Calculating time offset from file modification time and last TM packet timestamp...')
        idx = -1
        pkt_time = None
        while abs(idx) <= len(pkts):
            if not (pkts[idx][0] >> 4) & 1:
                pkt_time = int.from_bytes(pkts[idx][10:14], 'big')
                break

        if pkt_time is None:
            print('No TM packet found for reference')
            return

        toff = int(os.path.getmtime(fn)) - pkt_time

    print('TOFF =', toff)

    if outfile is None:
        outfile = fn + '.tmod'

    with open(outfile, 'wb') as fd:
        for pkt in pkts:
            # check if pkt is TC
            if (pkt[0] >> 4) & 1:
                fd.write(pkt)
            else:
                fd.write(mod_time(pkt, toff))

    print('Modified packets written to {}.'.format(os.path.abspath(outfile)))


def mod_time(pkt, ofs):
    nw = pkt[:10] + (int.from_bytes(pkt[10:14], 'big') + ofs).to_bytes(4, 'big') + pkt[14:-2]
    return nw + cfl.crc(nw).to_bytes(2, 'big')


filename = '301123_LFT_cold_phase2_minus117_tcs'
offset = 1234567
# run(filename, toff=offset)


if __name__ == '__main__':

    import sys
    import confignator

    cfg = confignator.get_config()
    sys.path.append(cfg['paths']['ccs'])

    import ccs_function_lib as cfl

    filename = sys.argv[1]
    if len(sys.argv) > 2:
        offset = int(sys.argv[2])
    else:
        offset = None

    run(filename, toff=offset)
