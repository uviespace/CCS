#--------------------------------------------
# Name: StartAsw
# Title: Transition from BSW to ASW 
# Author: PnP
#--------------------------------------------
#
# Description: Command loading and start of ASW both directly from BSW and 
#              indirectly through a BSW reset and perform basic checks on 
#              ASW operation in STANDBY 
#
# Precondition: Instrument under BSW control configured as follows:
#               (a) Automatic start of ASW disabled
#               (b) Mission phase set to 'not encounter'  

#--------------------------------------------
# STEP 100 - Trigger Direct Transition to ASW
# Run FCP CometIntFcp:StartAswCoc to trigger direct transition into ASW 
# using the 'fallback' ASW image 
#
# NODE N1: Send TC(160,11) with FORCED set to False and with IMAGE set either 
# to 'Fallback' or 'Custom'
L160011SwImageId = FALLBACK  # UCAH0079
L160011ForceBoot = False  # UCAH0080
cfl.Tcsend_DB('L160011BootAsw', L160011SwImageId, L160011ForceBoot, pool_name='LIVE')

# NODE N2: Verify that event report EVT_ASW_READY is generated
# VERIFY that event EID 22000 is generated

#--------------------------------------------
# STEP 200 - Basic ASW Telemetry Checks
# VERIFY in HkAswBasicRep that:
#        (a) The ASW is in STANDBY Mode (CocOperationMode is STANDBY)
#        (b) The synchronization word in the TM Secondary Header (TIMESYNC) indicates
#            that the instrument is synchronized and the time-stamp is consistent
#            with the platform time
#        (c) The default telemetry packet HkAswBasicRep is generated with period 
#            as given in configuration parameter HkRdlPer
#        (e) The watchdog is enabled (LowWdEnabled is ENABLED in HkBswBasicRep)
#        (f) All error counters in HkBswBasicRep are set to zero (FdScrubDbeNmb,
#            FdScrubSbeNmb, Ver*Fail*, Mon*Err
#        (g) The SID of the periodically generated HkAswBasicRep packet is 7002
#        (h) The sensor state machines are in the OFF state (CsuMode is OFF)
# VERIFY that event Gen:EVT_ASW_TR (EID 22020) has been generated to report entry 
#        in STANDBY (MOdePrev is INVALID and ModeNew is STANDBY)

#--------------------------------------------
# STEP 220 - Verify Configuration Parameters
# Run FCP CometIntFcp:PersConfigPars and verify that CRC of configuration parameters
# in RAM is the same as CRC of configuration parameters in persistent memory 
#
# NODE N11: Send TC(166,24) to compute the CRC of configuration parameters in RAM
L166024ParamInstance = TBD (See Mantis 729)  # UCAH0084
cfl.Tcsend_DB('L166024RepCfgParamsCrc', L166024ParamInstance, pool_name='LIVE')

# NODE N12: Send TC(166,24) to compute the CRC of configuration parameters in 
#           persistent memory
L166024ParamInstance = TBD (See Mantis 729)  # UCAH0084
cfl.Tcsend_DB('L166024RepCfgParamsCrc', L166024ParamInstance, pool_name='LIVE')

# VERIFY that the CRCs reported at the previous two steps are identical

#--------------------------------------------
# STEP 230 - Report Context Data 
# Run FCP CometIntFcp:MngContextData to report context data and verify that their 
# values are as expected at ASW start-up 
#
# NODE N1: Send TC(166,21) to ask for a report carrying a copy of all context 
# data in both RAM and persistent memory 
cfl.Tcsend_DB('L166021RepCtx', pool_name='LIVE')

# NODE N7: Inspect values of context data in TM(166,22) triggered by command of 
#          node N1

#--------------------------------------------
# STEP 250 - Basic Heartbeat Generation Check  
# VERIFY that report HbRep is generated with period HbPeriod 
# VERIFY that successive instances of HbRep carry alternating values of 
#        HbToggleD1 and HbToggleD2

#--------------------------------------------
# STEP 300 - Perform Connection Test
# Same as step 400 of BasicBsw

#--------------------------------------------
# STEP 350 - Telemetry Jitter and Sequence Counters 
# Same as step 700 of BasicBsw

#--------------------------------------------
# STEP 400 - Trigger ASW Reset 
# Run FCP CometIntFcp:ResetInst 
TBD (TC(166,7) is missing from IRDB, see Mantis 703)

# VERIFY that, after the reset:
#         (a) The instrument enters MAINTENANCE Mode (CoCOperationMode is
#             MAINTENANCE)
#         (b) Event EVT_BSW2_READY (EID 22005) is generated
#         (c) The event parameters indicate that the instrument is running on
#             the custom BSW_2 image (BswImageType is CUSTOM_L)

#--------------------------------------------
# STEP 420 - Trigger Boot Report And Check Reset Type 
# Use FCP CometIntFcp:TrigBootRep to request a boot report and, in the boot
# report, verify that instrument was reset 
cfl.Tcsend_DB('L170010GenBootRep', pool_name='LIVE')

# VERIFY that TM(170,11) TmBootRep is generated within 100 ms of TC(170,10)
# VERIFY that the reset type information in the boot report is consistent 
#        with the instrument having been reset (i.e. RstTypeRtIn is equal
#        to TBD, see Mantis 731)

#--------------------------------------------
# STEP 450 - Trigger Indirect Transition to ASW
# Run FCP CometIntFcp:StartAswCoc to trigger indirect transition into ASW 
#
# NODE N7: Send TC(166,30) to set:
#          Autoboot Flag to True,
#          Fast Boot Flag to False,
#          BSW_2 and ASW image pointers to 'fallback'
L166030FastBootFl = False  # UCAH0089
L166030AutoBootFlDef = True  # UCAH0090
L166030MissionPhaseFlDef = NOT_ENCOUNTER  # UCAH0091
L166030SwImgTagBswNext = FALLBACK  # UCAH0092
L166030SwImgTagBswDef = FALLBACK  # UCAH0093
L166030SwImgTagAswNext = FALLBACK  # UCAH0094
L166030SwImgTagAswDef = FALLBACK  # UCAH0095
cfl.Tcsend_DB('L166030SetBootMode', L166030FastBootFl, L166030AutoBootFlDef, L166030MissionPhaseFlDef, L166030SwImgTagBswNext, L166030SwImgTagBswDef, L166030SwImgTagAswNext, L166030SwImgTagAswDef, pool_name='LIVE')

# NODE N5: Switch off instrument

# NODE N6: Switch on instrument

# NODE N2: Verify that event report EVT_ASW_READY is generated
# VERIFY that event EID 22000 is generated

#--------------------------------------------
# STEP 500 - Basic ASW Telemetry Check
# Same as step 200






