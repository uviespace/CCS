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
from numpy.lib import recfunctions as rf

# expected CE sizes in bytes
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
NODE_NUM = 1  # total number of nodes TODO: set to 4 for proper data

SCI_PRODUCTS = {0: 'ED', 1: 'UNKNOWN', 2: 'FT', 3: 'UV', 4: 'FF', 5: 'ED_WP'}

FILE_PREFIX = 'SMILE_SXI_L1'

ED_BIN_DTYPE = np.dtype(
    [('TIME', '>f8'), ('CCDFRAME', '>u4'), ('CCDNR', 'u1'), ('RAWX', '>u2'), ('RAWY', '>u2'), ('AMP', 'u1'),
     ('PHAS', '>u2', (25,))])

ED_PKT_DTYPE = np.dtype([('spw', '>u2'), ('dlen', '>u2'), ('mode', '>u1'), ('dtyp', '>u1'), ('fc', '>u2'), ('sc', '>u2'),
                         ('col', '>u2'), ('row', '>u2'), ('evts', '>u2', (25,))])

ID_ED = 1
ID_WP = 3

WP_PER_FRAME = 1


def convert_ce(cefile, fitsfile=None, guess=False):

    cedata = open(cefile, 'rb').read()

    # if guess:
    #     # guess product based on CE size
    #     if len(cedata) == SIZE_FF:
    #         mode, hdl = mk_ff(cedata)
    #     elif len(cedata) // SIZE_FT in [1, 2, 4]:
    #         mode, hdl = mk_ft(cedata)
    #     elif len(cedata) % SIZE_ED == 0:
    #         mode, hdl = mk_ed(cedata)
    #     else:
    #         print('Cannot determine product type for CE of length {}, aborting.'.format(len(cedata)))
    #         sys.exit()
    #
    #     obsid = 0

    # else:
    try:
        ce = CompressionEntity(cedata)
        prod = ce.header.items.product
        # cekey = ce.header.items.ce_key

        # obsid = ce.header.items.obsid

        assert ce.meta_frame.shape[0] == ce.header.items.sdp_group_members

        if fitsfile is not None:
            asfits = True
        else:
            asfits = False

        if SCI_PRODUCTS.get(prod) == 'FF':
            mode, *hdl = mk_ff(ce, asfits=asfits)
        elif SCI_PRODUCTS.get(prod) == 'FT':
            mode, *hdl = mk_ft(ce, asfits=asfits)
        elif SCI_PRODUCTS.get(prod) == 'UV':
            mode, *hdl = mk_uv(ce, asfits=asfits)
        elif SCI_PRODUCTS.get(prod) in ['ED', 'ED_WP']:
            mode, *hdl = mk_ed(ce, asfits=asfits)
        else:
            print('Unknown product in CE ({}), aborting.'.format(prod))
            sys.exit()

        if fitsfile is not None:
            hdl[0].writeto(fitsfile, overwrite=True)

    except Exception as err:
        print(err)
        sys.exit()

    # if fitsfile is None:
    #     outdir = os.path.dirname(os.path.abspath(cefile))
    #     fitsfile = os.path.join(outdir, '{}_{}_{:010d}_{}.fits'.format(FILE_PREFIX, mode, obsid, _mk_ts()))

    return ce.header, hdl


def mk_ff(data, asfits=True):
    # create uint16 array from raw data and reshape
    arr = np.frombuffer(data.scidata, dtype='>H').reshape(NROWS_FF, NCOLS_FF)
    fnode = arr[:, ::2]
    enode = arr[:, 1::2][:, ::-1]
    ff = np.concatenate((fnode, enode), axis=1)

    if asfits:
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

    else:
        return 'FF', ff, data.meta_group, data.meta_frame


def mk_ft(data, asfits=True):

    # check if stacking ('2') was applied and use correct pixel bit size
    if '2' in hex(data.header.items.ce_key):
        pixbits = '>I'
    else:
        pixbits = '>H'

    arr = np.frombuffer(data.scidata, dtype=pixbits).reshape(-1, NODE_NUM, NROWS_FT, NCOLS_FT)

    if asfits:
        hdl = _mk_hdl('FT', data.header)
        n_nodes = arr.shape[0]

        if n_nodes % NODE_NUM:
            print('Total number of nodes ({}) is not a multiple of 4!'.format(n_nodes))

            for n in range(arr.shape[0]):
                node = fits.ImageHDU(data=arr[n, :, :], name='FT_CCD_NODE_{}'.format(n))
                node.add_checksum()
                hdl.append(node)
        else:
            for n in range(NODE_NUM):
                node = fits.ImageHDU(data=arr[n::NODE_NUM, :, :], name='FT_CCD_NODE_{}'.format(n))
                node.add_checksum()
                hdl.append(node)

        # arrange all nodes to full CCD
        if n_nodes % 4 == 0:

            nn = _assemble_ft_frames_to_fp_view(arr)

            hdl.append(fits.ImageHDU(data=nn, name='FULLARRAY'))

        group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
        frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

        # checksums
        group_table.add_checksum()
        frame_table.add_checksum()
        hdl.append(group_table)
        hdl.append(frame_table)

        return 'FT', hdl

    return 'FT', arr, data.meta_group, data.meta_frame


def mk_uv(data, asfits=True):

    # check if stacking ('2') was applied and use correct pixel bit size
    if '2' in hex(data.header.items.ce_key):
        pixbits = '>I'
    else:
        pixbits = '>H'

    arr = np.frombuffer(data.scidata, dtype=pixbits).reshape(-1, NODE_NUM, NROWS_UV, NCOLS_UV)

    if asfits:
        hdl = _mk_hdl('UV', data.header)
        n_nodes = arr.shape[0]

        if n_nodes % NODE_NUM:
            for n in range(arr.shape[0]):
                node = fits.ImageHDU(data=arr[n, :, :], name='UV_CCD_NODE_{}'.format(n))
                node.add_checksum()
                hdl.append(node)
        else:
            for n in range(NODE_NUM):
                node = fits.ImageHDU(data=arr[n::NODE_NUM, :, :], name='UV_CCD_NODE_{}'.format(n))
                node.add_checksum()
                hdl.append(node)

        # arrange all nodes to full CCD
        if n_nodes % 4 == 0:

            nn = _assemble_ft_frames_to_fp_view(arr)

            hdl.append(fits.ImageHDU(data=nn, name='FULLARRAY'))

        group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
        frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

        # checksums
        group_table.add_checksum()
        frame_table.add_checksum()
        hdl.append(group_table)
        hdl.append(frame_table)

        return 'UV', hdl

    return 'UV', arr, data.meta_group, data.meta_frame


def mk_ed(data, asfits=True, edmap=False):
    # reshape into array of evt packets
    # arr = np.frombuffer(data.scidata, dtype='>H').reshape(-1, SIZE_ED // 2)

    arr = np.frombuffer(data.scidata, dtype=ED_PKT_DTYPE)

    frmevtcnt = data.meta_frame['LastFrameEvtCount']

    if data.meta_frame['LastFrameEvtCount'].sum() != data.meta_group['NOfEvtDet'][0]:
        print('Inconsistent CE frame count: LastFrameEvtCount_sum = {}, NOfEvtDet = {}'.format(frmevtcnt.sum(), data.meta_group['NOfEvtDet'][0]))

    hdl = _mk_hdl('ED', data.header)
    ts = data.meta_frame['sdpProductStarttimeCrs'] + data.meta_frame['sdpProductStarttimeFine'] / 1e6
    # ts_ext = ts.repeat(frmevtcnt)

    # bindata = np.array([_mk_bin_entry(evt, t, wpm_raise=True) for evt, t in zip(arr, ts_ext)], dtype=ED_BIN_DTYPE)
    bindata, wpmdata = _mk_bin_arrays(arr, ts, frmevtcnt)

    if asfits:
        if edmap:
            # also add an HDU with event map
            nodes = np.zeros((2, 2, NROWS_FT, NCOLS_FT))

            for _, _, ccd, col, row, node, fx in bindata:
                try:
                    nodes[ccd, node, row - 2:row + 3, col - 2:col + 3] += fx.reshape(5, 5)
                except:
                    print(col, row, 'FAILED')

            # nodes[nodes == 0] = np.nan
            ed_img = _assemble_ft_frames_to_fp_view(nodes)

            hdl.append(fits.ImageHDU(data=ed_img, name='EVTMAP'))

        evts = fits.BinTableHDU(data=bindata, name='EVENTS')
        evts.add_checksum()
        hdl.append(evts)

        group_table = fits.BinTableHDU(data=data.meta_group, name='GROUP_HK')
        frame_table = fits.BinTableHDU(data=data.meta_frame, name='FRAME_HK')

        if len(wpmdata) > 0:
            wpm_table = fits.BinTableHDU(data=wpmdata, name='WNDRNG_PXL')
            wpm_table.add_checksum()
            hdl.append(wpm_table)

        # checksums
        group_table.add_checksum()
        frame_table.add_checksum()
        hdl.append(group_table)
        hdl.append(frame_table)

        return 'ED', hdl

    return 'ED', (bindata, wpmdata), data.meta_group, data.meta_frame


def _mk_bin_entry(data, timestamp, wpm_raise=False):
    spw, dlen, dtyp, fc, sc, col, row, *evts = data

    ccdnr = (dtyp >> 4) & 1
    node = (dtyp >> 5) & 0b11

    if wpm_raise:
        if (dtyp & 0b11) == 3:
            raise ValueError('WPM detected')

    return timestamp, fc, ccdnr, col, row, node, evts


def _fmt_bin_data(data, ts):

    ccdnr = (data['dtyp'] >> 4) & 1
    node = (data['dtyp'] >> 5) & 0b11

    return np.array(list(zip(ts, data['fc'], ccdnr, data['col'], data['row'], node, data['evts'])), dtype=ED_BIN_DTYPE)


def _mk_bin_arrays(pkts, ts, frmevtcnt):

    evt_pkts = pkts[pkts['dtyp'] & 0b11 == ID_ED]
    wp_pkts = pkts[pkts['dtyp'] & 0b11 == ID_WP]

    # if (len(wp_pkts) != 0) and (len(wp_pkts) != WP_PER_FRAME * len(frmevtcnt)):
    if (len(wp_pkts) != 0) and (len(wp_pkts) % WP_PER_FRAME):
        print('Unexpected number of WP packets ({})'.format(len(wp_pkts)))

    evts = _fmt_bin_data(evt_pkts, np.repeat(ts, frmevtcnt))
    wpm = _fmt_bin_data(wp_pkts, np.repeat(ts, WP_PER_FRAME))

    return evts, wpm


def _assemble_ft_frames_to_fp_view(arrnd):

    # interpreting TVAC results, CCD0/2 is at the "top" and CCD1/4 at the "bottom" in the detector plane layout

    # FT
    # according to MSSL-IF-122 the nodes arrive in the following order: E2, F2, E4, F4
    if arrnd.ndim == 3:
        n00 = arrnd[1::NODE_NUM, ::-1, ::-1]  # CCD2 F-side (upper right in FP view)
        n01 = arrnd[0::NODE_NUM, ::-1, :]  # CCD2 E-side (upper left in FP view)
        n10 = arrnd[3::NODE_NUM, :, :]  # CCD4 F-side (lower left in FP view)
        n11 = arrnd[2::NODE_NUM, :, ::-1]  # CCD4 E-side (lower right in FP view)

    # ED
    elif arrnd.ndim == 4:
        n00 = arrnd[0, 0, :, :][::-1, ::-1]  # CCD2 F-side
        n01 = arrnd[0, 1, :, :][::-1, :]  # CCD2 E-side
        n10 = arrnd[1, 0, :, :]  # CCD4 F-side
        n11 = arrnd[1, 1, :, :][:, ::-1]  # CCD4 E-side

    else:
        return

    # in case multiple frames are in the FT/UV CE
    if n00.ndim == 3:
        ax = 1
    else:
        ax = 0

    n0 = np.concatenate((n01, n00), axis=1 + ax)  # CCD2
    n1 = np.concatenate((n10, n11), axis=1 + ax)  # CCD4

    return np.concatenate((n1, n0), axis=0 + ax)


def _mk_hdl(dmode, dhead):
    hdl = fits.HDUList()
    phdu = fits.PrimaryHDU()

    phdu.header['TELESCOP'] = 'SMILE'
    phdu.header['INSTRUME'] = 'SXI'
    phdu.header['DATAMODE'] = dmode
    phdu.header['OBS_ID'] = dhead.items.obsid
    phdu.header['PRODTYP'] = 'single CE'
    phdu.header['SDPGRPN'] = (dhead.items.sdp_group_members, 'number of SDP group members')

    phdu.header['SOFTVER'] = dhead.items.version_number
    phdu.header['BUILD'] = dhead.items.build_number
    phdu.header['SDPVER'] = dhead.items.sdp_version
    phdu.header['CREATOR'] = "SXITLM2FITS"
    phdu.header['TLM2FITS'] = "0.2b"
    phdu.header['DATE'] = datetime.datetime.isoformat(datetime.datetime.now(datetime.UTC))

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

    def info(self):
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

    # cefile="/home/marko/space/smile/tvac/oct2024/20241002_180038/proc/0000000000_00001_213125754215040_00593_SXI-SCI-FT.ce"
    # fitsfile="/home/marko/space/smile/tvac/oct2024/20241002_180038/proc/0000000000_00001_213125754215040_00593_SXI-SCI-FT.ce.fits"
    # convert_ce(cefile, fitsfile=fitsfile)
    #
    # sys.exit()

    if len(sys.argv) > 2:
        cefile, fitsfile = sys.argv[1:3]
    else:
        cefile = sys.argv[1]
        fitsfile = None

    convert_ce(cefile, fitsfile=fitsfile)
