#!/usr/bin/env python

"""
Convert unprocessed CE raw data to FITS files. Product type is determined (guessed) based on CE size.
"""

import datetime
import os
import sys

import numpy as np
from astropy.io import fits

# expected CE sizes in bytes
SIZE_FF = 4511 * 4608 * 2
SIZE_FT = 639 * 384 * 2  # 1 node
SIZE_ED = 64  # 1 event

FILE_PREFIX = 'SMILE_SXI_L1'

ED_BIN_DTYPE = np.dtype(
    [('TIME', '>f8'), ('CCDFRAME', '>i4'), ('CCDNR', 'u1'), ('RAWX', '>i2'), ('RAWY', '>i2'), ('AMP', 'u1'),
     ('PHAS', '>i2', (25,))])


def convert_ce(cefile, fitsfile=None):

    cedata = open(cefile, 'rb').read()

    # guess product based on CE size
    if len(cedata) == SIZE_FF:
        mode, hdl = mk_ff(cedata)
    elif len(cedata) // SIZE_FT in [1, 2, 4]:
        mode, hdl = mk_ft(cedata)
    elif len(cedata) % SIZE_ED == 0:
        mode, hdl = mk_ed(cedata)
    else:
        print('Cannot determine product type for CE of length {}, aborting.'.format(len(cedata)))
        sys.exit()

    if fitsfile is None:
        outdir = os.path.dirname(os.path.abspath(cefile))
        fitsfile = os.path.join(outdir, '{}_{}_{}.fits'.format(FILE_PREFIX, mode, _mk_ts()))
    else:
        fitsfile = fitsfile.replace('.fits', '_{}.fits'.format(mode))

    hdl.writeto(fitsfile, overwrite=True)


def mk_ff(data):
    # create uint16 array from raw data and reshape
    arr = np.frombuffer(data, dtype='>H').reshape(4511, -1)
    fnode = arr[:, ::2]
    enode = arr[:, 1::2][:, ::-1]
    ff = np.concatenate((fnode, enode), axis=1)

    # write array to FITS file
    hdl = _mk_hdl('FF')
    hdl.append(fits.ImageHDU(data=ff, name='FULLFRAME'))

    return 'FF', hdl


def mk_ft(data):
    arr = np.frombuffer(data, dtype='>H').reshape(-1, 639, 384)

    hdl = _mk_hdl('FT')
    for n in range(arr.shape[0]):
        hdl.append(fits.ImageHDU(data=arr[n, :, :], name='FT_CCD_NODE_{}'.format(n)))

    # arrange all nodes to full CCD view
    if arr.shape[0] == 4:
        n00 = arr[0, :, :]  # CCD2 F-side
        n01 = arr[1, :, ::-1]  # CCD2 E-side
        n10 = arr[2, ::-1, :]  # CCD4 F-side
        n11 = arr[3, ::-1, ::-1]  # CCD4 E-side

        n0 = np.concatenate((n00, n01), 1)
        n1 = np.concatenate((n10, n11), 1)

        nn = np.concatenate((n0, n1), 0)  # [::-1, :]

        hdl.append(fits.ImageHDU(data=nn, name='FULLCCD'))

    return 'FT', hdl


def mk_ed(data):
    # reshape into array of evt packets
    arr = np.frombuffer(data, dtype='>H').reshape(-1, 32)

    hdl = _mk_hdl('FT')
    ts = int(hdl['PRIMARY'].header['OBS_ID'])
    bindata = np.array([_mk_bin_entry(evt, ts) for evt in arr], dtype=ED_BIN_DTYPE)

    # also add an HDU with event map
    nodes = np.zeros((2, 2, 639, 384))
    nodes[:] = np.nan

    for _, _, ccd, col, row, node, fx in bindata:
        try:
            nodes[ccd, node, row - 2:row + 3, col - 2:col + 3] = fx.reshape(5, 5)
        except:
            print(col, row, 'FAILED')

    n00 = nodes[0, 0, :, :]  # CCD2 F-side
    n01 = nodes[0, 1, :, :][:, ::-1]  # CCD2 E-side
    n10 = nodes[1, 0, :, :][::-1, :]  # CCD4 F-side
    n11 = nodes[1, 1, :, :][::-1, ::-1]  # CCD4 E-side

    n0 = np.concatenate((n00, n01), 1)
    n1 = np.concatenate((n10, n11), 1)

    ed_img = np.concatenate((n0, n1), 0)  # [::-1, :]

    hdl.append(fits.ImageHDU(data=ed_img, name='EVTMAP'))

    hdl.append(fits.BinTableHDU(data=bindata, name='EVENTS'))

    return 'ED', hdl


def _mk_bin_entry(data, timestamp):
    spw, dlen, dtyp, fc, sc, col, row, *evts = data

    ccdnr = (dtyp >> 4) & 1
    node = (dtyp >> 5) & 0b11

    return timestamp, fc, ccdnr, col, row, node, evts


def _mk_hdl(dmode):
    hdl = fits.HDUList()
    phdu = fits.PrimaryHDU()

    phdu.header['TELESCOP'] = 'SMILE'
    phdu.header['INSTRUME'] = 'SXI'
    phdu.header['DATAMODE'] = dmode
    phdu.header['OBS_ID'] = datetime.datetime.utcnow().strftime('%s')

    hdl.append(phdu)

    return hdl


def _mk_ts(cefile=None):

    if cefile is None:
        return datetime.datetime.utcnow().strftime('%j_%H%M%S%f')[:-3]
    else:
        return cefile.split('_')[-1]


if __name__ == "__main__":

    if len(sys.argv) > 2:
        cefile, fitsfile = sys.argv[1:3]
    else:
        cefile = sys.argv[1]
        fitsfile = None

    convert_ce(cefile, fitsfile=fitsfile)
