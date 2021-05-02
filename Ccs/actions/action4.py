############################
# TEST SCRIPT: LoadIasw    #
#         for: IFSW v0.9   #
#      script: v0.5        #
#      author: UVIE        #
############################

# note, the ifswpath (defined in TestSetup) must be valid
    
iasw = ifswpath + "CrIa/build/dpu/ifsw.srec"

msg = "The upload of the IASW will take about 1 minute."

ccs.report(box="IASW Upload", msg=msg)

#ccs.srectohex(fname=iasw, memid=0x0002, memaddr=0x40180000, segid=0x200B0101, tcsend="TC", linesperpack=61)
import threading
loader = threading.Thread(target=ccs.srectohex, kwargs={'fname':iasw, 'memid':0x0002, 'memaddr':0x40180000, 'segid':0x200B0101, 'tcsend':"LIVE", 'linesperpack':61})
loader.start()

#ccs.report(askbox="IASW Uploaded...", msg="Continue?", timestamp=ccs.tnow)
answer, comment = ccs.ask_dialog(title="IASW start", message="Please wait until the upload has completed.\n\nShall we start the IASW?")
if (answer) :
    ccs.Tcsend_DB('DPU_DBS_TC_BOOT_IASW','DPU_RAM',0x40180000,0x40480000,b'12345678901234567890',pool_name='LIVE')
    
