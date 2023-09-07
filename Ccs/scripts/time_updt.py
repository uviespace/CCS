# Periodically send a PUS TC(9,128) time update packet in a background task

import threading

def timetick(period):
    global t_updt
    print('START TIMETICK')
    while t_updt:
        ObtTime = cfl.get_cuc_now()
        cfl.Tcbuild('SASW TimeUpdt', ObtTime, pool_name='LIVE', ack=0, sleep=period)
    print('STOP TIMETICK')


PERIOD = 1  # time tick period in seconds

t_updt = True
t = threading.Thread(target=timetick, args=[PERIOD])
t.start()

#! CCS.BREAKPOINT
t_updt = False