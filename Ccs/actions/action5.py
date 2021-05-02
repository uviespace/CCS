# boot image previously saved in flash
patchdestaddr = 0x00100000
startflash = 'DPU_FLASH1' 
ccs.Tcsend_DB('DPU_DBS_TC_BOOT_IASW',startflash,patchdestaddr,0x40480000,b'12345678901234567890',ack='0b1011') 

print("Starting image at", startflash, str(hex(patchdestaddr)))
