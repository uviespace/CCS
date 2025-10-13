"""
Tools to create and interpret general purpose command sequences
"""

import ctypes

NOP = 0b000
UPDT = 0b001
MOD = 0b010
CMT = 0b011
CBLK = 0b100
VER = 0b101
IMOD = 0b110

DATUM_BYTES_N = 4


class InstructionWord(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [("CMD", ctypes.c_uint32, 3),
                ("IM", ctypes.c_uint32, 1),
                ("DELAY", ctypes.c_uint32, 12),
                ("REG", ctypes.c_uint32, 6),
                ("SHIFT", ctypes.c_uint32, 5),
                ("WIDTH", ctypes.c_uint32, 5)]

    def __str__(self):
        return '\n'.join(['{}: {}'.format(i[0], getattr(self, i[0])) for i in self._fields_])


class Command(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [("INSTRUCTION", InstructionWord),
                ("DATUM", ctypes.c_uint32)]

    def __str__(self):
        return self.INSTRUCTION.__str__() + '\nDATUM: 0x{:08X}'.format(self.DATUM)

    @property
    def instr(self):
        return int.from_bytes(self.INSTRUCTION, 'big')

    @property
    def datum(self):
        return self.DATUM


class BlockCommit(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [("INSTRUCTION", InstructionWord),
                ("N", ctypes.c_uint32, 6),
                ("RESERVED", ctypes.c_uint32, 26)]

    def __str__(self):
        return self.INSTRUCTION.__str__() + '\nN: {}'.format(self.N)

    @property
    def instr(self):
        return int.from_bytes(self.INSTRUCTION, 'big')

    @property
    def datum(self):
        return (self.N << 26) | self.RESERVED


def nop():

    cmd = Command()
    cmd.INSTRUCTION.CMD = NOP

    return cmd

def updt(reg, im, delay):

    cmd = Command()
    cmd.INSTRUCTION.CMD = UPDT
    cmd.INSTRUCTION.REG = reg
    cmd.INSTRUCTION.IM = im
    cmd.INSTRUCTION.DELAY = delay

    return cmd

def mod(reg, shift, width, datum):

    cmd = Command()
    cmd.INSTRUCTION.CMD = MOD
    cmd.INSTRUCTION.REG = reg
    cmd.INSTRUCTION.SHIFT = shift
    cmd.INSTRUCTION.WIDTH = width
    cmd.DATUM = datum

    return cmd

def imod(reg, shift, width, datum):

    cmd = Command()
    cmd.INSTRUCTION.CMD = IMOD
    cmd.INSTRUCTION.REG = reg
    cmd.INSTRUCTION.SHIFT = shift
    cmd.INSTRUCTION.WIDTH = width
    cmd.DATUM = datum

    return cmd

def cmt(reg, im, delay):

    cmd = Command()
    cmd.INSTRUCTION.CMD = CMT
    cmd.INSTRUCTION.REG = reg
    cmd.INSTRUCTION.IM = im
    cmd.INSTRUCTION.DELAY = delay

    return cmd

def cblk(reg, n, delay, im):

    cmd = BlockCommit()
    cmd.INSTRUCTION.CMD = CBLK
    cmd.INSTRUCTION.REG = reg
    cmd.INSTRUCTION.IM = im
    cmd.INSTRUCTION.DELAY = delay
    cmd.N = n

    return cmd

def ver(reg, im ,delay, shift, width, datum):

    cmd = Command()
    cmd.INSTRUCTION.CMD = VER
    cmd.INSTRUCTION.IM = im
    cmd.INSTRUCTION.DELAY = delay
    cmd.INSTRUCTION.REG = reg
    cmd.INSTRUCTION.SHIFT = shift
    cmd.INSTRUCTION.WIDTH = width
    cmd.DATUM = datum

    return cmd
