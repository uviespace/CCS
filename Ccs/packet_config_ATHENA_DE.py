"""
Utility functions for communication with ATHENA detector electronics

Ref.: WFI_IAAT_ICD_141210_0001
      WFI_FP_DesignReport_draft_04Aug21

Author: Marko Mecina (UVIE)
"""

import ctypes
import io
import os
import queue
import socket

import numpy as np
from astropy.io import fits
from packet_config_ATHENA import RawGetterSetter


class EppStates:
    """
    EPP FSM states
    """
    INIT = 0xFF00
    STANDBY = 0xFFF0
    PROGRAM = 0xFF80
    OGEN = 0xFF8A
    NGEN = 0xFF8B
    DIAG_OGEN = 0xFFFA
    DIAG_NGEN = 0xFFFB
    DIAG = 0xFFFC
    WORK = 0xFFFF


# dict of states
EPP_STATES = {k: EppStates.__dict__[k] for k in EppStates.__dict__ if not k.startswith('_')}


class IfAddr:
    """
    FP interface addresses
    """
    HK = 0x33
    CMD = 0x34
    SCI = 0x35
    ECHO = 0x20


IF_ADDR = {k: IfAddr.__dict__[k] for k in IfAddr.__dict__ if not k.startswith('_')}


class CmdDir:
    """
    Write/request ID
    """
    SEND = 0x4182
    RECV = 0xC003


# HK & command interface

STRUCT_CMD_PKT = [
    ("ifaddr", ctypes.c_uint8),
    ("addr", ctypes.c_uint16),
    ("txrx", ctypes.c_uint16),
    ("cmddata", ctypes.c_uint16)
]


class CommandBaseStruct(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [(label, ctype) for label, ctype in STRUCT_CMD_PKT]

    def __init__(self):
        super(CommandBaseStruct).__init__()


IF_LEN = 1
CMD_LEN = ctypes.sizeof(CommandBaseStruct)
ACK_LEN = 3
SCI_CMD_LEN = 2


class CommandBase(ctypes.Union, RawGetterSetter):
    """
    Base class for command packets
    """
    _pack_ = 1
    _fields_ = [
        ('items', CommandBaseStruct),
        ('bin', ctypes.c_ubyte * CMD_LEN)
    ]


class HkCmdWrite(CommandBase):

    def __init__(self, addr, data):
        super(HkCmdWrite).__init__()
        self.items.ifaddr = IfAddr.HK
        self.items.addr = addr
        self.items.txrx = CmdDir.SEND
        self.items.cmddata = data


class HkCmdRead(CommandBase):

    def __init__(self, addr):
        super(HkCmdRead).__init__()
        self.items.ifaddr = IfAddr.HK
        self.items.addr = addr
        self.items.txrx = CmdDir.RECV
        self.items.cmddata = 0


class CmdWrite(CommandBase):

    def __init__(self, addr, data):
        super(CmdWrite).__init__()
        self.items.ifaddr = IfAddr.CMD
        self.items.addr = addr
        self.items.txrx = CmdDir.SEND
        self.items.cmddata = data


class CmdRead(CommandBase):

    def __init__(self, addr):
        super(CmdRead).__init__()
        self.items.ifaddr = IfAddr.CMD
        self.items.addr = addr
        self.items.txrx = CmdDir.RECV
        self.items.cmddata = 0


# aliases for script backwards-compatibility
CmdSend = CmdWrite
CmdRecv = CmdRead
HkCmdSend = HkCmdWrite
HkCmdRecv = HkCmdRead


class Ack:

    def __init__(self, raw=bytes(ACK_LEN)):
        self._raw = raw
        # self._val = int.from_bytes(raw, 'big')

    def __str__(self):
        return self._raw.hex().upper()

    @property
    def ifaddr(self):
        return self._raw[0]

    @ifaddr.setter
    def ifaddr(self, addr):
        self._raw = addr.to_bytes(1, 'big') + self._raw[1:]

    @property
    def data(self):
        return self._raw[1:]
        # return self._val & 0xFFFF

    @data.setter
    def data(self, d):
        self._raw = self._raw[:1] + d[:2]


class HkPkt:

    def __init__(self, raw):
        self._raw = raw

    @property
    def ifaddr(self):
        return self._raw[0]


# Science interface

FRAME_SIZE_X = 512
FRAME_SIZE_Y = 512

EVT_PKT_ELEMENT_LEN = 6  # length of event packet element (timestamp, header, pixel, footer) in bytes
STRUCT_EVT_PIX = {  # name, bitsize, bitoffset (LSB)
    "FRAME_N": (8, 40),
    "ENERGY": (14, 26),
    "LINE_N": (9, 17),
    "PIXEL_N": (9, 8),
    "PFLAGS": (8, 0)
}


class PixProcFlags:
    """
    Flags indicating processing steps
    """
    PT = 0b10000000
    T2 = 0b01000000
    T1 = 0b00100000
    BM = 0b00010000
    LT = 0b00001000
    UT = 0b00000100
    HP = 0b00000010
    DP = 0b00000001


STRUCT_EVT_HEADER = {
    "FRAME_N": (8, 40),
    "HEADER": (32, 8),
    "INDICTR": (8, 0)
}

STRUCT_EVT_TIMESTAMP = {
    "FRAME_N": (8, 40),
    "SPARE": (2, 38),
    "SEC": (24, 14),
    "SUBSEC": (14, 0)
}

# TBD
STRUCT_EVT_FOOTER = {}


class EvtPktBase:
    """
    Base class for event packet elements
    """

    def __init__(self, byt):
        assert len(byt) == EVT_PKT_ELEMENT_LEN
        self._raw = byt
        self._val = int.from_bytes(byt, 'big')

    @property
    def raw(self):
        return self._raw

    @property
    def frame_n(self):
        return _shift_mask(self._val, STRUCT_EVT_PIX["FRAME_N"])


class EvtPix(EvtPktBase):
    """
    Event Pixel element
    """

    def __init__(self, raw):
        super(EvtPix, self).__init__(raw)

    @property
    def energy(self):
        return _shift_mask(self._val, STRUCT_EVT_PIX["ENERGY"])

    @property
    def line_n(self):
        return _shift_mask(self._val, STRUCT_EVT_PIX["LINE_N"])

    @property
    def pixel_n(self):
        return _shift_mask(self._val, STRUCT_EVT_PIX["PIXEL_N"])

    @property
    def pflags(self):
        return _shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"])

    @property
    def pflags_PT(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.PT) >> 7

    @property
    def pflags_T2(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.T2) >> 6

    @property
    def pflags_T1(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.T1) >> 5

    @property
    def pflags_BM(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.BM) >> 4

    @property
    def pflags_LT(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.LT) >> 3

    @property
    def pflags_UT(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.UT) >> 2

    @property
    def pflags_HP(self):
        return (_shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.HP) >> 1

    @property
    def pflags_DP(self):
        return _shift_mask(self._val, STRUCT_EVT_PIX["PFLAGS"]) & PixProcFlags.DP


class EvtHeader(EvtPktBase):
    """
    *EventFrame* header
    """

    def __init__(self, raw):
        super(EvtHeader, self).__init__(raw)

    @property
    def header(self):
        return _shift_mask(self._val, STRUCT_EVT_HEADER["HEADER"])

    @property
    def header_indicator(self):
        return _shift_mask(self._val, STRUCT_EVT_HEADER["INDICTR"])


class EvtFooter(EvtPktBase):
    """
    *EventFrame* footer
    """

    def __init__(self, raw):
        super(EvtFooter, self).__init__(raw)

    @property
    def foo(self):
        return


class EvtTimestamp(EvtPktBase):
    """
    *EventFrame* time stamp structure
    """

    def __init__(self, raw):
        super(EvtTimestamp, self).__init__(raw)

    @property
    def spare(self):
        return _shift_mask(self._val, STRUCT_EVT_TIMESTAMP["SPARE"])

    @property
    def seconds(self):
        return _shift_mask(self._val, STRUCT_EVT_TIMESTAMP["SEC"])

    @property
    def subseconds(self):
        return _shift_mask(self._val, STRUCT_EVT_TIMESTAMP["SUBSEC"])


def _shift_mask(x, bs_os):
    """
    Shift and mask packet element to obtain parameter value.
    
    :param x: integer value of entire packet element (6 bytes)
    :type x: int 
    :param bs_os: size and offset (from LSB) of parameter in bits
    :type bs_os: tuple
    :return: 
    """
    return (x >> bs_os[1]) & (2 ** bs_os[0] - 1)


class EventFrame:
    """
    FP frame containing event data
    """

    def __init__(self, raw, process=True, notime=False):
        self._raw = raw
        self._len = len(raw)
        self.evt_list_proc = None

        if notime:
            hoff = 1
            poff = 2
            self.timestamp = None
        else:
            hoff = 1
            poff = 2
            self.timestamp = EvtTimestamp(raw[:EVT_PKT_ELEMENT_LEN])

        self.header = EvtHeader(raw[hoff * EVT_PKT_ELEMENT_LEN:poff * EVT_PKT_ELEMENT_LEN])
        # self._pixels_block = raw[2 * EVT_PKT_ELEMENT_LEN:-EVT_PKT_ELEMENT_LEN]  # if footer is present
        self._pixels_block = raw[poff * EVT_PKT_ELEMENT_LEN:]
        self.evt_list = [self._pixels_block[i:i + EVT_PKT_ELEMENT_LEN] for i in
                         range(0, len(self._pixels_block), EVT_PKT_ELEMENT_LEN)]
        # self.footer = EvtFooter(raw[-EVT_PKT_ELEMENT_LEN:])

        if process:
            self._process_evts()

    def __str__(self):
        return 'EventFrame (ID {}, {} events)'.format(self.frameid, self.nevts)

    @property
    def nevts(self):
        return len(self.evt_list_proc)

    @property
    def frameid(self):
        return self._raw[0]

    def get_inv_evts(self):
        return [x for x in self.evt_list if x[-1] != 0xFF]

    def _process_evts(self):
        # only include valid events (LSB == 0xFF)
        self.evt_list_proc = [EvtPix(pix) for pix in self.evt_list if pix[-1] == 0xFF]

    def as_array(self, nans=False):

        # initialise empty array
        if nans:
            arr = np.zeros((FRAME_SIZE_Y, FRAME_SIZE_X))
            arr[:] = np.NAN
        else:
            arr = np.zeros((FRAME_SIZE_Y, FRAME_SIZE_X), dtype=np.uint16)

        for p in self.evt_list_proc:
            arr[p.line_n, p.pixel_n] = p.energy

        return arr

    def save_fits(self, fname, nans=False, overwrite=False):
        hdu = fits.ImageHDU(data=self.as_array(nans=nans))
        hdu.header['FRAMENUM'] = self.header.frame_n
        hdu.header['NEVTS'] = len(self.evt_list)

        hdu.writeto(fname, overwrite=overwrite)
        return fname


# delay = 0xXX * sys_clk period
SCI_DELAY_CONT = 0x00  # continuous transmission
SCI_DELAY_NOTX = 0xFF  # no transmission


class SciCmd:

    def __init__(self, delay):
        assert 0 <= delay < 256
        self._raw = ((IfAddr.SCI << 8) + delay).to_bytes(SCI_CMD_LEN, 'big')

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, rawdata):
        self._raw = rawdata

    @property
    def hex(self):
        return self._raw.hex(' ').upper()

    @property
    def ifaddr(self):
        return self._raw[0]

    @property
    def delay(self):
        return self._raw[1]


class FpmPktParser:
    """
    Parses telemetry received from FPM
    """

    def __init__(self, scibytes, echobytes=None, defaultbytes=1024):

        self.scibytes = scibytes
        self.echobytes = echobytes
        self.defaultbytes = defaultbytes

        self.lastpkt = None

    def __call__(self, sock):

        strict = True
        msg = sock.recv(IF_LEN)

        if not msg:
            return b''

        if msg[0] == IfAddr.CMD:
            mlen = ACK_LEN - IF_LEN
        elif msg[0] == IfAddr.SCI:
            mlen = self.scibytes
        elif msg[0] == IfAddr.HK:
            mlen = ACK_LEN - IF_LEN
            # TODO: HK interface
            # msg += sock.recv(1)
            # mlen = msg[1]  # first byte after interface ID specifies HK length?
        elif msg[0] == IfAddr.ECHO:
            if self.echobytes is None:
                print('WARNING: Echo length is not defined, reading {}!'.format(self.defaultbytes))
                mlen = self.defaultbytes
                strict = False
                # raise ValueError('WARNING: Echo length is not defined, reading {}!'.format(self.defaultbytes))
            else:
                mlen = self.echobytes

        else:
            print('ERROR: Unknown interface ID {:02X}'.format(msg[0]))
            mlen = self.defaultbytes
            strict = False

        msg += self.read_socket(sock, mlen, strict=strict)

        self.lastpkt = msg

        return msg

    def set_scibytes(self, nbytes):
        self.scibytes = nbytes

    def set_echobytes(self, nbytes):
        self.echobytes = nbytes

    def set_defaultbytes(self, nbytes):
        self.defaultbytes = nbytes

    def read_socket(self, sock, rlen, strict=True):
        msg = b''

        if strict:
            while len(msg) < rlen:
                try:
                    msg += sock.recv(rlen - len(msg))
                except socket.timeout:
                    continue
        else:
            msg += sock.recv(rlen)

        return msg


class FpmProcessor:
    """
    Processes FPM packets and assembles event frames.
    """

    def __init__(self, ashex=True, process=True, notime=False, tofile=None, queue_to=10):
        self.ashex = ashex
        self.process = process
        self.notime = notime

        self.cfdata = b''
        self.curfrm = -1
        self.framecnt = 0

        self.frames = []
        self.tofile = tofile

        self.queue_to = queue_to

        if tofile is not None:
            self.tofile = open(tofile, 'wb')

    def __call__(self, buf, ts=None):

        assert isinstance(buf, queue.Queue)

        try:
            pkt = buf.get(timeout=self.queue_to)
        except queue.Empty:
            return

        self.frames.clear()

        try:
            if self.tofile is not None:
                self.tofile.write(pkt)
                self.tofile.flush()

            # process non-SCI data
            if pkt[0] != IfAddr.SCI:
                return pkt.hex(sep=' ') if self.ashex else pkt

            # process data from SCI itnerface
            nevts = (len(pkt) - 1) // EVT_PKT_ELEMENT_LEN
            buf = io.BytesIO(pkt[1:])
            for i in range(nevts):
                self.proc(buf)

            if self.frames:
                return self.frames

        except Exception as err:
            print(err)

    def proc(self, buf, verbose=False):

        ed = buf.read(EVT_PKT_ELEMENT_LEN)

        if ed[0] == self.curfrm:
            self.cfdata += ed

        else:

            if self.curfrm != -1:
                self.frames.append(self.mk_evt_frame(verbose=verbose))

            self.cfdata = ed
            self.framecnt += 1
            self.curfrm = ed[0]

    def mk_evt_frame(self, verbose=False):
        try:
            frame = EventFrame(self.cfdata)
            if verbose:
                print(frame)
        except Exception as err:
            print(err)
            return self.cfdata

        return frame

    def close_file(self):
        self.tofile.close()

    def proc_file(self, fname, npkts_sci=16, binary=False):

        assert os.path.isfile(fname)

        if binary:
            buf = open(fname, 'rb')
        else:
            f = bytes.fromhex(open(fname, 'r').read())
            buf = io.BytesIO(f)

        while True:
            pt = buf.read(IF_LEN)
            if not pt:
                print('END OF FILE.', buf.tell(), 'bytes read.')
                break
            if pt[0] == IfAddr.CMD:
                msg = buf.read(ACK_LEN - IF_LEN)
                print((pt + msg).hex(sep=' '))
            elif pt[0] == IfAddr.SCI:
                for i in range(npkts_sci):
                    self.proc(buf, verbose=True)
            else:
                print('ERROR', pt, buf.tell())

        return self.frames

    def reset(self):
        self.cfdata = b''
        self.curfrm = -1
        self.framecnt = 0

        self.frames.clear()


def filter_frames(objlist, empty_frames=True):

    if not empty_frames:
        return [x for x in objlist if isinstance(x, EventFrame)]
    else:
        return [x for x in objlist if isinstance(x, EventFrame) and x.nevts > 0]


# PCM Registers [TBC]
PCM_MODE = (0x0000, False, 0x0000)
PCM_CMD = (0x0000, False, 0x0000)
PCM_SERIAL_NO = (0x0000, False, 0x0000)
PCM_HW_VERSION = (0x0000, False, 0x0000)
PCM_SW_VERSION = (0x0000, False, 0x0000)
PCM_STATUS = (0x0000, False, 0x0000)
PCM_PWR_STATUS = (0x0000, False, 0x0000)
PCM_V_SET_SWA_VSUB = (0x0000, False, 0x0000)
PCM_V_SET_SWA_A_HI = (0x0000, False, 0x0000)
PCM_V_SET_SWA_A_LO = (0x0000, False, 0x0000)
PCM_V_SET_SWA_B_HI = (0x0000, False, 0x0000)
PCM_V_SET_SWA_B_LO = (0x0000, False, 0x0000)
PCM_V_SET_SWA_C_HI = (0x0000, False, 0x0000)
PCM_V_SET_SWA_C_LO = (0x0000, False, 0x0000)
PCM_V_SET_VRS_VREF = (0x0000, False, 0x0000)
PCM_V_SET_VRS_VSSS = (0x0000, False, 0x0000)
PCM_V_SET_VRS_NGATE_SF = (0x0000, False, 0x0000)
PCM_V_SET_VRS_PGATE_SF = (0x0000, False, 0x0000)
PCM_V_SET_DFT_DS = (0x0000, False, 0x0000)
PCM_V_SET_DFT_IS = (0x0000, False, 0x0000)
PCM_V_SET_DFT_OS = (0x0000, False, 0x0000)
PCM_V_SET_DFT_R1 = (0x0000, False, 0x0000)
PCM_V_SET_DFT_R2 = (0x0000, False, 0x0000)
PCM_V_SET_DFT_BC = (0x0000, False, 0x0000)
PCM_V_SET_DFT_BC_IGR = (0x0000, False, 0x0000)
PCM_V_SET_DFT_TEMP_P = (0x0000, False, 0x0000)

# HK Registers [TBC]
HK_PCM_TEMPERATURE = (0x0000, False, 0x0000)
HK_V_ACT_PCM_P5V = (0x0000, False, 0x0000)
HK_I_ACT_PCM_P5V = (0x0000, False, 0x0000)
HK_V_ACT_PCM_N5V = (0x0000, False, 0x0000)
HK_I_ACT_PCM_N5V = (0x0000, False, 0x0000)
HK_V_ACT_SWA_DVDD = (0x0000, False, 0x0000)
HK_I_ACT_SWA_DVDD = (0x0000, False, 0x0000)
HK_V_ACT_SWA_VSUB = (0x0000, False, 0x0000)
HK_I_ACT_SWA_VSUB = (0x0000, False, 0x0000)
HK_V_ACT_SWA_A_HI = (0x0000, False, 0x0000)
HK_I_ACT_SWA_A_HI = (0x0000, False, 0x0000)
HK_V_ACT_SWA_A_LO = (0x0000, False, 0x0000)
HK_I_ACT_SWA_A_LO = (0x0000, False, 0x0000)
HK_V_ACT_SWA_B_HI = (0x0000, False, 0x0000)
HK_I_ACT_SWA_B_HI = (0x0000, False, 0x0000)
HK_V_ACT_SWA_B_LO = (0x0000, False, 0x0000)
HK_I_ACT_SWA_B_LO = (0x0000, False, 0x0000)
HK_V_ACT_SWA_C_HI = (0x0000, False, 0x0000)
HK_I_ACT_SWA_C_HI = (0x0000, False, 0x0000)
HK_V_ACT_SWA_C_LO = (0x0000, False, 0x0000)
HK_I_ACT_SWA_C_LO = (0x0000, False, 0x0000)
HK_V_ACT_VRS_AVDD = (0x0000, False, 0x0000)
HK_I_ACT_VRS_AVDD = (0x0000, False, 0x0000)
HK_V_ACT_VRS_AVSS = (0x0000, False, 0x0000)
HK_I_ACT_VRS_AVSS = (0x0000, False, 0x0000)
HK_V_ACT_VRS_DVDD = (0x0000, False, 0x0000)
HK_I_ACT_VRS_DVDD = (0x0000, False, 0x0000)
HK_V_ACT_VRS_DVSS = (0x0000, False, 0x0000)
HK_I_ACT_VRS_DVSS = (0x0000, False, 0x0000)
HK_V_ACT_VRS_TVDD = (0x0000, False, 0x0000)
HK_I_ACT_VRS_TVDD = (0x0000, False, 0x0000)
HK_V_ACT_VRS_TVSS = (0x0000, False, 0x0000)
HK_I_ACT_VRS_TVSS = (0x0000, False, 0x0000)
HK_V_ACT_VRS_VREF = (0x0000, False, 0x0000)
HK_I_ACT_VRS_VREF = (0x0000, False, 0x0000)
HK_V_ACT_VRS_VSSS = (0x0000, False, 0x0000)
HK_I_ACT_VRS_VSSS = (0x0000, False, 0x0000)
HK_V_ACT_VRS_NGATE_SF = (0x0000, False, 0x0000)
HK_I_ACT_VRS_NGATE_SF = (0x0000, False, 0x0000)
HK_V_ACT_VRS_PGATE_SF = (0x0000, False, 0x0000)
HK_I_ACT_VRS_PGATE_SF = (0x0000, False, 0x0000)
HK_V_ACT_DFT_DS = (0x0000, False, 0x0000)
HK_I_ACT_DFT_DS = (0x0000, False, 0x0000)
HK_V_ACT_DFT_IS = (0x0000, False, 0x0000)
HK_I_ACT_DFT_IS = (0x0000, False, 0x0000)
HK_V_ACT_DFT_OS = (0x0000, False, 0x0000)
HK_I_ACT_DFT_OS = (0x0000, False, 0x0000)
HK_V_ACT_DFT_R1 = (0x0000, False, 0x0000)
# HK_V_ACT_DFT_R1 = (0x0000, False, 0x0000)
HK_I_ACT_DFT_R1 = (0x0000, False, 0x0000)
HK_V_ACT_DFT_R2 = (0x0000, False, 0x0000)
HK_I_ACT_DFT_R2 = (0x0000, False, 0x0000)
HK_V_ACT_DFT_BC = (0x0000, False, 0x0000)
HK_I_ACT_DFT_BC = (0x0000, False, 0x0000)
HK_V_ACT_DFT_BC_IGR = (0x0000, False, 0x0000)
HK_I_ACT_DFT_BC_IGR = (0x0000, False, 0x0000)
HK_V_ACT_DFT_TEMP_GUARD = (0x0000, False, 0x0000)
HK_I_ACT_DFT_TEMP_GUARD = (0x0000, False, 0x0000)
HK_V_ACT_DFT_TEMP_P = (0x0000, False, 0x0000)

# Sequencer Registers [TBC]
SEQ_VER_SPI_MEM = (0x0000, False, 0x0000)
SEQ_INIT_LEN = (0x0000, False, 0x0000)
SEQ_INIT_PATCH_LEN = (0x0000, False, 0x0000)
SEQ_LINE_LEN = (0x0000, False, 0x0000)
SEQ_LINE_PATCH_LEN = (0x0000, False, 0x0000)
SEQ_CMD_ACK = (0x0000, False, 0x0000)
SEQ_MODE = (0x0000, False, 0x0000)
SEQ_CMD = (0x0000, False, 0x0000)
SEQ_STARTLINE = (0x0000, False, 0x0000)
SEQ_STOPLINE = (0x0000, False, 0x0000)
SEQ_ERROR_CODE = (0x0000, False, 0x0000)
SEQ_PMEM_A = (0x0000, False, 0x0000)
SEQ_PMEM_B = (0x0000, False, 0x0000)
SEQ_LMEM = (0x0000, False, 0x0000)

# EPP registers [TBC]
EPP_UPPER_THRHLD = (0x0000, False, 0x0000)
EPP_LOWER_THRHLD = (0x0000, False, 0x0000)
EPP_PFU_MASK = (0x0000, False, 0x0000)
EPP_MODE = (0x0000, False, 0x0000)
EPP_DIAG_RATIO = (0x0000, False, 0x0000)
EPP_SELECT = (0x0000, False, 0x0000)
EPP_PFU_SWITCH = (0x0000, False, 0x0000)
EPP_MLT = (0x0000, False, 0x0000)
EPP_MHT = (0x0000, False, 0x0000)
EPP_LTP_SIGMA1 = (0x0000, False, 0x0000)
EPP_LTP_SIGMA2 = (0x0000, False, 0x0000)
EPP_PCU_OFFSET_ADDR = (0x0000, False, 0x0000)
EPP_EFU_OFFSET_ADDR = (0x0000, False, 0x0000)
EPP_SLICE_SELECT = (0x0000, False, 0x0000)
EPP_STARTLINE = (0x0000, False, 0x0000)
EPP_STOPPLINE = (0x0000, False, 0x0000)
EPP_CTCU_R1 = (0x0000, False, 0x0000)
EPP_CTCU_R2 = (0x0000, False, 0x0000)
EPP_CMD = (0x0000, False, 0x0000)
EPP_PFU_BYPASS = (0x0000, False, 0x0000)
MSD_TAB_DELAY = (0x0000, False, 0x0000)
MSD_SPW_DIV = (0x0000, False, 0x0000)
MSD_SPW_PKG_SIZE = (0x0000, False, 0x0000)
MSD_ETH_PWR_ADDR_ = (0x0000, False, 0x0000)
MSD_ETH_BURST_SIZE_ = (0x0000, False, 0x0000)
MSD_ETH_SELECT_SLICE_ = (0x0000, False, 0x0000)
MSD_ETH_SELECT_MODULE_ = (0x0000, False, 0x0000)
MSD_ETH_MAC_SOURCE_0_ = (0x0000, False, 0x0000)
MSD_ETH_MAC_SOURCE_1_ = (0x0000, False, 0x0000)
MSD_ETH_MAC_SOURCE_2_ = (0x0000, False, 0x0000)
MSD_ETH_MAC_DESTIN_0_ = (0x0000, False, 0x0000)
MSD_ETH_MAC_DESTIN_1_ = (0x0000, False, 0x0000)
MSD_ETH_MAC_DESTIN_2_ = (0x0000, False, 0x0000)
MSD_ETH_IP_SOURCE_0_ = (0x0000, False, 0x0000)
MSD_ETH_IP_SOURCE_1_ = (0x0000, False, 0x0000)
MSD_ETH_IP_DESTIN_0_ = (0x0000, False, 0x0000)
MSD_ETH_IP_DESTIN_1_ = (0x0000, False, 0x0000)
MSD_ETH_UDP_SOURCE_ = (0x0000, False, 0x0000)
MSD_ETH_UDP_DESTIN_ = (0x0000, False, 0x0000)

# EPP SUB-registers [TBC]
SRAM_FIFO3_SLICE0 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE1 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE2 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE3 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE4 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE5 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE6 = (0x0000, False, 0x0000)
SRAM_FIFO3_SLICE7 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE0 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE1 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE2 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE3 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE4 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE5 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE6 = (0x0000, False, 0x0000)
SRAM_FIFO2_SLICE7 = (0x0000, False, 0x0000)
DIAG_GOOD_RAM = (0x0000, False, 0x0000)
DIAG_BAD_RAM = (0x0000, False, 0x0000)
