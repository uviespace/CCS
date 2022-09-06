"""
PUS & SpW packet header structure definitions and utility functions

PUS-A for SMILE

Author: Marko Mecina (MM)
"""

import ctypes
import datetime
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
PUS_VERSION = 1
MAX_PKT_LEN = 1024  # bytes

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
    ("FTIME", ctypes.c_uint32, 24),
    ("TIMESYNC", ctypes.c_uint32, 8)
]

TC_SECONDARY_HEADER = [
    ("CCSDS_SEC_HEAD_FLAG", ctypes.c_uint8, 1),
    ("PUS_VERSION", ctypes.c_uint8, 3),
    ("ACK", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("SOURCE_ID", ctypes.c_uint8, 8)
]

# [format of time stamp, amount of bytes of time stamp including sync byte(s), fine time resolution, length of extra sync flag in bytes]
timepack = [ptt[9][18], 8, 1e6, 1]
CUC_EPOCH = datetime.datetime(2018, 1, 1, 0, 0, 0, 0, tzinfo=datetime.timezone.utc)


def timecal(data, string=False):

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
        coarse = data >> 32
        fine = ((data >> 8) & 0xffffff) / timepack[2]
    else:
        coarse = data >> 24
        fine = (data & 0xffffff) / timepack[2]

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
        ctime = int.from_bytes(time[:4], 'big')
        ftime = int.from_bytes(time[4:7], 'big')
        if len(time) == timepack[1]:
            sync = time[-1]
        else:
            sync = None

    else:
        raise TypeError('Unsupported input for time ({})'.format(type(time)))

    if return_bytes:
        if sync is None or sync is False:
            return ctime.to_bytes(4, 'big') + ftime.to_bytes(3, 'big')
        else:
            return ctime.to_bytes(4, 'big') + ftime.to_bytes(3, 'big') + sync.to_bytes(1, 'big')
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
    ("TARGET_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("PROTOCOL_ID", ctypes.c_uint8, 8),
    ("PKT_TYPE", ctypes.c_uint8, 2),
    ("WRITE", ctypes.c_uint8, 1),
    ("VERIFY", ctypes.c_uint8, 1),
    ("REPLY", ctypes.c_uint8, 1),
    ("INCREMENT", ctypes.c_uint8, 1),
    ("REPLY_ADDR_LEN", ctypes.c_uint8, 2),
    ("KEY", ctypes.c_uint8, 8),
    ("INIT_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("TRANSACTION_ID", ctypes.c_uint16, 16),
    ("EXT_ADDR", ctypes.c_uint8, 8),
    ("ADDR", ctypes.c_uint32, 32),
    ("DATA_LEN", ctypes.c_uint32, 24),
    ("HEADER_CRC", ctypes.c_uint32, 8)
]

RMAP_REPLY_WRITE_HEADER = [
    ("INIT_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("PROTOCOL_ID", ctypes.c_uint8, 8),
    ("PKT_TYPE", ctypes.c_uint8, 2),
    ("WRITE", ctypes.c_uint8, 1),
    ("VERIFY", ctypes.c_uint8, 1),
    ("REPLY", ctypes.c_uint8, 1),
    ("INCREMENT", ctypes.c_uint8, 1),
    ("REPLY_ADDR_LEN", ctypes.c_uint8, 2),
    ("STATUS", ctypes.c_uint8, 8),
    ("TARGET_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("TRANSACTION_ID", ctypes.c_uint16, 16),
    ("HEADER_CRC", ctypes.c_uint8, 8)
]

RMAP_REPLY_READ_HEADER = [
    ("INIT_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("PROTOCOL_ID", ctypes.c_uint8, 8),
    ("PKT_TYPE", ctypes.c_uint8, 2),
    ("WRITE", ctypes.c_uint8, 1),
    ("VERIFY", ctypes.c_uint8, 1),
    ("REPLY", ctypes.c_uint8, 1),
    ("INCREMENT", ctypes.c_uint8, 1),
    ("REPLY_ADDR_LEN", ctypes.c_uint8, 2),
    ("STATUS", ctypes.c_uint8, 8),
    ("TARGET_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("TRANSACTION_ID", ctypes.c_uint16, 16),
    ("RESERVED", ctypes.c_uint8, 8),
    ("DATA_LEN", ctypes.c_uint32, 24),
    ("HEADER_CRC", ctypes.c_uint32, 8)
]

# FEEDATA packet structure definitions

FEEDATA_TRANSFER_HEADER = [
    ("INIT_LOGICAL_ADDR", ctypes.c_uint8, 8),
    ("PROTOCOL_ID", ctypes.c_uint8, 8),
    ("DATA_LEN", ctypes.c_uint16, 16),
    ("RESERVED1", ctypes.c_uint8, 4),
    ("MODE", ctypes.c_uint8, 4),
    ("LAST_PKT", ctypes.c_uint8, 1),
    ("CCDSIDE", ctypes.c_uint8, 2),
    ("CCD", ctypes.c_uint8, 1),
    ("RESERVED2", ctypes.c_uint8, 2),
    ("PKT_TYPE", ctypes.c_uint8, 2),
    ("FRAME_CNT", ctypes.c_uint16, 16),
    ("SEQ_CNT", ctypes.c_uint16, 16)
]


class RMapCommandHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in RMAP_COMMAND_HEADER]


RMAP_COMMAND_HEADER_LEN = ctypes.sizeof(RMapCommandHeaderBits)  # sum([x[2] for x in RMAP_COMMAND_HEADER]) // 8


class RMapCommandHeader(ctypes.Union, RawGetterSetter):
    _pack_ = 1
    _fields_ = [
        ('bits', RMapCommandHeaderBits),
        ('bin', ctypes.c_ubyte * RMAP_COMMAND_HEADER_LEN)
    ]

    def __init__(self, *args, **kw):
        super(RMapCommandHeader, self).__init__(*args, **kw)
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS["RMAP"]
        self.bits.PKT_TYPE = 1


class RMapReplyWriteHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in RMAP_REPLY_WRITE_HEADER]


RMAP_REPLY_WRITE_HEADER_LEN = ctypes.sizeof(
    RMapReplyWriteHeaderBits)  # sum([x[2] for x in RMAP_REPLY_WRITE_HEADER]) // 8


class RMapReplyWriteHeader(ctypes.Union, RawGetterSetter):
    _pack_ = 1
    _fields_ = [
        ('bits', RMapReplyWriteHeaderBits),
        ('bin', ctypes.c_ubyte * RMAP_REPLY_WRITE_HEADER_LEN)
    ]

    def __init__(self, *args, **kw):
        super(RMapReplyWriteHeader, self).__init__(*args, **kw)
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS["RMAP"]
        self.bits.PKT_TYPE = 0
        self.bits.WRITE = 1
        self.bits.REPLY = 1


class RMapReplyReadHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in RMAP_REPLY_READ_HEADER]


RMAP_REPLY_READ_HEADER_LEN = ctypes.sizeof(RMapReplyReadHeaderBits)  # sum([x[2] for x in RMAP_REPLY_READ_HEADER]) // 8


class RMapReplyReadHeader(ctypes.Union, RawGetterSetter):
    _pack_ = 1
    _fields_ = [
        ('bits', RMapReplyReadHeaderBits),
        ('bin', ctypes.c_ubyte * RMAP_REPLY_READ_HEADER_LEN)
    ]

    def __init__(self, *args, **kw):
        super(RMapReplyReadHeader, self).__init__(*args, **kw)
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS["RMAP"]
        self.bits.PKT_TYPE = 0
        self.bits.WRITE = 0
        self.bits.VERIFY = 0
        self.bits.REPLY = 1


class FeeDataTransferHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in FEEDATA_TRANSFER_HEADER]


FEE_DATA_TRANSFER_HEADER_LEN = ctypes.sizeof(
    FeeDataTransferHeaderBits)  # sum([x[2] for x in FEEDATA_TRANSFER_HEADER]) // 8


class FeeDataTransferHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', FeeDataTransferHeaderBits),
        ('bin', ctypes.c_ubyte * FEE_DATA_TRANSFER_HEADER_LEN)
    ]

    def __init__(self, *args, **kw):
        super(FeeDataTransferHeader, self).__init__()
        self.bits.INIT_LOGICAL_ADDR = SPW_DPU_LOGICAL_ADDRESS
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS["FEEDATA"]

    @property
    def raw(self):
        return bytes(self.bin)

    @property
    def comptype(self):
        """Composite packet type used in DB storage, consists of sub-parameters"""
        return int.from_bytes(self.bin[4:6], 'big')


#########################
# FEE utility functions #
#########################

# FEE RW registers (SMILE-MSSL-PL-Register_map_v0.20)

FEE_CFG_REG_0  = 0x00000000
FEE_CFG_REG_1  = 0x00000004
FEE_CFG_REG_2  = 0x00000008
FEE_CFG_REG_3  = 0x0000000C
FEE_CFG_REG_4  = 0x00000010
FEE_CFG_REG_5  = 0x00000014
FEE_CFG_REG_6  = 0x00000018  # unused
FEE_CFG_REG_7  = 0x0000001C  # unused
FEE_CFG_REG_8  = 0x00000020  # unused
FEE_CFG_REG_9  = 0x00000024  # unused
FEE_CFG_REG_10 = 0x00000028  # unused
FEE_CFG_REG_11 = 0x0000002C  # unused
FEE_CFG_REG_12 = 0x00000030  # unused
FEE_CFG_REG_13 = 0x00000034  # unused
FEE_CFG_REG_14 = 0x00000038
FEE_CFG_REG_15 = 0x0000003C
FEE_CFG_REG_16 = 0x00000040
FEE_CFG_REG_17 = 0x00000044
FEE_CFG_REG_18 = 0x00000048
FEE_CFG_REG_19 = 0x0000004C
FEE_CFG_REG_20 = 0x00000050
FEE_CFG_REG_21 = 0x00000054
FEE_CFG_REG_22 = 0x00000058
FEE_CFG_REG_23 = 0x0000005C
FEE_CFG_REG_24 = 0x00000060
FEE_CFG_REG_25 = 0x00000064
FEE_CFG_REG_26 = 0x00000068


# FEE  RO registers (SMILE-MSSL-PL-Register_map_v0.20)

FEE_HK_REG_0  = 0x00000700  # reserved
FEE_HK_REG_1  = 0x00000704  # reserved
FEE_HK_REG_2  = 0x00000708  # reserved
FEE_HK_REG_3  = 0x0000070C  # reserved
FEE_HK_REG_4  = 0x00000710
FEE_HK_REG_5  = 0x00000714
FEE_HK_REG_6  = 0x00000718
FEE_HK_REG_7  = 0x0000071C
FEE_HK_REG_8  = 0x00000720
FEE_HK_REG_9  = 0x00000724
FEE_HK_REG_10 = 0x00000728
FEE_HK_REG_11 = 0x0000072C
FEE_HK_REG_12 = 0x00000730
FEE_HK_REG_13 = 0x00000734
FEE_HK_REG_14 = 0x00000738
FEE_HK_REG_15 = 0x0000073C
FEE_HK_REG_16 = 0x00000740
FEE_HK_REG_17 = 0x00000744
FEE_HK_REG_18 = 0x00000748
FEE_HK_REG_19 = 0x0000074C
FEE_HK_REG_20 = 0x00000750
FEE_HK_REG_21 = 0x00000754
FEE_HK_REG_22 = 0x00000758
FEE_HK_REG_23 = 0x0000075C
FEE_HK_REG_24 = 0x00000760  # reserved
FEE_HK_REG_25 = 0x00000764  # reserved
FEE_HK_REG_26 = 0x00000768  # reserved
FEE_HK_REG_27 = 0x0000076C  # reserved
FEE_HK_REG_28 = 0x00000770  # reserved
FEE_HK_REG_29 = 0x00000774  # reserved
FEE_HK_REG_30 = 0x00000778  # reserved
FEE_HK_REG_31 = 0x0000077C  # reserved
FEE_HK_REG_32 = 0x00000780
FEE_HK_REG_33 = 0x00000784
FEE_HK_REG_34 = 0x00000788
FEE_HK_REG_35 = 0x0000078C
FEE_HK_REG_36 = 0x00000790
FEE_HK_REG_37 = 0x00000794


# FEE modes
# see MSSL-SMILE-SXI-IRD-0001  Draft A.14, req. MSSL-IF-17
# also SMILE-MSSL-PL-Register_map_v0.22, as the IRD does not list all modes

FEE_MODE_ID_ON	   = 0x0  # the thing is switched on
FEE_MODE_ID_FTP	   = 0x1  # frame transfer pattern
FEE_MODE_ID_STBY   = 0x2  # stand-by-mode
FEE_MODE_ID_FT	   = 0x3  # frame transfer
FEE_MODE_ID_FF	   = 0x4  # full frame
FEE_CMD__ID_IMM_ON = 0x8  # immediate on-mode, this is a command, not a mode
FEE_MODE_ID_FFSIM  = 0x9  # full frame simulation simulation
FEE_MODE_ID_EVSIM  = 0xA  # event detection simulation
FEE_MODE_ID_PTP1   = 0xB  # parallel trap pump mode 1
FEE_MODE_ID_PTP2   = 0xC  # parallel trap pump mode 2
FEE_MODE_ID_STP1   = 0xD  # serial trap pump mode 1
FEE_MODE_ID_STP2   = 0xE  # serial trap pump mode 2

FEE_MODE2_NOBIN = 0x1	 # no binning mode
FEE_MODE2_BIN6  = 0x2	 # 6x6 binning mode
FEE_MODE2_BIN24 = 0x3	 # 24x4 binning mode

# these identifiy the bits in the readout node selection register
FEE_READOUT_NODE_E2	= 0b0010
FEE_READOUT_NODE_F2	= 0b0001
FEE_READOUT_NODE_E4	= 0b1000
FEE_READOUT_NODE_F4	= 0b0100

# see MSSL-SMILE-SXI-IRD-0001 Draft A.14, req. MSSL-IF-108
FEE_CCD_SIDE_F = 0x0		 # left side
FEE_CCD_SIDE_E = 0x1		 # right side
FEE_CCD_INTERLEAVED = 0x2	 # F and E inverleaved

FEE_CCD_ID_2 = 0x0
FEE_CCD_ID_4 = 0x1

FEE_PKT_TYPE_DATA	= 0x0	 # any data
FEE_PKT_TYPE_EV_DET = 0x1	 # event detection
FEE_PKT_TYPE_HK		= 0x2	 # housekeeping
FEE_PKT_TYPE_WMASK	= 0x3	 # wandering mask packet


class RMapCommandWrite(RMapCommandHeader):
    """This is intended for building an RMap Write Command"""

    def __init__(self, addr, data, verify=True, reply=True, incr=True, key=SPW_FEE_KEY,
                 initiator=SPW_DPU_LOGICAL_ADDRESS, tid=1, *args, **kwargs):
        super(RMapCommandWrite, self).__init__(*args, **kwargs)

        self.header = self.bits
        self.data = data
        self.data_crc = rmapcrc(self.data).to_bytes(RMAP_PEC_LEN, 'big')

        self.bits.TARGET_LOGICAL_ADDR = SPW_FEE_LOGICAL_ADDRESS
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS['RMAP']

        self.bits.PKT_TYPE = 1
        self.bits.WRITE = 1
        self.bits.VERIFY = verify
        self.bits.REPLY = reply
        self.bits.INCREMENT = incr
        self.bits.REPLY_ADDR_LEN = 0
        self.bits.KEY = key

        self.bits.INIT_LOGICAL_ADDR = initiator
        self.bits.TRANSACTION_ID = tid
        self.bits.EXT_ADDR = addr >> 32
        self.bits.ADDR = addr & 0xFFFFFFFF
        self.bits.DATA_LEN = len(self.data)
        self.bits.HEADER_CRC = rmapcrc(bytes(self.bin[:-1]))

    @property
    def raw(self):
        """Return raw packet with updated CRCs"""
        self.bits.HEADER_CRC = rmapcrc(bytes(self.bin[:-1]))
        self.data_crc = rmapcrc(self.data).to_bytes(RMAP_PEC_LEN, 'big')
        return bytes(self.bin) + self.data + self.data_crc

    @raw.setter
    def raw(self, rawdata):
        self.bin[:] = rawdata[:RMAP_COMMAND_HEADER_LEN]
        self.data = rawdata[RMAP_COMMAND_HEADER_LEN:-RMAP_PEC_LEN]
        self.data_crc = rawdata[-RMAP_PEC_LEN:]


class RMapCommandRead(RMapCommandHeader):
    """This is intended for building an RMap Read Command"""

    def __init__(self, addr, datalen, incr=True, key=SPW_FEE_KEY, initiator=SPW_DPU_LOGICAL_ADDRESS, tid=1,
                 *args, **kwargs):
        super(RMapCommandRead, self).__init__(*args, **kwargs)

        self.header = self.bits

        self.bits.TARGET_LOGICAL_ADDR = SPW_FEE_LOGICAL_ADDRESS
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS['RMAP']

        self.bits.PKT_TYPE = 1
        self.bits.WRITE = 0
        self.bits.VERIFY = 0
        self.bits.REPLY = 1
        self.bits.INCREMENT = incr
        self.bits.REPLY_ADDR_LEN = 0
        self.bits.KEY = key

        self.bits.INIT_LOGICAL_ADDR = initiator
        self.bits.TRANSACTION_ID = tid
        self.bits.EXT_ADDR = addr >> 32
        self.bits.ADDR = addr
        self.bits.DATA_LEN = datalen
        self.bits.HEADER_CRC = rmapcrc(bytes(self.bin[:-1]))

    @property
    def raw(self):
        """Return raw packet with updated CRCs"""
        self.bits.HEADER_CRC = rmapcrc(bytes(self.bin[:-1]))
        return bytes(self.bin)

    @raw.setter
    def raw(self, rawdata):
        self.bin[:] = rawdata[:RMAP_COMMAND_HEADER_LEN]


class FeeDataTransfer(FeeDataTransferHeader):
    """
    Bytes 4 and 5 of the data-packet-header contains additional information about the packet-content. The type-field is defined in the following way:
    - bits 15:12 = reserved for future usage
    - bits 11:8 = See MSSL-IF-17
    - bit 7 = last packet: 1 = last packet of this type in the current read-out-cycle
    - bit 6:5 = CCD side: 0 = left side (side F), 1 = right side (side E), 2 = F&E   interleaved
    - bit 4 = CCD: 0 = CCD2, 1= CCD4
    - bit 3:2 = reserved
    - bits 1:0 = packet type: 0 = data packet, 1 = Event detection packet, 2 = housekeeping packet
    """

    _modes = {FEE_MODE_ID_ON: "On Mode",
              FEE_MODE_ID_FTP: "Frame Transfer Pattern",
              FEE_MODE_ID_STBY: "Stand-By-Mode",
              FEE_MODE_ID_FT: "Frame Transfer",
              FEE_MODE_ID_FF: "Full Frame",
              FEE_MODE_ID_FFSIM: "Full frame simulation",
              FEE_MODE_ID_EVSIM: "Event detection simulation",
              FEE_MODE_ID_PTP1: "Parallel trap pumping mode 1",
              FEE_MODE_ID_PTP2: "Parallel trap pumping mode 2",
              FEE_MODE_ID_STP1: "Serial trap pumping mode 1",
              FEE_MODE_ID_STP2: "Serial trap pumping mode 2"}
    _ccd_sides = {FEE_CCD_SIDE_F: "left side (F)",
                  FEE_CCD_SIDE_E: "right side (E)",
                  FEE_CCD_INTERLEAVED: "F&E interleaved"}
    _ccds = {FEE_CCD_ID_2: "CCD2",
             FEE_CCD_ID_4: "CCD4"}
    _pkt_types = {FEE_PKT_TYPE_DATA: "Data",
                  FEE_PKT_TYPE_EV_DET: "Event detection",
                  FEE_PKT_TYPE_HK: "Housekeeping",
                  FEE_PKT_TYPE_WMASK: "Wandering mask"}

    _DATA_HK_STRUCT = []

    def __init__(self, pkt=None):
        super(FeeDataTransfer, self).__init__()

        if pkt is not None:
            self._raw = pkt
            self.bin[:] = self._raw[:FEE_DATA_TRANSFER_HEADER_LEN]
            self.data = self._raw[FEE_DATA_TRANSFER_HEADER_LEN:]

            self.set_evt_data()

        else:
            self._raw = b''
            self.set_evt_data()

        self.set_type_details()

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, rawdata):
        self.bin[:] = rawdata[:FEE_DATA_TRANSFER_HEADER_LEN]
        self.data = rawdata[FEE_DATA_TRANSFER_HEADER_LEN:]
        self._raw = rawdata
        self.set_type_details()
        self.set_evt_data()

    #@property
    def info(self):
        head = 'HEADER\n' + '\n'.join(['{}:\t{}'.format(key, self.type_details[key]) for key in self.type_details])
        if self.evt_data is not None:
            data = 'DATA\ncolumn: {}, row: {}\n\n{}'.format(self.evt_data['COLUMN'], self.evt_data['ROW'],
                                                            str(self.evt_data['IMAGE']).replace('[', ' ').replace(']', ' '))
        else:
            data = 'DATA\n' + self.data.hex().upper()

        # return head + '\n' + data
        print(head + '\n' + data)

    def set_type_details(self):
        self.type_details = {"MODE": self._modes[self.bits.MODE] if self.bits.MODE in self._modes else self.bits.MODE,
                             "LAST_PKT": bool(self.bits.LAST_PKT),
                             "CCDSIDE": self._ccd_sides[
                                 self.bits.CCDSIDE] if self.bits.CCDSIDE in self._ccd_sides else self.bits.CCDSIDE,
                             "CCD": self._ccds[self.bits.CCD] if self.bits.CCD in self._ccds else self.bits.CCD,
                             "PKT_TYPE": self._pkt_types[
                                 self.bits.PKT_TYPE] if self.bits.PKT_TYPE in self._pkt_types else self.bits.PKT_TYPE}

    def set_evt_data(self):
        if self.bits.PKT_TYPE == FEE_PKT_TYPE_EV_DET:
            evtdata = EventDetectionData()
            evtdata.bin[:] = self.data
            self.evt_data = {"COLUMN": evtdata.bits.column,
                             "ROW": evtdata.bits.row,
                             "IMAGE": np.array(evtdata.bits.array)[::-1]}  # structure according to MSSL-SMILE-SXI-IRD-0001
        else:
            self.evt_data = None


class EventDetectionFields(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("column", ctypes.c_uint16),
        ("row", ctypes.c_uint16),
        ("array", (ctypes.c_uint16 * 5) * 5)
    ]


class EventDetectionData(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ("bits", EventDetectionFields),
        ("bin", ctypes.c_ubyte * ctypes.sizeof(EventDetectionFields))
    ]
