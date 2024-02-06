#--------------------------------------------
# Name: ServHb
# Title: Heartbeat Service Operation
# Author: PnP
#--------------------------------------------
#
# Description: Verify generation and configuration of heartbeat reports 
#
# Precondition: Instrument in an ASW-based mode 

#--------------------------------------------
# STEP 100 - Heartbeat Report Period and Content 
# VERIFY that:
#           (a) The heartbeat report HbRep is generated with period 
#               as given in configuration parameter HbPeriod
#           (b) The heartbeat report HbRep carries the current ASW 
#               Mode in parameter AswMode
#           (c) The toggle word in HbRep changes between HbToggleD1
#               and Hb:ToggleD2
# Make a note of the current Heartbeat Report Period

#--------------------------------------------
# STEP 200 - Heartbeat Report Disabling
# Use CometIntFcp:UpdConfigPars to set Hb:Period to zero
# NODE N1: Send TC(20,3) to update the values of the target configuration parameters
L020003NumOfParams = 1  # UCAH0054
L020003ParamId = 'HbPeriod'  # UCAH0055
L020003OnbParamVal = 0  # UCAH0056
cfl.Tcsend_DB('L020003SetParamValues', L020003NumOfParams, L020003ParamId, L020003OnbParamVal, pool_name='LIVE')

# NODE N2: Send TC(20,1) to download the values of the configuration parameters 
#          updated in node N1
L020001NumOfParams = 1  # UCAH0052
L020001ParamId = 'HbPeriod'  # UCAH0053
cfl.Tcsend_DB('L020001RepParamValues', L020001NumOfParams, L020001ParamId, pool_name='LIVE')

# NODE N3: Verify in TM(20,2) that the values of the updated configuration parameters
#          are as expected
# VERIFY that OnbParamVal in TM(20,2) is equal to 0

# VERIFY that generation of the heartbeat report ceases

#--------------------------------------------
# STEP 300 - Non-Nominal Heartbeat Period
# Use CometIntFcp:UpdConfigPars to set Hb:Period to twice its default value
# (the default value was read at step 100)
# NODE N1: Send TC(20,3) to update the values of the target configuration parameter
L020003NumOfParams = 1  # UCAH0054
L020003ParamId = 'HbPeriod'  # UCAH0055
L020003OnbParamVal = 2*DefaultHbPeriod  # UCAH0056
cfl.Tcsend_DB('L020003SetParamValues', L020003NumOfParams, L020003ParamId, L020003OnbParamVal, pool_name='LIVE')

# NODE N2: Send TC(20,1) to download the values of the configuration parameters 
#          updated in node N1
L020001NumOfParams = 1  # UCAH0052
L020001ParamId = 'HbPeriod'  # UCAH0053
cfl.Tcsend_DB('L020001RepParamValues', L020001NumOfParams, L020001ParamId, pool_name='LIVE')

# NODE N3: Verify in TM(20,2) that the values of the updated configuration parameters
#          are as expected
# VERIFY that OnbParamVal in TM(20,2) is equal to the value set at node N1

# VERIFY that frequency of generation of the heartbeat report halves

# Use UCometIntFcp:UpdConfigPars to reset Hb:Period to its default value 
#(default value is read at step 100)
# NODE N1: Send TC(20,3) to update the values of the target configuration parameters
L020003NumOfParams = 1  # UCAH0054
L020003ParamId = 'HbPeriod'  # UCAH0055
L020003OnbParamVal = defaultHbPeriod  # UCAH0056
cfl.Tcsend_DB('L020003SetParamValues', L020003NumOfParams, L020003ParamId, L020003OnbParamVal, pool_name='LIVE')

# NODE N2: Send TC(20,1) to download the values of the configuration parameters 
#          updated in node N1
L020001NumOfParams = 1  # UCAH0052
L020001ParamId = 'HbPeriod'  # UCAH0053
cfl.Tcsend_DB('L020001RepParamValues', L020001NumOfParams, L020001ParamId, pool_name='LIVE')

# NODE N3: Verify in TM(20,2) that the values of the updated configuration parameters
#          are as expected
# VERIFY that OnbParamVal in TM(20,2) is equal to value set at node N1

#--------------------------------------------
# STEP 400 - Non-Nominal Toggle Values 
# (a) Use CometIntFcp:UpdConfigPars to set Hb:ToggleD1 to 0x1111 and Hb:ToggleD2 to 0x2222
# NODE N1: Send TC(20,3) to update the values of the target configuration parameters
L020003NumOfParams = 2  # UCAH0054
L020003ParamId1 = 'HbToggleD1'  # UCAH0055
L020003OnbParamVal1 = 0x1111  # UCAH0056
L020003ParamId2 = 'HbToggleD2'  # UCAH0055
L020003OnbParamVal2 = 0x2222  # UCAH0056
cfl.Tcsend_DB('L020003SetParamValues', L020003NumOfParams, L020003ParamId1, L020003OnbParamVal1, L020003ParamId2, L020003OnbParamVal2, pool_name='LIVE')

# NODE N2: Send TC(20,1) to download the values of the configuration parameters 
#          updated in node N1
L020001NumOfParams = 2 # UCAH0052
L020001ParamId1 = 'HbToggleD1'  # UCAH0053
L020001ParamId2 = 'HbToggleD2'  # UCAH0053
cfl.Tcsend_DB('L020001RepParamValues', L020001NumOfParams, L020001ParamId1, L020001ParamId2, pool_name='LIVE')

# NODE N3: Verify in TM(20,2) that the values of the updated configuration parameters
#          are as expected
# VERIFY that OnbParamVal's in TM(20,2) is equal to value set at node N1
# VERIFY that the heartbeat report carries the new toggle values

# Use Update Configuration Parameter FCP to restore the nominal values of DataItem:Hb:ToggleD1 and Hb:ToggleD2
# NODE N1: Send TC(20,3) to update the values of the target configuration parameters
L020003NumOfParams = 2  # UCAH0054
L020003ParamId1 = 'HbToggleD1'  # UCAH0055
L020003OnbParamVal1 = 0xA5A5  # UCAH0056
L020003ParamId2 = 'HbToggleD2'  # UCAH0055
L020003OnbParamVal2 = 0x5A5A  # UCAH0056
cfl.Tcsend_DB('L020003SetParamValues', L020003NumOfParams, L020003ParamId1, L020003OnbParamVal1, L020003ParamId2, L020003OnbParamVal2, pool_name='LIVE')

# NODE N2: Send TC(20,1) to download the values of the configuration parameters 
#          updated in node N1
L020001NumOfParams = 2  # UCAH0052
L020001ParamId1 = 'HbToggleD1'  # UCAH0053
L020001ParamId2 = 'HbToggleD2'  # UCAH0053
cfl.Tcsend_DB('L020001RepParamValues', L020001NumOfParams, L020001ParamId1, L020001ParamId2, pool_name='LIVE')

# NODE N3: Verify in TM(20,2) that the values of the updated configuration parameters
#          are as expected
# VERIFY that OnbParamVal's in TM(20,2) are equal to values set at node N1
# VERIFY that the heartbeat report carries the default toggle values



