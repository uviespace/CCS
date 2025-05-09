"""Template for uploading the ASW binary to ARIEL DPU"""

import Ccs.tools.asw_upload.asw_image_lib_ariel as ail

POOLNAME = "LIVE"
binary = "/home/marko/space/ariel/asw_images/flightos_v1.0b.elf"

#! CCS.BREAKPOINT
memid = 2  # memory ID
start_addr = 0x40000000  # start address/entry point of ASW in RAM
asw = ail.AswImage(memid, start_addr, binary, skip_bytes=65536)

#! CCS.BREAKPOINT
mem_addr = 0x80000  # address where the data is uploaded to (relative to base address of memid)
cfl.load_to_memory(asw.img, memid, mem_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME)

#! CCS.BREAKPOINT
MemoryID16 = 'MRAM'  # JA0H0124
# N = 1  # JA0H0042 [NOT EDITABLE]
StartAddress = mem_addr  # JA0H0125
Length = asw.size  # JA0H0123
cfl.Tcsend_DB('SASW CheckMemData', MemoryID16, StartAddress, Length, pool_name=POOLNAME)
