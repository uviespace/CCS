"""
Upload ARIEL FGS SIDECAR firmware and personality files
"""

memid = 18
cfl.Tcsend_DB('BSW_DisableWritePro', memid, no_check=True, pool_name=POOLNAME)

#! CCS.BREAKPOINT
# FW and personality files
fw_A = open('/home/marko/space/ariel/SIDECAR/Case_Main.mcd', 'rb').read()
pers_A = open('/home/marko/space/ariel/SIDECAR/DCL_CASE_tuning/FPM_EM1_CASE_tuning.glf', 'rb').read()
fw_B = fw_A  # no separate fw yet?
pers_B = open('/home/marko/space/ariel/SIDECAR/DCL_CASE_tuning/FPM_EM2_CASE_tuning.glf', 'rb').read()

# addresses in MRAM, according to BSW ICD
fw_A_addr = 0x10018000
pers_A_addr = 0x10027000
fw_B_addr = 0x10028000
pers_B_addr = 0x10037000

#! CCS.BREAKPOINT
# upload
cfl.load_to_memory(fw_A, memid, fw_A_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

cfl.load_to_memory(pers_A, memid, pers_A_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

cfl.load_to_memory(fw_B, memid, fw_B_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

cfl.load_to_memory(pers_B, memid, pers_B_addr, max_pkt_size=1024, progress=True, calc_crc=True, byte_align=4, pool_name=POOLNAME,tcname="BSW_LoadMemData",sleep=.25)

#! CCS.BREAKPOINT
cfl.Tcsend_DB('BSW_EnableWriteProt', memid, no_check=True, pool_name=POOLNAME)

