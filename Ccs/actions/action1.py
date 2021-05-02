# Prologue
#if (('initialization' not in dir()) or (initialization != "DB")) :
#    exec(open('../acceptance_tests/v0.5/TestSetup_DB_05.py').read())

import time


#ccs.CnCsend('TC_CSR_OTA_S_HTR_N_ILIM 0.3')
#ccs.CnCsend('TC_OTA_S_HTR_N_SET_MODE 0')

##############################
# allow several heater lines #
##############################

#ccs.CnCsend('TC_CSR_OTA_S_HTR_N_ON')
ccs.CnCsend('TC_CSR_FEE_S_HTR_N_ON')
#ccs.CnCsend('TC_CSR_FPA_S_HTR_N_ON')
#ccs.CnCsend('TC_CSR_FPA_ANN_HTR_N_ON')

####################
# POWER ON THE BEE #
####################

# LCL/ARM the BEE power supply
ccs.CnCsend('TC_CSR_PS_ARM')
time.sleep(1)

# set BEE PSN OVP and Voltage
ccs.CnCsend('TC_CSR_PSN_OVP 32.0')
ccs.CnCsend('TC_CSR_PSN_VSET 31.0')

# switch ON the BEE power supply [NOMINAL]
ccs.CnCsend('TC_CSR_PSN_ON')
time.sleep(0.5)

# set heater PS OCP limit
ccs.CnCsend('TC_CSR_PSH_OVP 32.0')
ccs.CnCsend('TC_CSR_PSH_ILIM 2.0')
ccs.CnCsend('TC_CSR_PSH_VSET 31.0')

# switch ON the BEE Heater Output power supply [NOMINAL]
ccs.CnCsend('TC_CSR_PSH_ON')
time.sleep(0.5)

# set ILIM of OTA Output to 0.5 (default is 0.2)
ccs.CnCsend('TC_CSR_P28V_OTA_N_ILIM 2.0')
time.sleep(0.25)

# switch ON the OTA Output (also necessary for heaters)
ccs.CnCsend('TC_CSR_P28V_OTA_N_ON')
time.sleep(1)


#########################
# SEND THE BEE ON PULSE #
#########################

# ARM the SHP pulse
ccs.CnCsend('TC_CSR_SHP_ARM 1')
time.sleep(0.5)

# activate BEE [NOMINAL] via SHP output
ccs.CnCsend('TC_CSR_BEE_ON_N')

# DISARM the SHP pulse
# ccs.CnCsend('TC_CSR_SHP_ARM 0',socket_name='TC')
