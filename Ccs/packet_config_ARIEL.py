"""
PUS & SpW packet header structure definitions and utility functions

PUS-C for ARIEL

Author: Marko Mecina (MM)
"""
### TBD ###
import ctypes
import datetime
import struct
import numpy as np

import crcmod
from s2k_partypes import ptt

# ID of the parameter format type defining parameter
FMT_TYPE_PARAM = 'DPPXXXXX'

# pre/suffixes for TM/TC packets from/to PLMSIM
# PLM_PKT_PREFIX = b'tc PUS_TC '
PLM_PKT_PREFIX_TC_SEND = b'tc PUS_TC '
PLM_PKT_PREFIX_TC = b'TM PUS_TC '
PLM_PKT_PREFIX_TM = b'TM PUS_TM '
PLM_PKT_SUFFIX = b'\r\n'

# CRC methods
puscrc = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
rmapcrc = crcmod.mkCrcFun(0x107, rev=True, initCrc=0, xorOut=0)
PEC_LEN = 2  # in bytes
RMAP_PEC_LEN = 1

# PUS packet structure definition

PUS_PKT_VERS_NUM = 0  # 0 for space packets
PUS_VERSION = 2
MAX_PKT_LEN = 1024  # 886 for TMs [EID-1298], 504 for TCs [EID-1361]

TMTC = {0: 'TM', 1: 'TC'}
TSYNC_FLAG = {0: 'U', 1: 'S'}

PRIMARY_HEADER = [
    ("PKT_VERS_NUM", ctypes.c_uint16, 3),
    ("PKT_TYPE", ctypes.c_uint16, 1),
    ("SEC_HEAD_FLAG", ctypes.c_uint16, 1),
    ("APID", ctypes.c_uint16, 11),
    ("SEQ_FLAGS", ctypes.c_uint16, 2),
    ("PKT_SEQ_CNT", ctypes.c_uint16, 14),
    ("PKT_LEN", ctypes.c_uint16, 16)
]

TM_SECONDARY_HEADER = [
    ("PUS_VERSION", ctypes.c_uint8, 4),
    ("SCTRS", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("MTC", ctypes.c_uint16, 16),
    ("DEST_ID", ctypes.c_uint16, 16),
    ("CTIME", ctypes.c_uint32, 32),
    ("FTIME", ctypes.c_uint16, 16)
]

TC_SECONDARY_HEADER = [
    ("PUS_VERSION", ctypes.c_uint8, 4),
    ("ACK", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("SOURCE_ID", ctypes.c_uint16, 16)
]

# [format of time stamp, amount of bytes of time stamp including sync byte(s), fine time resolution, length of extra sync flag in bytes]
timepack = [ptt(9, 17), 6, 2**16, 0]
CUC_EPOCH = datetime.datetime(2020, 1, 1, 0, 0, 0, 0, tzinfo=datetime.timezone.utc)


def timecal(data, string=False, checkft=False):
    if not isinstance(data, bytes):
        try:
            return data[0]
        except (IndexError, TypeError):
            return data

    if len(data) == timepack[1]:
        sync_byte = True
    elif len(data) == timepack[1] - timepack[3]:
        sync_byte = False
    else:
        raise ValueError('Wrong length of time stamp data ({} bytes)'.format(len(data)))

    data = int.from_bytes(data, 'big')

    if sync_byte:
        coarse = data >> 24
        fine = ((data >> 8) & 0xffff) / timepack[2]
    else:
        coarse = data >> 16
        fine = (data & 0xffff) / timepack[2]

    # check for fine time overflow
    if checkft and (fine > timepack[2]):
        raise ValueError('Fine time is greater than resolution {} > {}!'.format(fine, timepack[2]))

    if string:
        if sync_byte:
            sync = 'S' if (data & 0xff) == 0b101 else 'U'
        else:
            sync = ''
        return '{:.6f}{}'.format(coarse + fine, sync)

    else:
        return coarse + fine


def calc_timestamp(time, sync=None, return_bytes=False):
    if isinstance(time, (float, int)):
        ctime = int(time)
        ftime = round(time % 1 * timepack[2])
        if ftime == timepack[2]:
            ctime += 1
            ftime = 0

    elif isinstance(time, str):
        if time[-1].upper() in ['U', 'S']:
            t = float(time[:-1])
        else:
            t = float(time)
        ctime = int(t)
        ftime = round(t % 1 * timepack[2])
        if ftime == timepack[2]:
            ctime += 1
            ftime = 0
        sync = 0b101 if time[-1].upper() == 'S' else 0

    elif isinstance(time, bytes):
        if len(time) not in [timepack[1], timepack[1] - timepack[3]]:
            raise ValueError(
                'Bytestring size ({}) does not match length specified in format ({})'.format(len(time), timepack[1]))
        ctime = int.from_bytes(time[:4], 'big')
        ftime = int.from_bytes(time[4:6], 'big')
        if len(time) == timepack[1]:
            sync = None
            # sync = time[-1]
        else:
            sync = None

    else:
        raise TypeError('Unsupported input for time ({})'.format(type(time)))

    if return_bytes:
        if sync is None or sync is False:
            return ctime.to_bytes(4, 'big') + ftime.to_bytes(2, 'big')
        else:
            pass
            # no sync byte in ARIEL?
            # return ctime.to_bytes(4, 'big') + ftime.to_bytes(2, 'big') + sync.to_bytes(1, 'big')
    else:
        return ctime, ftime, sync


# P_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER]) // 8
# TM_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER + TM_SECONDARY_HEADER]) // 8
# TC_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER + TC_SECONDARY_HEADER]) // 8

class RawGetterSetter:

    @property
    def raw(self):
        return bytes(self.bin)

    @raw.setter
    def raw(self, rawdata):
        self.bin[:] = rawdata


class PHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER]


P_HEADER_LEN = ctypes.sizeof(PHeaderBits)


class PHeader(ctypes.Union, RawGetterSetter):
    _pack_ = 1
    _fields_ = [
        ('bits', PHeaderBits),
        ('bin', ctypes.c_ubyte * P_HEADER_LEN)
    ]


class TMHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER + TM_SECONDARY_HEADER]


TM_HEADER_LEN = ctypes.sizeof(TMHeaderBits)


class TMHeader(ctypes.Union, RawGetterSetter):
    _pack_ = 1
    _fields_ = [
        ('bits', TMHeaderBits),
        ('bin', ctypes.c_ubyte * TM_HEADER_LEN)
    ]

    def __init__(self):
        super(TMHeader, self).__init__()
        self.bits.PKT_VERS_NUM = PUS_PKT_VERS_NUM
        self.bits.PKT_TYPE = 0
        self.bits.PUS_VERSION = PUS_VERSION


class TCHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER + TC_SECONDARY_HEADER]


TC_HEADER_LEN = ctypes.sizeof(TCHeaderBits)


class TCHeader(ctypes.Union, RawGetterSetter):
    _pack_ = 1
    _fields_ = [
        ('bits', TCHeaderBits),
        ('bin', ctypes.c_ubyte * TC_HEADER_LEN)
    ]

    def __init__(self, *args, **kw):
        super(TCHeader, self).__init__(*args, **kw)
        self.bits.PKT_VERS_NUM = PUS_PKT_VERS_NUM
        self.bits.PKT_TYPE = 1
        self.bits.PUS_VERSION = PUS_VERSION


CUC_OFFSET = TMHeaderBits.CTIME.offset

SPW_PROTOCOL_IDS = {
    "RMAP": 0x01,
    "FEEDATA": 0xF0,
    "CCSDS": 0x02
}

# RMAP packet structure definitions

RMAP_MAX_PKT_LEN = 2 ** 15
SPW_DPU_LOGICAL_ADDRESS = 0x50
SPW_FEE_LOGICAL_ADDRESS = 0x51
SPW_FEE_KEY = 0xD1  # application authorisation key

RMAP_COMMAND_HEADER = [
    ("TARGET_LOGICAL_ADDR", ctypes.c_uint32, 8),
    ("PROTOCOL_ID", ctypes.c_uint32, 8),
    ("PKT_TYPE", ctypes.c_uint32, 2),
    ("WRITE", ctypes.c_uint32, 1),
    ("VERIFY", ctypes.c_uint32, 1),
    ("REPLY", ctypes.c_uint32, 1),
    ("INCREMENT", ctypes.c_uint32, 1),
    ("REPLY_ADDR_LEN", ctypes.c_uint32, 2),
    ("KEY", ctypes.c_uint32, 8),
    ("INIT_LOGICAL_ADDR", ctypes.c_uint32, 8),
    ("TRANSACTION_ID", ctypes.c_uint32, 16),
    ("EXT_ADDR", ctypes.c_uint32, 8),
    ("ADDR", ctypes.c_uint32, 32),
    ("DATA_LEN", ctypes.c_uint32, 24),
    ("HEADER_CRC", ctypes.c_uint32, 8)
]

RMAP_REPLY_WRITE_HEADER = [
    ("INIT_LOGICAL_ADDR", ctypes.c_uint32, 8),
    ("PROTOCOL_ID", ctypes.c_uint32, 8),
    ("PKT_TYPE", ctypes.c_uint32, 2),
    ("WRITE", ctypes.c_uint32, 1),
    ("VERIFY", ctypes.c_uint32, 1),
    ("REPLY", ctypes.c_uint32, 1),
    ("INCREMENT", ctypes.c_uint32, 1),
    ("REPLY_ADDR_LEN", ctypes.c_uint32, 2),
    ("STATUS", ctypes.c_uint32, 8),
    ("TARGET_LOGICAL_ADDR", ctypes.c_uint32, 8),
    ("TRANSACTION_ID", ctypes.c_uint32, 16),
    ("HEADER_CRC", ctypes.c_uint32, 8)
]

RMAP_REPLY_READ_HEADER = [
    ("INIT_LOGICAL_ADDR", ctypes.c_uint32, 8),
    ("PROTOCOL_ID", ctypes.c_uint32, 8),
    ("PKT_TYPE", ctypes.c_uint32, 2),
    ("WRITE", ctypes.c_uint32, 1),
    ("VERIFY", ctypes.c_uint32, 1),
    ("REPLY", ctypes.c_uint32, 1),
    ("INCREMENT", ctypes.c_uint32, 1),
    ("REPLY_ADDR_LEN", ctypes.c_uint32, 2),
    ("STATUS", ctypes.c_uint32, 8),
    ("TARGET_LOGICAL_ADDR", ctypes.c_uint32, 8),
    ("TRANSACTION_ID", ctypes.c_uint32, 16),
    ("RESERVED", ctypes.c_uint32, 8),
    ("DATA_LEN", ctypes.c_uint32, 24),
    ("HEADER_CRC", ctypes.c_uint32, 8)
]


# S13 data header format, using python struct conventions
S13_FMT_OBSID = 'I'
S13_FMT_TIME = 'I'
S13_FMT_FTIME = 'H'
S13_FMT_COUNTER = 'H'
_S13_HEADER_FMT = S13_FMT_OBSID + S13_FMT_TIME + S13_FMT_FTIME + S13_FMT_COUNTER


def s13_unpack_data_header(buf):
    return struct.unpack('>' + _S13_HEADER_FMT, buf[:struct.calcsize(_S13_HEADER_FMT)])
