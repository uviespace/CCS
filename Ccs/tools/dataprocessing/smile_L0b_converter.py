#!/usr/bin/env python3
"""
Process SMILE SXI L0b product to L0d
"""

import datetime
import logging
import os
import subprocess
import sys

from astropy.io import fits
import numpy as np

from hk_processing import proc_hk
from packetstruct import ST_OFF, SST_OFF

import crcmod

puscrc = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')

# logging.setLevel(logging.INFO)

DP_OFFSET = 345544320

PROC_ST = [1, 3, 5, 20]  # PUS service types to be processed for ENG product

SDUID = 1

SDUID_OFF = 18
SDUID_LEN = 1
SDU_SEQ_NMB_OFF = 19
SDU_SEQ_NMB_LEN = 2
SDU_DATALEN_OFF = 21
SDU_DATALEN_LEN = 2

SDU_DATA_OFF = 23

TIME_OFF = 10
TIME_C_LEN = 4
TIME_F_LEN = 3

CHECK_SEQ = True
seqcnt = None

trashcnt = 0

CE_EXEC = "./smile_raw_ce_converter.py"

PRODUCT_IDS = {0: 'SXI-SCI-ED',
               2: 'SXI-SCI-FT',
               4: 'SXI-SCI-FF',
               # 3: 'SXI-SCI-ST',
               # 4: 'SXI-SCI-PT',
               3: 'SXI-SCI-UV'}

SCI_PRODUCTS = {0: 'ED', 1: 'UNKNOWN', 2: 'FT', 3: 'UV', 4: 'FF'}

MODES = tuple(PRODUCT_IDS.values())

FT_NODES = ('FT_CCD_NODE_0', 'FT_CCD_NODE_1', 'FT_CCD_NODE_2', 'FT_CCD_NODE_3')

ED_BIN_DTYPE = np.dtype(
    [('TIME', '>f8'), ('CCDFRAME', '>u4'), ('CCDNR', 'u1'), ('RAWX', '>u2'), ('RAWY', '>u2'), ('AMP', 'u1'),
     ('PHAS', '>u2', (25,))])

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

GROUP_TABLE_STRUCT = [('groupIdx', 'UINT16'),
                      ('timetag', 'FLOAT'),
                      ('obsid', 'UINT32'),
                      ('ceCounter', 'UINT16'),
                      ('sdpGroupMembers', 'UINT32'),
                      ('ceSize', 'UINT32'),
                      ('ceKey', 'S10'),
                      ('product', 'S10'),
                      ('ceIntegrity', 'UINT8'),
                      ('groupMetaSize', 'UINT32'),
                      ('frameMetaSize', 'UINT32'),
                      ('compressedMetaSize', 'UINT32'),
                      ('dataSize', 'UINT32'),
                      ('compressedDataSize', 'UINT32'),
                      ('FRMccd2EPixThreshold', 'H'),
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

FRAME_TABLE_STRUCT = [('AdcTempCcd', 'H'),
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
                    ('RseShutSts', 'B'),
                    ('groupIdx', 'H')]

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

HEADER_KEYS_GROUP = ['TIMETAG',
                     'OBSID',
                     'CE_COUNTER',
                     'SDP_GROUP_MEMBERS',
                     'CE_SIZE',
                     'CE_KEY',
                     'PRODUCT',
                     'CE_INTEGRITY',
                     'GROUP_META_SIZE',
                     'FRAME_META_SIZE',
                     'COMPRESSED_META_SIZE',
                     'DATA_SIZE',
                     'COMPRESSED_DATA_SIZE']


# data format utility functions
def fmt_func_float(uint_arr):
    return uint_arr.astype(np.uint32).view(np.float32)


def fmt_func_signed_int16(uint_arr):
    return uint_arr.astype(np.uint16).view(np.int16)


def read_pus(data):
    """
    Read single PUS packet from buffer

    @param data: buffer
    @return: single PUS packet as byte string or *None*
    """
    pkt = b''
    while len(pkt) < 6:
        pkt += data.read(6 - len(pkt))
        if len(pkt) == 0:
            return

    pktlen = int.from_bytes(pkt[4:6], 'big') + 7
    while len(pkt) < pktlen:
        add = data.read(pktlen - len(pkt))

        if add == b'':
            return

        pkt += add

    return pkt


def extract_pus_crc(data):
    """
    :param data:
    :return:
    """
    global trashcnt

    while True:
        pos = data.tell()
        pkt = read_pus(data)

        if pkt is not None:
            if not crc_check(pkt):
                return pkt
            else:
                logging.warning('invalid CRC encountered at bytepos {}'.format(pos))
                data.seek(pos + 1)
                trashcnt += 1
        else:
            return


def crc_check(pkt):
    return puscrc(pkt)


def get_sdu_info(pkt):
    sduid = pkt[SDUID_OFF]
    seqnmb = int.from_bytes(pkt[SDU_SEQ_NMB_OFF:SDU_SEQ_NMB_OFF + SDU_SEQ_NMB_LEN], 'big')
    datalen = int.from_bytes(pkt[SDU_DATALEN_OFF:SDU_DATALEN_OFF + SDU_DATALEN_LEN], 'big')

    return sduid, seqnmb, datalen


def get_pkt_time(pkt):
    coarse = int.from_bytes(pkt[TIME_OFF:TIME_OFF + TIME_C_LEN], 'big')
    fine = int.from_bytes(pkt[TIME_OFF + TIME_C_LEN:TIME_OFF + TIME_C_LEN + TIME_F_LEN], 'big')

    return coarse + fine / 1e6


def get_ce_id(pkt):
    # OBSID_CeCounter_TimeStamp_SequenceNumber.ce

    pktseqcnt = int.from_bytes(pkt[2:4], 'big') & 0x3FFF

    ts = int.from_bytes(pkt[SDU_DATA_OFF + 6: SDU_DATA_OFF + 12], 'big')
    coarse = ts >> 16
    fine = (ts & 0xFFFF) << 8

    obsid = int.from_bytes(pkt[SDU_DATA_OFF + 12: SDU_DATA_OFF + 16], 'big')
    cecnt = int.from_bytes(pkt[SDU_DATA_OFF + 16: SDU_DATA_OFF + 18], 'big')

    product = PRODUCT_IDS[pkt[SDU_DATA_OFF + 28]]
    # product = pkt[SDU_DATA_OFF + 28]

    return '{:010d}_{:05d}_{:09d}{:06d}_{:05d}_{}'.format(obsid, cecnt, coarse, fine, pktseqcnt, product)


def extract_ce_data(pkt, check_seq=CHECK_SEQ):
    global seqcnt

    sduid, seqnmb, datalen = get_sdu_info(pkt)

    if check_seq:
        if seqnmb != seqcnt:
            logging.warning('out-of-sequence packet ({} vs {}) at {}'.format(seqnmb, seqcnt, get_pkt_time(pkt)))
            seqcnt = seqnmb

    seqcnt += 1

    return pkt[SDU_DATA_OFF:SDU_DATA_OFF + datalen]


def parse_pkts(fd):
    global seqcnt

    ces = {}
    bad_ces = {}
    hks = {}
    tx = False
    txtime = None
    ce_id = None
    txpkts = None

    while True:
        pkt = extract_pus_crc(fd)
        if pkt is None:
            break

        # discard TCs
        if (pkt[0] >> 4) & 1:
            continue

        # handle ENG telemetry
        elif pkt[ST_OFF] in PROC_ST:
            pktkey, descr, procpkt, timestamp, decoded = proc_hk(pkt)

            if pktkey is None:
                logging.debug("Unidentified packet: {}".format(pkt[:SDUID_OFF].hex()))
                continue

            key = (*pktkey, descr)

            if isinstance(procpkt, bytes):
                tpsd = None
                params = None
                values = (*timestamp, procpkt)
                fmts = None
            else:
                tpsd = procpkt[0]
                params = procpkt[1]
                fmts = procpkt[3]

                if tpsd == -1:
                    values = (*timestamp, *procpkt[2])
                else:
                    values = (*timestamp, *[(x[0], x[1][1]) for x in procpkt[2]])

            if key in hks:
                hks[key]['values'].append(values)
            else:
                if params is not None:
                    params = [(x[1], y) for x, y in zip(params, fmts)]

                hks[key] = {'descr': descr, 'tpsd': tpsd, 'params': params, 'values': [values], 'decoded': decoded}

        elif pkt[ST_OFF] == 13 and pkt[SDUID_OFF] == SDUID:  # TODO: replace with SDUID

            if pkt[SST_OFF] == 1:
                if not tx:
                    tx = True
                    txtime = get_pkt_time(pkt)
                    ce_id = get_ce_id(pkt)
                    seqcnt = 1
                    txpkts = [extract_ce_data(pkt)]

                else:
                    if len(txpkts) > 1:
                        logging.warning('incomplete downlink at {}'.format(txtime))
                        bad_ces[ce_id] = b''.join(txpkts)
                    else:
                        logging.debug('single packet downlink at {}'.format(txtime))
                        ces[ce_id] = b''.join(txpkts)
                    seqcnt = 1
                    txpkts = [extract_ce_data(pkt)]
                    tx = True
                    txtime = get_pkt_time(pkt)
                    ce_id = get_ce_id(pkt)

            elif pkt[SST_OFF] == 2:
                if tx:
                    txpkts.append(extract_ce_data(pkt))
                else:
                    logging.warning('missing first packet for downlink at {}'.format(get_pkt_time(pkt)))

            elif pkt[SST_OFF] == 3:
                if tx:
                    txpkts.append(extract_ce_data(pkt))
                    ces[ce_id] = b''.join(txpkts)
                    tx = False
                    logging.info('finished {}'.format(txtime))
                else:
                    logging.warning('unexpected end-of-transmission packet at {}'.format(get_pkt_time(pkt)))
                    tx = False

            elif pkt[SST_OFF] == 4:
                if tx:
                    logging.warning('aborted downlink at {}'.format(get_pkt_time(pkt)))
                    txpkts.append(extract_ce_data(pkt))
                    bad_ces[ce_id] = b''.join(txpkts)
                    tx = False
                else:
                    logging.warning('unexpected abort-of-transmission packet at {}'.format(get_pkt_time(pkt)))
                    tx = False

            else:
                logging.error("I shouldn't be here! ({})".format(get_pkt_time(pkt)))

        else:
            logging.debug("Packet not processed: {}, {}".format(pkt[ST_OFF], pkt[SST_OFF]))

    return ces, bad_ces, hks


def extract(infile, outdir):
    global trashcnt

    # extracted_ces = []
    # for ce in [infile+f'_{x}.ce' for x in range(1,4)]:
    #     outpath = os.path.join(outdir,os.path.basename(ce))
    #     try:
    #         with open(outpath, 'wb') as fd:
    #             fd.write(b'a')
    #         extracted_ces.append(outpath)
    #     except Exception as err:
    #         logging.error('Failed writing {}'.format(outpath))
    #         logging.exception(err)
    #
    # return extracted_ces

    with open(infile, 'rb') as fd:
        try:
            trashcnt = 0
            good_ces, bad_ces, hks = parse_pkts(fd)
            if trashcnt != 0:
                logging.warning('skipped {} bytes because of wrong CRCs'.format(trashcnt))
        except Exception as err:
            logging.exception(err)

    logging.info('extracted {} files'.format(len(good_ces)))

    if len(bad_ces) != 0:
        logging.warning('there were {} bad compression entities'.format(len(bad_ces)))

    extracted_ces = []
    for ce in good_ces:
        outfile = '{}.ce'.format(ce)
        try:
            with open(os.path.join(outdir, outfile), 'wb') as fd:
                fd.write(good_ces[ce])
            extracted_ces.append(outfile)
        except Exception as err:
            logging.error('Failed writing {}'.format(outfile))
            logging.exception(err)

    return extracted_ces, hks


def decompress(cefile, outdir):

    cefile = os.path.join(outdir, cefile)

    logging.info("Decompressing {}".format(cefile))
    fitsfile = os.path.basename(cefile)[:-2] + 'fits'
    fitspath = os.path.join(outdir, fitsfile)

    proc = subprocess.run([CE_EXEC, cefile, fitspath], capture_output=True)

    for msg in proc.stdout.decode().split('\n'):
        if msg.strip():
            logging.info(msg.replace("\"", "\'"))

    for err in proc.stderr.decode().split('\n'):
        if err.strip():
            logging.error(err.replace("\"", "\'"))

    if proc.returncode != 0:
        logging.error("Decompression exited with status {}".format(proc.returncode))
        raise Exception("Decompression failed for {}".format(cefile))

    return fitspath


def mk_hk_prod(hks, infile):
    hdl = mk_hdl('HK')

    for key in hks:

        try:
            hdu = mk_hk_hdu(key, hks[key])
            hdl.append(hdu)
        except Exception as err:
            logging.error(err)

    fname = infile.replace('L0b', 'L0d').replace('.dat', '_ENG.fits')
    hdl.writeto(fname, overwrite=True)

    return fname


def mk_hk_hdu(key, hk):
    st, sst, apid, pi1val, descr = key

    if hk['descr'] is not None:
        name = hk['descr']
    else:
        name = '{}-{}-{}-{}'.format(st, sst, apid, pi1val)

    hdu = fits.BinTableHDU()
    hdu.header['SRVTYPE'] = (st, 'PUS service type')
    hdu.header['SRVSBTYP'] = (sst, 'PUS sub-service type')
    hdu.header['APID'] = (apid, 'Packet APID')
    hdu.header['PI1VAL'] = (pi1val, 'PUS packet discriminant value')
    hdu.header['PKTDESCR'] = (descr, 'Packet description')
    hdu.header['NPKTS'] = (len(hk['values']), 'Number of processed packet samples of this kind')
    hdu.header['DECODED'] = (hk['decoded'], 'Parameter decoding success flag')

    tab = mk_hk_table(hk)

    hdu.data = tab
    hdu.name = name

    hdu.add_checksum()

    return hdu


def mk_hk_table(data):
    TIMETAG = [('PktTime', 'd'), ('SyncFlag', 'B')]

    if data['tpsd'] is not None and data['tpsd'] != -1:
        raise NotImplementedError('Variable length packets are not yet handled.')

    if data['decoded']:
        cols = TIMETAG + data['params']
    else:
        # find max length of undecoded source data
        maxlen = max([len(x[-1]) for x in data['values']])
        cols = TIMETAG + [('Undecoded source data', '|S{}'.format(maxlen))]

    tab = np.array(data['values'], dtype=[(p[0], FMT_LUT.get(p[1], p[1])) for p in cols])

    return tab


def merge_fits(sorted_files, infile):
    # ED
    ed_merged = merge_ed(sorted_files['SXI-SCI-ED'], infile)

    # FT
    ft_merged = merge_ft(sorted_files['SXI-SCI-FT'], infile)

    # FF
    ff_merged = merge_ff(sorted_files['SXI-SCI-FF'], infile)

    # ST
    st_merged = merge_st(sorted_files['SXI-SCI-ST'], infile)

    # PT
    pt_merged = merge_pt(sorted_files['SXI-SCI-PT'], infile)

    # UV
    uv_merged = merge_uv(sorted_files['SXI-SCI-UV'], infile)

    return ed_merged, ft_merged, ff_merged, st_merged, pt_merged, uv_merged


def merge_ed(files, infile):
    if len(files) == 0:
        return

    hdul = mk_hdl('ED')

    group_idx = 1  # to associate frames to a group
    group_data = []
    frame_data = []
    ed_data = []

    meta = None
    for file in files:
        try:
            ff = format_ed_fits(file, group_idx)
            group_data.append(ff[0])
            frame_data += ff[1]
            ed_data += ff[2]

            if meta is None:
                metaf = fits.open(file)
                metah = metaf[0]
                metah.verify('fix')
                meta = metah.header
        except Exception as err:
            logging.error(err)
        group_idx += 1

    p_head = hdul[0].header
    p_head['SOFTVER'] = meta['VERSION_NUMBER']
    p_head['BUILD'] = meta['BUILD_NUMBER']
    p_head['SDPVER'] = meta['SDP_VERSION']
    p_head['CREATOR'] = "SXITLM2FITS"
    p_head['TLM2FITS'] = "0.1"
    p_head['DATE'] = datetime.datetime.isoformat(datetime.datetime.utcnow())

    group_table = fits.BinTableHDU(
        data=np.array(group_data, dtype=[(p[0], FMT_LUT.get(p[1])) for p in GROUP_TABLE_STRUCT]), name='GROUP_HK')
    frame_table = fits.BinTableHDU(
        data=np.array(frame_data, dtype=[(p[0], FMT_LUT.get(p[1])) for p in FRAME_TABLE_STRUCT]), name='FRAME_HK')
    ed_table = fits.BinTableHDU(data=np.array(ed_data, dtype=ED_BIN_DTYPE), name='EVENTS')

    # comment header items
    gcom = group_table.header.comments

    # checksums
    group_table.add_checksum()
    frame_table.add_checksum()
    ed_table.add_checksum()

    hdul.append(group_table)
    hdul.append(frame_table)
    hdul.append(ed_table)

    fname = infile.replace('L0b', 'L0d').replace('.dat', '.fits')

    try:
        hdul.writeto(fname, overwrite=True)
    except Exception as err:
        logging.exception(err)
        return

    return fname


def format_ed_fits(fname, gidx):
    ff = fits.open(fname)

    group = ff[1]
    frames = ff[2]
    evts = ff[3]

    # rearrange group table
    gd = group.data['Frame_001']
    phdu = ff[0]

    # fix potential FITS header violations
    phdu.verify('fix')

    # rearrange frame table
    fd = frames.data
    ed = evts.data

    t_frames = calc_frame_time(fd, gd)
    frames_new = [tuple(fd[n][:].tolist() + [t_frames.get(fd[n][-1]), gidx]) for n in
                  fd.names[1:]]  # TODO: omit crs and fine time and use calc time instead once included

    hinfo = phdu.header
    hdata = [hinfo.get(x) for x in HEADER_KEYS_GROUP]

    # fix broken header fields
    hdata[1] = int(hdata[1].split(' ')[0])
    hdata[5] = '0xEF908030'
    hdata[6] = str(hdata[6].split(' ')[0])
    hdata[7] = int(hdata[7].split(' ')[0])

    # TODO: REMOVE manual tweaks
    group_new = tuple([gidx, *hdata] + gd[:-3].tolist() + [gd[-1]])
    # group_new = tuple([gidx] + group.data['Frame_001'].tolist())

    # rearrange ED table
    ed['TIME'] = np.array([t_frames.get(x, np.nan) for x in ed['CCDFRAME']])

    ed_new = [(*ed[i][:6], ed[i][6:]) for i in range(ed.size) if not np.isnan(ed[i][0])]

    return group_new, frames_new, ed_new


def merge_ft(files, infile):
    if len(files) == 0:
        return

    hdul = mk_hdl('FT')

    group_idx = 1  # to associate frames to a group
    group_data = []
    frame_data = []
    ft_data = []

    meta = None
    for file in files:
        try:
            ff = format_ft_fits(file, group_idx)
            group_data.append(ff[0])
            frame_data += ff[1]
            ft_data += ff[2]

            if meta is None:
                metaf = fits.open(file)
                metah = metaf[0]
                metah.verify('fix')
                meta = metah.header
        except Exception as err:
            logging.error(err)
        group_idx += 1

    fname = infile.replace('L0b', 'L0d').replace('.dat', '-FT.fits')

    try:
        hdul.writeto(fname)
    except Exception as err:
        logging.exception(err)
        return

    return fname


def format_ft_fits(fname, gidx):
    ff = fits.open(fname)

    group = ff['GROUP_HK']
    frames = ff['FRAME_HK']

    nodes = []
    for node in FT_NODES:
        if node in ff:
            nodes.append(ff[node].data)
        else:
            nodes.append(None)

    group_new = tuple([gidx] + group.data.tolist())
    frames_new = tuple(frames.data.tolist() + [gidx])

    return group_new, frames_new, nodes


def merge_ff(files, infile):
    if len(files) == 0:
        return

    hdul = mk_hdl('FF')

    for file in files:
        try:
            ff = fits.open(file)
            print(ff)
        except Exception as err:
            print(err)
            logging.error(err)

    fname = infile.replace('L0b', 'L0d').replace('.dat', '-FF.fits')

    try:
        hdul.writeto(fname)
    except Exception as err:
        logging.exception(err)
        return

    return fname


def merge_st(files, infile):
    fname = None

    hdul = mk_hdl('ST')

    for file in files:
        try:
            ff = fits.open(file)
            print(ff)
        except Exception as err:
            print(err)
            logging.error(err)

    return fname


def merge_pt(files, infile):
    fname = None

    hdul = mk_hdl('PT')

    for file in files:
        try:
            ff = fits.open(file)
            print(ff)
        except Exception as err:
            print(err)
            logging.error(err)

    return fname


def merge_uv(files, infile):
    fname = None

    hdul = mk_hdl('UV')

    for file in files:
        try:
            ff = fits.open(file)
            print(ff)
        except Exception as err:
            print(err)
            logging.error(err)

    return fname


def get_dp_desc(dpid):
    try:
        return data_pool[dpid + DP_OFFSET][0]
    except KeyError:
        logging.error("Unknown DP ID {} in header".format(dpid))
        return str(dpid)[:8]


def calc_frame_time(rarr, reftime):
    # TODO: use actual values from frames
    arr = np.vstack([rarr[n] for n in rarr.names[1:]]).T

    ###
    ct, ft, _ = reftime[-3:]
    fcnts = rarr[-1][1:]
    tt = ct + (ft << 8) / 1e6
    tts = [tt - 10 * i - .13 for i in range(len(fcnts) - 1, -1, -1)]
    return {i: t for i, t in zip(fcnts, tts)}
    ###
    return {i: t for i, t in zip(fcnt, ct + (ft << 8) / 1e6)}


def sort_by_mode(sorted_modes, file):
    fn = os.path.basename(file)

    recognised = False
    for mode in MODES:
        if fn.count(mode):
            sorted_modes[mode].append(file)
            recognised = True
            break

    if not recognised:
        logging.error('Unidentified mode for file {}'.format(file))

    return sorted_modes


def mk_hdl(dmode):
    hdl = fits.HDUList()
    phdu = fits.PrimaryHDU()

    phdu.header['TELESCOP'] = 'SMILE'
    phdu.header['INSTRUME'] = 'SXI'
    phdu.header['DATAMODE'] = dmode

    hdl.append(phdu)

    return hdl


def process_file(infile, outdir):
    ces, hks = extract(infile, outdir)

    decompressed = {mode: [] for mode in MODES}
    for ce in ces:
        try:
            fitspath = decompress(ce, outdir)
            if os.path.isfile(fitspath):
                decompressed = sort_by_mode(decompressed, fitspath)
        except Exception as err:
            # logging.error('Decompression failed for {}'.format(ce))
            logging.exception(err)

    merged = merge_fits(decompressed, infile)

    # put HK in FITS
    try:
        hkfile = mk_hk_prod(hks, infile)
    except Exception as err:
        hkfile = None
        logging.error("Failed creating ENG product for {} ({}).".format(infile, err))

    return *merged, hkfile


def load_dp():
    with open('dp.csv', 'r') as fd:
        dp = fd.read()

    data = [x.split('|')[:3] for x in dp.split('\n')[2:]]

    return {int(x[1]): (x[0].strip(), x[2].strip()) for x in data if x[0]}


def setup_logging(output_dir):
    # Configure logging to write to a file in the output directory
    log_filename = os.path.join(output_dir, "log.json")
    logging.basicConfig(filename=log_filename, level=logging.INFO,
                        format='  {\n    "timestamp": "%(asctime)s",  \n    "level": "%(levelname)s",  \n    "message": "%(message)s"\n  },')

    return log_filename


if __name__ == '__main__':

    setup_logging('/home/marko/space/smile/cedata/proc')
    process_file('/home/marko/space/smile/datapools/UL_flatsat_08072024_1156_rev_clk_dgen.bin', '/home/marko/space/smile/cedata/proc')
    sys.exit()

    infile = sys.argv[1]

    if len(sys.argv) >= 3:
        outdir = sys.argv[2]
    else:
        outdir = None

    process_file(infile, outdir)




