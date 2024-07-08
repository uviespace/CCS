#!/usr/bin/env python3

"""
Convert unprocessed CE raw data to FITS files. Product type is determined (guessed) based on CE size.
"""

import ctypes
import datetime
import os
import sys
# import struct

import numpy as np
from astropy.io import fits

# expected CE sizes in bytes TODO: 24x24 binned FT
NROWS_FF = 4511
NCOLS_FF = 4608
NROWS_FT = 639
NCOLS_FT = 384
NROWS_UV = 165  # 160
NCOLS_UV = 96  # 99
SIZE_FF = NROWS_FF * NCOLS_FF * 2
SIZE_FT = NROWS_FT * NCOLS_FT * 2  # 1 node
SIZE_UV = NROWS_UV * NCOLS_UV * 2  # 1 node
SIZE_ED = 64  # 1 event

SCI_PRODUCTS = {0: 'ED', 1: 'UNKNOWN', 2: 'FT', 3: 'UV', 4: 'FF'}

FILE_PREFIX = 'SMILE_SXI_L1'

ED_BIN_DTYPE = np.dtype(
    [('TIME', '>f8'), ('CCDFRAME', '>u4'), ('CCDNR', 'u1'), ('RAWX', '>u2'), ('RAWY', '>u2'), ('AMP', 'u1'),
     ('PHAS', '>u2', (25,))])


def convert_ce(cefile, fitsfile=None, guess=False):

    cedata = open(cefile, 'rb').read()

    if guess:
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
    else:
        try:
            ce = CompressionEntity(cedata)
            prod = ce.header.items.product

            if SCI_PRODUCTS.get(prod) == 'FF':
                mode, hdl = mk_ff(ce)
            elif SCI_PRODUCTS.get(prod) == 'FT':
                mode, hdl = mk_ft(ce)
            elif SCI_PRODUCTS.get(prod) == 'UV':
                mode, hdl = mk_uv(ce)
            elif SCI_PRODUCTS.get(prod) == 'ED':
                mode, hdl = mk_ed(ce)
            else:
                print('Unknown product in CE ({}), aborting.'.format(prod))
                sys.exit()

        except Exception as err:
            print(err)
            sys.exit()

    if fitsfile is None:
        outdir = os.path.dirname(os.path.abspath(cefile))
        fitsfile = os.path.join(outdir, '{}_{}_{}.fits'.format(FILE_PREFIX, mode, _mk_ts()))

    hdl.writeto(fitsfile, overwrite=True)


def mk_ff(data):
    # create uint16 array from raw data and reshape
    arr = np.frombuffer(data.scidata, dtype='>H').reshape(NROWS_FF, NCOLS_FF)
    fnode = arr[:, ::2]
    enode = arr[:, 1::2][:, ::-1]
    ff = np.concatenate((fnode, enode), axis=1)

    # write array to FITS file
    hdl = _mk_hdl('FF', data.header)
    fullframe = fits.ImageHDU(data=ff, name='FULLFRAME')
    fullframe.add_checksum()
    hdl.append(fullframe)

    group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
    frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

    # checksums
    group_table.add_checksum()
    frame_table.add_checksum()
    hdl.append(group_table)
    hdl.append(frame_table)

    return 'FF', hdl


def mk_ft(data):
    arr = np.frombuffer(data.scidata, dtype='>H').reshape(-1, NROWS_FT, NCOLS_FT)

    hdl = _mk_hdl('FT', data.header)
    for n in range(arr.shape[0]):
        node = fits.ImageHDU(data=arr[n, :, :], name='FT_CCD_NODE_{}'.format(n))
        node.add_checksum()
        hdl.append(node)

    # arrange all nodes to full CCD
    if arr.shape[0] == 4:

        nn = _assemble_ft_frames_to_fp_view(arr)

        hdl.append(fits.ImageHDU(data=nn, name='FULLCCD'))

    group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
    frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

    # checksums
    group_table.add_checksum()
    frame_table.add_checksum()
    hdl.append(group_table)
    hdl.append(frame_table)

    return 'FT', hdl


def mk_uv(data):
    arr = np.frombuffer(data.scidata, dtype='>H').reshape(-1, NROWS_UV, NCOLS_UV)

    hdl = _mk_hdl('UV', data.header)
    for n in range(arr.shape[0]):
        node = fits.ImageHDU(data=arr[n, :, :], name='UV_CCD_NODE_{}'.format(n))
        node.add_checksum()
        hdl.append(node)

    # arrange all nodes to full CCD
    if arr.shape[0] == 4:

        nn = _assemble_ft_frames_to_fp_view(arr)

        hdl.append(fits.ImageHDU(data=nn, name='FULLCCD'))

    group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
    frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

    # checksums
    group_table.add_checksum()
    frame_table.add_checksum()
    hdl.append(group_table)
    hdl.append(frame_table)

    return 'UV', hdl


def mk_ed(data):
    # reshape into array of evt packets
    arr = np.frombuffer(data.scidata, dtype='>H').reshape(-1, SIZE_ED // 2)

    hdl = _mk_hdl('ED', data.header)
    # ts = int(hdl['PRIMARY'].header['OBS_ID'])
    ts = data.meta_frame['sdpProductStarttimeCrs'] + data.meta_frame['sdpProductStarttimeFine'] / 1e6
    bindata = np.array([_mk_bin_entry(evt, ts) for evt in arr], dtype=ED_BIN_DTYPE)

    # also add an HDU with event map
    nodes = np.zeros((2, 2, NROWS_FT, NCOLS_FT))

    for _, _, ccd, col, row, node, fx in bindata:
        try:
            nodes[ccd, node, row - 2:row + 3, col - 2:col + 3] += fx.reshape(5, 5)
        except:
            print(col, row, 'FAILED')

    nodes[nodes == 0] = np.nan

    ed_img = _assemble_ft_frames_to_fp_view(nodes)

    hdl.append(fits.ImageHDU(data=ed_img, name='EVTMAP'))

    evts = fits.BinTableHDU(data=bindata, name='EVENTS')
    evts.add_checksum()
    hdl.append(evts)

    group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
    frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

    # checksums
    group_table.add_checksum()
    frame_table.add_checksum()
    hdl.append(group_table)
    hdl.append(frame_table)

    return 'ED', hdl


def _mk_bin_entry(data, timestamp):
    spw, dlen, dtyp, fc, sc, col, row, *evts = data

    ccdnr = (dtyp >> 4) & 1
    node = (dtyp >> 5) & 0b11

    return timestamp, fc, ccdnr, col, row, node, evts


def _assemble_ft_frames_to_fp_view(arrnd):

    # interpreting TVAC results, CCD0/2 is at the "top" and CCD1/4 at the "bottom" in the detector plane layout

    # FT
    # according to MSSL-IF-122 the nodes arrive in the following order: E2, F2, E4, F4
    if arrnd.ndim == 3:
        n00 = arrnd[1, ::-1, ::-1]  # CCD2 F-side (upper right in FP view)
        n01 = arrnd[0, ::-1, :]  # CCD2 E-side (upper left in FP view)
        n10 = arrnd[3, :, :]  # CCD4 F-side (lower left in FP view)
        n11 = arrnd[2, :, ::-1]  # CCD4 E-side (lower right in FP view)
    # ED
    elif arrnd.ndim == 4:
        n00 = arrnd[0, 0, :, :][::-1, ::-1]  # CCD2 F-side
        n01 = arrnd[0, 1, :, :][::-1, :]  # CCD2 E-side
        n10 = arrnd[1, 0, :, :]  # CCD4 F-side
        n11 = arrnd[1, 1, :, :][:, ::-1]  # CCD4 E-side
    else:
        return

    n0 = np.concatenate((n01, n00), axis=1)  # CCD2
    n1 = np.concatenate((n10, n11), axis=1)  # CCD4

    return np.concatenate((n1, n0), axis=0)


def _mk_hdl(dmode, dhead):
    hdl = fits.HDUList()
    phdu = fits.PrimaryHDU()

    phdu.header['TELESCOP'] = 'SMILE'
    phdu.header['INSTRUME'] = 'SXI'
    phdu.header['DATAMODE'] = dmode
    phdu.header['OBS_ID'] = dhead.items.obsid

    phdu.header['SOFTVER'] = dhead.items.version_number
    phdu.header['BUILD'] = dhead.items.build_number
    phdu.header['SDPVER'] = dhead.items.sdp_version
    phdu.header['CREATOR'] = "SXITLM2FITS"
    phdu.header['TLM2FITS'] = "0.2b"
    phdu.header['DATE'] = datetime.datetime.isoformat(datetime.datetime.utcnow())

    hdl.append(phdu)

    return hdl


def _mk_ts(cefile=None):

    if cefile is None:
        return datetime.datetime.utcnow().strftime('%j_%H%M%S%f')[:-3]
    else:
        return cefile.split('_')[-1]


FMT_LUT = {'UINT8': '>u1',
           'B': '>u1',
           'uint1': '>u1',
           'uint2': '>u1',
           'uint3': '>u1',
           'uint4': '>u1',
           'uint5': '>u1',
           'uint6': '>u1',
           'uint7': '>u1',
           'UINT16': '>u2',
           'H': '>u2',
           'UINT32': '>u4',
           'I': '>u4',
           'INT8': '>i1',
           'b': '>i1',
           'INT16': '>i2',
           'h': '>i2',
           'INT32': '>i4',
           'i': '>i4',
           'FLOAT': '>f8',
           'f': '>f8',
           'd': '>f8',
           'CUC918': '>f8',
           'S10': '|S10'}

STRUCT_CE_HEADER = [
    ("version_number", ctypes.c_uint16),
    ("build_number", ctypes.c_uint16),
    ("sdp_version", ctypes.c_uint16),
    ("coarse", ctypes.c_uint32),
    ("fine", ctypes.c_uint16),
    ("obsid", ctypes.c_uint32),
    ("ce_counter", ctypes.c_uint16),
    ("sdp_group_members", ctypes.c_uint16),
    ("ce_size", ctypes.c_uint32),
    ("ce_key", ctypes.c_uint32),
    ("product", ctypes.c_uint8),
    ("ce_integrity", ctypes.c_uint8),
    ("group_meta_size", ctypes.c_uint16),
    ("frame_meta_size", ctypes.c_uint16),
    ("compressed_meta_size", ctypes.c_uint16),
    ("data_size", ctypes.c_uint32),
    ("compressed_data_size", ctypes.c_uint32)
]

META_GROUP_ITEMS = [('FRMccd2EPixThreshold', 'H'),
                    ('FRMccd2FPixThreshold', 'H'),
                    ('FRMccd2Readout', 'B'),
                    ('FRMccd4EPixThreshold', 'H'),
                    ('FRMccd4FPixThreshold', 'H'),
                    ('FRMccd4Readout', 'B'),
                    ('FRMccdMode2Config', 'B'),
                    ('FRMccdModeConfig', 'B'),
                    ('FRMchargeInjectionEn', 'B'),
                    ('FRMchargeInjectionGap', 'H'),
                    ('FRMchargeInjectionWidth', 'H'),
                    ('FRMcorrectionBypass', 'B'),
                    ('FRMcorrectionType', 'B'),
                    ('FRMeduWanderingMaskEn', 'B'),
                    ('FRMeventDetection', 'B'),
                    ('FRMimgClkDir', 'B'),
                    ('FRMintSyncPeriod', 'I'),
                    ('FRMpixOffset', 'B'),
                    ('FRMreadoutNodeSel', 'B'),
                    ('sdpDiffAxis', 'B'),
                    ('sdpDiffMethod', 'B'),
                    ('EvtBadPixelCount', 'I'),
                    ('EvtFilterCount1', 'I'),
                    ('EvtFilterCount2', 'I'),
                    ('EvtFilterCount3', 'I'),
                    ('EvtFilterN', 'H'),
                    ('EvtFilterThr1', 'H'),
                    ('EvtFilterThr2', 'H'),
                    ('EvtFilterThr3', 'H'),
                    ('FeeBadPixelFilter', 'B'),
                    ('FeeEventFilterEnable', 'B'),
                    ('sdpAriPar1', 'I'),
                    ('sdpAriPar2', 'I'),
                    ('sdpBinX', 'H'),
                    ('sdpBinY', 'H'),
                    ('sdpCropB', 'H'),
                    ('sdpCropT', 'H'),
                    ('sdpCropX', 'H'),
                    ('sdpCropY', 'H'),
                    ('sdpDecimN', 'I'),
                    ('sdpEvtCeil', 'H'),
                    ('sdpEvtCtr', 'I'),
                    ('sdpEvtFloor', 'H'),
                    ('sdpGolombPar1', 'I'),
                    ('sdpGolombPar2', 'I'),
                    ('sdpOffsetSignal', 'h'),
                    ('NOfEvtDet', 'H')]

META_FRAME_ITEMS = [('AdcTempCcd', 'H'),
                    ('FrameDiscardCount', 'I'),
                    ('LastFrameEvtCount', 'I'),
                    ('FRMHK1v2dMon', 'H'),
                    ('FRMHK2v5aMon', 'H'),
                    ('FRMHK2v5dMon', 'H'),
                    ('FRMHK3v3bMon', 'H'),
                    ('FRMHK3v3dMon', 'H'),
                    ('FRMHK5vbNegMon', 'H'),
                    ('FRMHK5vbPosMon', 'H'),
                    ('FRMHK5vrefMon', 'H'),
                    ('FRMHKboardId', 'B'),
                    ('FRMHKccd2EPixFullSun', 'H'),
                    ('FRMHKccd2FPixFullSun', 'H'),
                    ('FRMHKccd2TsA', 'H'),
                    ('FRMHKccd2VddMon', 'H'),
                    ('FRMHKccd2VgdMon', 'H'),
                    ('FRMHKccd2VodMonE', 'H'),
                    ('FRMHKccd2VodMonF', 'H'),
                    ('FRMHKccd2VogMon', 'H'),
                    ('FRMHKccd2VrdMonE', 'H'),
                    ('FRMHKccd2VrdMonF', 'H'),
                    ('FRMHKccd4EPixFullSun', 'H'),
                    ('FRMHKccd4FPixFullSun', 'H'),
                    ('FRMHKccd4TsB', 'H'),
                    ('FRMHKccd4VddMon', 'H'),
                    ('FRMHKccd4VgdMon', 'H'),
                    ('FRMHKccd4VodMonE', 'H'),
                    ('FRMHKccd4VodMonF', 'H'),
                    ('FRMHKccd4VogMon', 'H'),
                    ('FRMHKccd4VrdMonE', 'H'),
                    ('FRMHKccd4VrdMonF', 'H'),
                    ('FRMHKcmicCorr', 'H'),
                    ('FRMHKerrorFlags', 'I'),
                    ('FRMHKfpgaMajorVersion', 'B'),
                    ('FRMHKfpgaMinorVersion', 'B'),
                    ('FRMHKfpgaOpMode', 'B'),
                    ('FRMHKframeCounter', 'H'),
                    ('FRMHKigHiMon', 'H'),
                    ('FRMHKprt1', 'H'),
                    ('FRMHKprt2', 'H'),
                    ('FRMHKprt3', 'H'),
                    ('FRMHKprt4', 'H'),
                    ('FRMHKprt5', 'H'),
                    ('FRMHKspwStatus', 'I'),
                    ('FRMHKvan1PosRaw', 'H'),
                    ('FRMHKvan2PosRaw', 'H'),
                    ('FRMHKvan3NegMon', 'H'),
                    ('FRMHKvccd', 'H'),
                    ('FRMHKvccdPosRaw', 'H'),
                    ('FRMHKvclkPosRaw', 'H'),
                    ('FRMHKvdigRaw', 'H'),
                    ('FRMHKviclk', 'H'),
                    ('FRMHKvrclkMon', 'H'),
                    ('sdpProductStarttimeCrs', 'I'),
                    ('sdpProductStarttimeFine', 'I'),
                    ('RseShutSts', 'B')]

# _meta_group_fmt = '>' + ''.join([x[1] for x in META_GROUP_ITEMS])
# _meta_frame_fmt = '>' + ''.join([x[1] for x in META_FRAME_ITEMS])
_meta_group_fmt = [(x[0], FMT_LUT[x[1]]) for x in META_GROUP_ITEMS]
_meta_frame_fmt = [(x[0], FMT_LUT[x[1]]) for x in META_FRAME_ITEMS]


class CeHeaderStruct(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype) for label, ctype in STRUCT_CE_HEADER]

    def __init__(self):
        super(CeHeaderStruct).__init__()

    @property
    def timestamp(self):
        return self.coarse + (self.fine << 8) / 1e6


CE_HEADER_LEN = ctypes.sizeof(CeHeaderStruct)


class CeHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('items', CeHeaderStruct),
        ('bin', ctypes.c_ubyte * CE_HEADER_LEN)
    ]

    def __str__(self):
        return '\n'.join(['{}: {}'.format(n, getattr(self.items, n)) for n, _ in self.items._fields_])

    def show(self):
        print(self.__str__())


class CompressionEntity:

    def __init__(self, data):

        assert isinstance(data, bytes)
        assert len(data) >= CE_HEADER_LEN

        self.header = CeHeader()
        self.header.bin[:] = data[:CE_HEADER_LEN]

        self.cedata = data[CE_HEADER_LEN:]

    @property
    def scidata(self):
        data = self.cedata[self.header.items.compressed_meta_size:]
        if len(data) != self.header.items.compressed_data_size:
            print('Inconsistent data length')
        return data

    @property
    def meta_group(self):
        data = self.cedata[:self.header.items.group_meta_size]
        # vals = struct.unpack(_meta_group_fmt, data)
        return np.frombuffer(data, _meta_group_fmt)

    @property
    def meta_frame(self):
        data = self.cedata[self.header.items.group_meta_size:self.header.items.compressed_meta_size]
        return np.frombuffer(data, _meta_frame_fmt)


if __name__ == "__main__":

    if len(sys.argv) > 2:
        cefile, fitsfile = sys.argv[1:3]
    else:
        cefile = sys.argv[1]
        fitsfile = None

    convert_ce(cefile, fitsfile=fitsfile)
