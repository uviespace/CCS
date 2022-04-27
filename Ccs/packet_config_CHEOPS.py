"""
PUS Packet header structure configuration

PUS-A for CHEOPS

Author: Marko Mecina (MM)
"""

import ctypes
import datetime
from s2k_partypes import ptt
import crcmod

# ID of the parameter format type defining parameter
FMT_TYPE_PARAM = 'DPPXXXXX'

# pre/suffixes for TM/TC packets from/to PLMSIM
PLM_PKT_PREFIX = b'tc PUS_TC '
PLM_PKT_PREFIX_TC_SEND = b'tc PUS_TC '
PLM_PKT_PREFIX_TC = b'tm PUS_TC '
PLM_PKT_PREFIX_TM = b'tm PUS_TM '
PLM_PKT_SUFFIX = b'\r\n'

# CRC methods
puscrc = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')
rmapcrc = crcmod.mkCrcFun(0x107, rev=True, initCrc=0, xorOut=0)

PEC_LEN = 2  # in bytes
RMAP_PEC_LEN = 1

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
    ("FTIME", ctypes.c_uint16, 15),
    ("TIMESYNC", ctypes.c_uint16, 1)
]

TC_SECONDARY_HEADER = [
    ("CCSDS_SEC_HEAD_FLAG", ctypes.c_uint8, 1),
    ("PUS_VERSION", ctypes.c_uint8, 3),
    ("ACK", ctypes.c_uint8, 4),
    ("SERV_TYPE", ctypes.c_uint8, 8),
    ("SERV_SUB_TYPE", ctypes.c_uint8, 8),
    ("SOURCE_ID", ctypes.c_uint8, 8)
]
# [Format of time Packet, Amount of Bytes in Time Packet, Factor for Finetime, length of extra sync flag
timepack = [ptt[9][17], 6, 2**15, 0]
CUC_EPOCH = datetime.datetime(2000, 1, 1, 0, 0, 0, 0, tzinfo=datetime.timezone.utc)


def timecal(data, string=False):
    if not isinstance(data, bytes):
        try:
            return data[0]
        except (IndexError, TypeError):
            return data

    if len(data) != timepack[1]:
        raise ValueError('Wrong length of time stamp data ({} bytes)'.format(len(data)))

    data = int.from_bytes(data, 'big')
    coarse = data >> 16
    fine = ((data & 0xffff) >> 1) / timepack[2]
    if string:
        sync = ['U', 'S'][data & 1]
        return '{:.6f}{}'.format(coarse + fine, sync)
    else:
        return coarse + fine


def calc_timestamp(time, sync=0):
    if isinstance(time, (float, int)):
        ctime = int(time)
        ftime = round(time % 1 * timepack[2])
    elif isinstance(time, str):
        t = float(time[:-1])
        ctime = int(t)
        ftime = round(t % 1 * timepack[2])
        sync = 1 if time[-1].upper() == 'S' else 0
    elif isinstance(time, bytes):
        ctime = int.from_bytes(time[:4], 'big')
        ftime = int.from_bytes(time[-2:], 'big') >> 1
        sync = time[-1] & 1

    return ctime, ftime, sync


# P_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER]) // 8
# TM_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER + TM_SECONDARY_HEADER]) // 8
# TC_HEADER_LEN = sum([x[2] for x in PRIMARY_HEADER + TC_SECONDARY_HEADER]) // 8


class PHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER]


P_HEADER_LEN = ctypes.sizeof(PHeaderBits)


class PHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', PHeaderBits),
        ('bin', ctypes.c_ubyte * P_HEADER_LEN)
    ]


class TMHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER + TM_SECONDARY_HEADER]


TM_HEADER_LEN = ctypes.sizeof(TMHeaderBits)


class TMHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', TMHeaderBits),
        ('bin', ctypes.c_ubyte * TM_HEADER_LEN)
    ]


class TCHeaderBits(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype, bits) for label, ctype, bits in PRIMARY_HEADER + TC_SECONDARY_HEADER]


TC_HEADER_LEN = ctypes.sizeof(TCHeaderBits)


class TCHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ('bits', TCHeaderBits),
        ('bin', ctypes.c_ubyte * TC_HEADER_LEN)
    ]


CUC_OFFSET = TMHeaderBits.CTIME.offset


SPW_PROTOCOL_IDS = {
    "RMAP": 0x01,
    "FEEDATA": 0xF0,
    "CCSDS": 0x02
}

class RawGetterSetter:

    @property
    def raw(self):
        return bytes(self.bin)

    @raw.setter
    def raw(self, rawdata):
        self.bin[:] = rawdata

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
        self.bits.PROTOCOL_ID = SPW_PROTOCOL_IDS["FEEDATA"]

    @property
    def raw(self):
        return bytes(self.bin)

    @property
    def comptype(self):
        """Composite packet type used in DB storage, consists of sub-parameters"""
        return int.from_bytes(self.bin[4:6], 'big')


##########################
# FEE utility functions #
##########################

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
        self.bits.ADDR = addr
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
    modes = {0: "On Mode",
             1: "Frame Transfer Pattern",
             2: "Stand-By-Mode",
             3: "Frame Transfer",
             4: "Full Frame",
             5: "Parallel trap pumping mode 1",
             6: "Parallel trap pumping mode 2",
             7: "Serial trap pumping mode 1",
             8: "Serial trap pumping mode 2"}
    ccd_sides = {0: "left side (F)",
                 1: "right side (E)",
                 2: "F&E interleaved"}
    ccds = {0: "CCD2",
            1: "CCD4"}
    pkt_types = {0: "Data",
                 1: "Event detection",
                 2: "Housekeeping"}

    DATA_HK_STRUCT = []

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

    def set_type_details(self):
        self.type_details = {"MODE": self.modes[self.bits.MODE] if self.bits.MODE in self.modes else self.bits.MODE,
                             "LAST_PKT": bool(self.bits.LAST_PKT),
                             "CCDSIDE": self.ccd_sides[
                                 self.bits.CCDSIDE] if self.bits.CCDSIDE in self.ccd_sides else self.bits.CCDSIDE,
                             "CCD": self.ccds[self.bits.CCD] if self.bits.CCD in self.ccds else self.bits.CCD,
                             "PKT_TYPE": self.pkt_types[
                                 self.bits.PKT_TYPE] if self.bits.PKT_TYPE in self.pkt_types else self.bits.PKT_TYPE}

    def set_evt_data(self):
        if self.bits.PKT_TYPE == 1:
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
