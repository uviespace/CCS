# Template for uploading the IASW binary to DPU via SREC file

# convert the IASW binary to SREC format
binary = '/path/to/binary'  # IASW binary
srecfile = '/path/to/srec'  # SREC filename
start_addr = 0x60040000  # start address of IASW in RAM

cfl.source_to_srec(binary, srecfile, start_addr, skip_bytes=0)

# upload the SREC content to DPU
memid = 'MEM_WR_MRAM'  # memory ID, 'DPU_MRAM' or 'MEM_WR_MRAM', depending on whether DBS or IASW S6 is used
mem_addr = 0x40000000  # address where the data is uploaded to
segid = 0x200B0101  # ID for data segments, see DBS UM

cfl.upload_srec(srecfile, memid, mem_addr, segid, pool_name='LIVE', max_pkt_size=504, progress=True)  # optionally, provide the name of the TC that shall be used for upload, e.g., tcname='DBS_TC_LOAD_MEMORY'

#! CCS.BREAKPOINT
# upload the SREC content directly without segmentation
srecfile = '/path/to/srec'  # SREC filename
memid = 'EEPROM'
tc_cmd = 'SES CMD_Memory_Load'
dlen, dcrc = cfl.srec_direct(srecfile, memid, pool_name='LIVE', max_pkt_size=200, tcname=tc_cmd, sleep=0.125, byte_align=2)


#! CCS.BREAKPOINT
# The upload command will block the console while the packets are being sent. Run it in a thread to avoid that.
import threading

thread = threading.Thread(target=cfl.upload_srec, args=[srecfile, memid, mem_addr, segid], kwargs={'pool_name':'LIVE','max_pkt_size':504, 'progress':True})
thread.start()
