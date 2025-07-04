import crcmod
import ctypes


HEADER_VERSION = 0x01
FILLER = 0x00

N_SECT_HEADERS = 8
SECTION_HEADER_SIZE = 16
HEADER_SIZE = 8 + N_SECT_HEADERS * SECTION_HEADER_SIZE

MEM_MRAM_ID = 2
MEM_MRAM_START = 0x10000000
MEM_MRAM_SIZE = 0x200000

MEM_RAM_ID = 6
MEM_RAM_START = 0x40000000
MEM_RAM_SIZE = 0x1000000

ASW_IMG_OFFSET = 0x80000


puscrc = crcmod.predefined.mkPredefinedCrcFun('crc-ccitt-false')


class SectionHeaderFields(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [("TARGET_ADDR", ctypes.c_uint32),
                ("SIZE", ctypes.c_uint32),
                ("SOURCE_ADDR", ctypes.c_uint32),
                ("SOURCE_SECT_ID", ctypes.c_uint8),
                ("FILLER", ctypes.c_uint8),
                ("CRC16", ctypes.c_uint16)]


class ImageHeaderFields(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = [("HEADER_CRC16", ctypes.c_uint16),
                ("HEADER_VERSION", ctypes.c_uint8),
                ("FILLER", ctypes.c_uint8),
                ("ENTRY_POINT", ctypes.c_uint32),
                ("SECTION1", SectionHeaderFields),
                ("SECTION2", SectionHeaderFields),
                ("SECTION3", SectionHeaderFields),
                ("SECTION4", SectionHeaderFields),
                ("SECTION5", SectionHeaderFields),
                ("SECTION6", SectionHeaderFields),
                ("SECTION7", SectionHeaderFields),
                ("SECTION8", SectionHeaderFields)]


class ImageHeader(ctypes.Union):
    _pack_ = 1
    _fields_ = [("fields", ImageHeaderFields),
                ("bin", ctypes.c_ubyte * HEADER_SIZE)]
    
    def __init__(self, memid, entrypoint, data, data_addr_offset=HEADER_SIZE):
        
        super().__init__()
    
        self.fields.HEADER_VERSION = HEADER_VERSION
        self.fields.FILLER = FILLER
        self.fields.ENTRY_POINT = entrypoint

        self.set_section(1, data, entrypoint, MEM_MRAM_START + ASW_IMG_OFFSET + data_addr_offset, memid)

        self.fields.HEADER_CRC16 = puscrc(bytes(self.bin[2:]))

    def set_section(self, n, data, target_addr, source_addr, memid):

        sect = getattr(self.fields, "SECTION{}".format(n))
        sect.TARGET_ADDR = target_addr
        sect.SOURCE_ADDR = source_addr
        sect.SOURCE_SECT_ID = memid

        # assert len(data) % 4 == 0

        sect.SIZE = len(data)
        sect.CRC16 = puscrc(data)


class AswImage:

    def __init__(self, memid, entrypoint, aswfile, skip_bytes=0):

        assert isinstance(aswfile, str)

        data = open(aswfile, 'rb').read()[skip_bytes:]

        self.header = ImageHeader(memid, entrypoint, data)
        self.data = data

    @property
    def img(self):
        return bytes(self.header) + self.data

    @property
    def size(self):
        """Total size of ASW image, including header"""
        return len(self.img)
