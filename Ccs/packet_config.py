"""
PUS Packet header structure configuration

PUS-A for SMILE

Author: Marko Mecina (MM)
"""

import ctypes

PUS_VERSION = 1
MAX_PKT_LEN = 8192  # bytes

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
    ("SPARE1", ctypes.c_uint8, 1),
    ("PUS_VERSION", ctypes.c_uint8, 3),
    ("SPARE2", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("DEST_ID", ctypes.c_uint8, 8),
    ("CTIME", ctypes.c_uint32, 32),
    ("TIMESYNC", ctypes.c_uint32, 1),
    ("FTIME", ctypes.c_uint32, 23),
    ("SPARE", ctypes.c_uint32, 8)
]

TC_SECONDARY_HEADER = [
    ("CCSDS_SEC_HEAD_FLAG", ctypes.c_uint8, 1),
    ("PUS_VERSION", ctypes.c_uint8, 3),
    ("ACK", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("SOURCE_ID", ctypes.c_uint8, 8)
]

PEC_LEN = 2  # in byte
P_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER]) // 8
TM_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER + TM_SECONDARY_HEADER]) // 8
TC_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER + TC_SECONDARY_HEADER]) // 8


class PHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER]


class PHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', PHeaderBits),
        ('bin', ctypes.c_ubyte * P_HEADER_LEN)
    ]


class TMHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER + TM_SECONDARY_HEADER]


class TMHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', TMHeaderBits),
        ('bin', ctypes.c_ubyte * TM_HEADER_LEN)
    ]


class TCHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER + TC_SECONDARY_HEADER]


class TCHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', TCHeaderBits),
        ('bin', ctypes.c_ubyte * TC_HEADER_LEN)
    ]


CUC_OFFSET = TMHeaderBits.CTIME.offset
