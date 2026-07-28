"""
Upload ARIEL FGS SIDECAR firmware and personality files
"""

import subprocess

def mk_fw_hdr(binary):
    size = len(binary)
    chksum = cfl.crc(binary)
    return size.to_bytes(2, 'big') + chksum.to_bytes(2, 'big')

# FW and personality files
fw_A_src = '/home/marko/space/ariel/SIDECAR/Case_Main.mcd'
fw_B_src = fw_A_src
pers_A_src = '/home/marko/space/ariel/SIDECAR/DCL_CASE_tuning/FPM_EM1_CASE_tuning.glf'
pers_B_src = '/home/marko/space/ariel/SIDECAR/DCL_CASE_tuning/FPM_EM2_CASE_tuning.glf'

# generate binary images for MRAM
awk_script = '/home/marko/space/ariel/FSW/software/util/gen_firmware_img.awk'
fw_A = subprocess.run([f"awk -f {awk_script} {fw_A_src} | xxd -r -p"], shell=True, capture_output=True, check=True).stdout
fw_B = fw_A = subprocess.run([f"awk -f {awk_script} {fw_B_src} | xxd -r -p"], shell=True, capture_output=True, check=True).stdout
pers_A = subprocess.run([f"awk -f {awk_script} <(grep -v ASIC_MODE {pers_A_src}) | xxd -r -p"], shell=True, capture_output=True, check=True).stdout
pers_B = subprocess.run([f"awk -f {awk_script} <(grep -v ASIC_MODE {pers_B_src}) | xxd -r -p"], shell=True, capture_output=True, check=True).stdout

# save binary images
#open(fw_A_src[:-4] + '.bin', 'wb').write(fw_A)
#open(fw_B_src[:-4] + '.bin', 'wb').write(fw_B)
#open(pers_A_src[:-4] + '.bin', 'wb').write(pers_A)
#open(pers_B_src[:-4] + '.bin', 'wb').write(pers_B)

#! CCS.BREAKPOINT
memid = 18
cfl.Tcsend_DB('BSW_DisableWritePro', memid, no_check=True, pool_name=POOLNAME)

# addresses in MRAM, according to BSW ICD
fw_A_addr = 0x10018000
pers_A_addr = 0x10027000
fw_B_addr = 0x10028000
pers_B_addr = 0x10037000

#! CCS.BREAKPOINT
# create headers and upload
cfl.load_to_memory(mk_fw_hdr(fw_A) + fw_A, memid, fw_A_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

cfl.load_to_memory(mk_fw_hdr(fw_B) + fw_B, memid, fw_B_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

cfl.load_to_memory(mk_fw_hdr(pers_A) + pers_A, memid, pers_A_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

cfl.load_to_memory(mk_fw_hdr(pers_B) + pers_B, memid, pers_B_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

#! CCS.BREAKPOINT
cfl.Tcsend_DB('BSW_EnableWriteProt', memid, no_check=True, pool_name=POOLNAME)

