"""Template for uploading the ASW binary to ARIEL DPU"""

import Ccs.tools.asw_upload.asw_image_lib_ariel as ail

#POOLNAME = "FCUn"
asw_path = "/home/marko/space/ariel/asw_images/ariel_fgs_asw_v1.1.5.elf"

#! CCS.BREAKPOINT
memid = 18  # memory ID
start_addr = 0x40000000  # start address/entry point of ASW in RAM
asw = ail.AswImage(memid, start_addr, asw_path, skip_bytes=65536)

#! CCS.BREAKPOINT
# write image to file
open(asw_path + '.img', 'wb').write(asw.img)
cfl.source_to_srec(asw.img, asw_path + '.img.srec', 0x10080000, bytes_per_line=64)  # write SREC file

cfl.Tcsend_DB('BSW_DisableWritePro', 18, no_check=True,pool_name=POOLNAME)
#! CCS.BREAKPOINT
mem_addr = 0x10080000  # address where the data is uploaded to (ail.MEM_MRAM_START + ail.ASW_IMG_OFFSET)
cfl.load_to_memory(asw.img, memid, mem_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)
print('IMG SIZE: ', asw.size)
print('IMG CRC: ', cfl.crc(asw.img))

cfl.Tcsend_DB('BSW_EnableWriteProt', 18, no_check=True,pool_name=POOLNAME)
#! CCS.BREAKPOINT
MemoryID16 = 18  # JA0H0124
# N = 1  # JA0H0042 [NOT EDITABLE]
StartAddress = mem_addr  # JA0H0125
Length = asw.size  # JA0H0123
cfl.Tcsend_DB('BSW_CheckMemData', MemoryID16, StartAddress, Length, no_check=True,pool_name=POOLNAME)
