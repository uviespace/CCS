#--------------------------------------------
# Name: PltfEvts
# Title: Generation of Platform Events
# Author: PnP
#--------------------------------------------

# Description: Use command Evt:TrigEvt to trigger power-off and power-cycle events
#              and verify instrument response to power-off and power-cycle commands 
#              by the platform 

# Precondition: Instrument under ASW control in a mode where sudden switch-off 
#               is not harmful; BSW configured for autonomous transition to ASW; 
#               and mission phase set to 'not encounter' 

#--------------------------------------------
# STEP 100 - Generate Power-Cycle Request Event
# Use command Evt:TrigEvt to request the generation of event Gen:EVT_POWER_CYC 
TBD Command

# VERIFY that Asw:PrepFastOff is received from the platform and then instrument 
#        is switched off by the platform
# VERIFY that Instrument is switched back on by the platform 
# VERIFY that instrument is under ASW control and HkBasicAswRep is generated
# VERIFY that instrument is in STANDBY (CocOperationMode in HkBasicAswRep is
#        STANDBY
# VERIFY that a boot report TmBootRep is generated as part of the instrument 
#        start-up and its parameter CcaRstTypeRtIn is PLTFRM_PW_CYC

#--------------------------------------------
# STEP 200 - Check Event Log  
# Use FCP CometIntFcp:MngEvtLogCoc to request download of the last entry in 
# the Event Log and verify that it is equal to Gen:EVT_POWER_OFF
#
# NODE N6: Send TC(170,1) to request download of Event Log entries 1 to 2
L170001EvtLogSeqCntFirst = 1  # UCAH0136
L170001EvtLogSeqCntLast = 2  # UCAH0137
cfl.Tcsend_DB('L170001ReadEventLogRecs', L170001EvtLogSeqCntFirst, L170001EvtLogSeqCntLast, pool_name='LIVE')

# VERIFY that the first EventId in TmEventLogRecordRep is equal to the EID
#        for EVT_POWER_CYC

#--------------------------------------------
# STEP 500 - Generate Power-Off Request Event 
# Use command Evt:TrigEvt to request the generation of event Gen:EVT_POWER_OFF
# and verify that: command Asw:PrepFastOff is received from the platform and 
# then instrument is switched off by the platform 
TBD Command

