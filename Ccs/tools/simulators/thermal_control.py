"""
SMILE PI thermal control algorithm, Python implementation
"""

import numpy as np
import time
import threading


def vctrl_ana_to_dig(v):
    return int(v * 1024 / 3.3)


class ThermalController:

    ASW_PERIOD_MS = 125.

    VCTRLLOWERVOLT = 0.4
    VCTRLUPPERVOLT = 2.8
    MAXDELTAVOLTAGE = 0.2

    def __init__(self, temp_ref, coeffP, coeffI, offset, exec_per, model=None, pi=True, deltaTmax=1.):

        self.tempRef = temp_ref
        self.coeffP = coeffP
        self.coeffI = coeffI
        self.offset = offset

        self.temp = temp_ref
        self.voltCtrl = self.VCTRLLOWERVOLT
        self.voltCtrlUint16 = vctrl_ana_to_dig(self.voltCtrl)

        self.tempOld = temp_ref
        self.integOld = 0
        self.voltCtrlOld = self.VCTRLLOWERVOLT

        self.hctrl_par_exec_per = exec_per
        self._algo_active = False

        if pi:
            self.calc_vctrl = self.do_pi_vctrl
        else:
            self.calc_vctrl = self.on_off_vctrl

        self.deltaTmax = deltaTmax

        self.model = model
        self.log = []

        self._thread = None

    def set_temp_ref(self, temp):
        self.tempRef = temp

    def do_pi_vctrl(self, temp):

        deltaTime = self.hctrl_par_exec_per * self.ASW_PERIOD_MS / 1000
        integ = self.integOld + deltaTime * (self.tempRef - self.tempOld)
        voltCtrlRel = self.offset + self.coeffP * (self.tempRef - temp) + self.coeffI * integ

        if voltCtrlRel < 0:
            self.voltCtrl = self.VCTRLLOWERVOLT
        elif voltCtrlRel > 100:
            self.voltCtrl = self.VCTRLUPPERVOLT
        else:
            self.voltCtrl = self.VCTRLLOWERVOLT + (voltCtrlRel / 100) * (self.VCTRLUPPERVOLT - self.VCTRLLOWERVOLT)

        if (self.voltCtrl - self.voltCtrlOld) > self.MAXDELTAVOLTAGE:
            self.voltCtrl = self.voltCtrlOld + self.MAXDELTAVOLTAGE
        elif (self.voltCtrlOld - self.voltCtrl) > self.MAXDELTAVOLTAGE:
            self.voltCtrl = self.voltCtrlOld - self.MAXDELTAVOLTAGE

        self.tempOld = temp
        self.integOld = integ
        self.voltCtrlOld = self.voltCtrl

        self.voltCtrlUint16 = vctrl_ana_to_dig(self.voltCtrl)

    def on_off_vctrl(self, temp):

        if temp > self.tempRef + self.deltaTmax:
            v = self.voltCtrl - self.MAXDELTAVOLTAGE
        elif temp < self.tempRef - self.deltaTmax:
            v = self.voltCtrl + self.MAXDELTAVOLTAGE
        else:
            v = self.voltCtrl

        if v > self.VCTRLUPPERVOLT:
            self.voltCtrl = self.VCTRLUPPERVOLT
        elif v < self.VCTRLLOWERVOLT:
            self.voltCtrl = self.VCTRLLOWERVOLT
        else:
            self.voltCtrl = v

    def start_algo(self):

        if self._thread is not None and self._thread.is_alive():
            print('TTC algo already running')
            return

        self._thread = threading.Thread(target=self._algo_worker, name='TTCALGO')
        # self._thread.daemon = True
        self._algo_active = True
        self._thread.start()

    def _algo_worker(self):
        print('TTC algo started (period = {:.1f}s)'.format(self.ASW_PERIOD_MS / 1000 * self.hctrl_par_exec_per))
        while self._algo_active:
            try:
                t1 = time.time()

                if self.model is not None:
                    self._step(t1, with_model=True)

                else:
                    self._step(t1, with_model=False)

                dt = (self.ASW_PERIOD_MS / 1000 * self.hctrl_par_exec_per) - (time.time() - t1)
                if dt > 0:
                    time.sleep(dt)

            except Exception as err:
                print(err)
                self.stop_algo()

        print('TTC algo stopped')

    def _step(self, t1, with_model=True, glitch=0):
        if with_model:
            self.temp = self.model.T_noisy + glitch
            self.calc_vctrl(self.temp)
            self.model.set_heater_power(vctrl=self.voltCtrl)

            self.log.append((t1, self.tempRef, self.temp, self.voltCtrl, self.coeffI * self.integOld, self.coeffP * (self.tempRef - self.temp)))
            
        else:
            self.calc_vctrl(self.temp)

    def stop_algo(self):
        self._algo_active = False

    def save_log(self, fname):
        np.savetxt(fname, np.array(self.log), header='time\tT_ref\tT\tV_ctrl\tcI*integ\tcP*(T_ref-T)')

