#####################
# POWER OFF THE BEE #
#####################

import time

# note: need no ARM command for power-off

# switch OFF the OTA Output (also necessary for heaters)
ccs.CnCsend('TC_CSR_P28V_OTA_N_OFF')
time.sleep(1)

# switch OFF the BEE Heater Output power supply [NOMINAL]
ccs.CnCsend('TC_CSR_PSH_OFF')
time.sleep(1)

# switch OFF the BEE power supply [NOMINAL]
ccs.CnCsend('TC_CSR_PSN_OFF')


