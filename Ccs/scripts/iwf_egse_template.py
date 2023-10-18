import communication as com
import iwf_egse as iwf

econ = com.Connector('', iwf.PORT, msgdecoding='ascii')
econ.connect()

def save_egse_tm(data, ts=None):
    if data.startswith(b'k'):
        htr=int(data[12:16].decode(),16)
        msg='{}\t{}\t{}({:.3f} V)\n'.format(ts, data.decode(),htr,htr/4095*5)
    else:
        msg='{}\t{}'.format(ts, data.decode())
    return msg

econ.start_receiver(procfunc=save_egse_tm, outfile='egselog.dat')

econ.send(iwf.Command.get_status(), rx=False)
econ.send(iwf.Command.set_psu_ok_signal(1,1), rx=False)  # set IWF_EGSE_PSU_OK = 1
econ.send(iwf.Command.set_psu_ok_signal(3,1), rx=False)  # set IWF_EGSE_RSE_OK = 1
econ.send(iwf.Command.set_psu_ok_signal(4,1), rx=False)  # set IWF_EGSE_PIN_PULL_OK = 1
econ.send(iwf.Command.set_rsm_end_switch(1,1), rx=False)  # set IWF_EGSE_CLOSE_POS = 1; response 'R7' -> only for EBOX
econ.send(iwf.Command.set_psu_analogue_value(iwf.Signal.EGSE_I_HEATER, 2000), rx=False)  # set IWF_EGSE_I_HEATER
econ.send(iwf.Command.set_pwm(2, 1663), rx=False)  # set CCD Thermistor

econ.send(iwf.Command.inject_errors(6,0,3,0,11,0), rx=False)  # inject RSE error

import time
cfl.Tcsend_DB('SASW ModHkPeriodCmd', 101, 1, pool_name='LIVE')
for i in range(0,4001,1):
    t=time.time()
    econ.send(iwf.Command.set_pwm(2, i), rx=False)
    print(i,t)
    time.sleep(1-(time.time()-t))
econ.send(iwf.Command.set_pwm(2, 0), rx=False)
cfl.Tcsend_DB('SASW ModHkPeriodCmd', 101, 40, pool_name='LIVE')

for i in range(1,5):
    econ.send(iwf.Command.set_psu_analogue_value(i, 0), rx=False)
