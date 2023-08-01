"""
Simple SMILE SXI thermal model for thermal control closed loop testing
"""

import threading
import time
import struct

import numpy as np
import communication as com
import iwf_egse as iwf
import calibrations_SMILE as cal

from ccs_function_lib import get_pool_rows, filter_rows

SIGMA_SB = 5.6703744191844314e-08
TZERO = 273.15

VCTRL_MIN = 0.4
VCTRL_MAX = 2.9
VHTR_MIN = 0.
VHTR_MAX = 14.

# linfit = np.polynomial.polynomial.Polynomial.fit((VCTRL_MIN, VCTRL_MAX), (VHTR_MIN, VHTR_MAX), 1)
# a0, a1 = linfit.convert().coef

rng = np.random.default_rng()


def ctok(t):
    return t + TZERO


def ktoc(t):
    return t - TZERO
    

def normalise(y):
    return (y - y.min()) / (y.max() - y.min())


def exp_norm(n, a, b):
    x = np.linspace(a, b, n)
    y = 1 - np.exp(1 / x)
    yn = normalise(y)
    return yn


def log_norm(n, a, b):
    x = np.linspace(a, b, n)
    y = np.log(x)
    yn = normalise(y)
    return yn


def sigmoid(n, a, b):
    x = np.linspace(-b, b, n)
    y = x / (1 + np.abs(x))
    yn = normalise(y)
    return yn


def heat_kernel(n, a, b):
    x = np.linspace(a, b, n)
    y = 1 / x * np.exp(-1 / (b*x))
    yn = normalise(y)
    return yn


def onoff(n, a, b):
    return np.array([0., 1.])


def cp_al(T):
    """
    Calculate specific heat capacity of Aluminium 6061-T6 at a given temperature between 4 an 300 K. From https://trc.nist.gov/cryogenics/materials/6061%20Aluminum/6061_T6Aluminum_rev.htm

    :param T: Temperature in Kelvin
    :return:
    """
    a = 46.6467
    b = -314.292
    c = 866.662
    d = -1298.3
    e = 1162.27
    f = -637.795
    g = 210.351
    h = -38.3094
    i = 2.96344

    return 10**(a+b*(np.log10(T)) + c*(np.log10(T))**2 + d*(np.log10(T))**3 + e*(np.log10(T))**4 + f*(np.log10(T))**5 + g*(np.log10(T))**6 + h*(np.log10(T))**7 + i*(np.log10(T))**8)


def k_al(T):
    """
    Calculate thermal conductivity of Aluminium 6061-T6 at a given temperature between 4 an 300 K. From https://trc.nist.gov/cryogenics/materials/6061%20Aluminum/6061_T6Aluminum_rev.htm

    :param T: Temperature in Kelvin
    :return:
    """
    a = 0.07918
    b = 1.0957
    c = -0.07277
    d = 0.08084
    e = 0.02803
    f = -0.09464
    g = 0.04179
    h = -0.00571
    i = 0

    return 10**(a+b*(np.log10(T)) + c*(np.log10(T))**2 + d*(np.log10(T))**3 + e*(np.log10(T))**4 + f*(np.log10(T))**5 + g*(np.log10(T))**6 + h*(np.log10(T))**7 + i*(np.log10(T))**8)


def vctrl_to_vhtr(vctrl):
    """
    Calculate heater voltage from control voltage; linear behaviour

    :param vctrl:
    :return:
    """

    if vctrl < VCTRL_MIN:
        return VHTR_MIN
    elif vctrl > VCTRL_MAX:
        return VHTR_MAX
    else:
        return ((vctrl - VCTRL_MIN) / (VCTRL_MAX - VCTRL_MIN)) * (VHTR_MAX - VHTR_MIN)


class ThermalModel:

    sigma_T = 0.001  # relative noise of T reading (Gaussian)

    htr_eff = 0.95  # heater efficiency
    R_htr = 22.75  # heater resistance [Ohm]
    epsilon = 0.9  # emissivity of radiator
    # cp = 800.  # specific heat capacity of radiator [J/kg/K]
    mass = 3.  # radiator thermal mass [kg] (500x500x~4mm) 2700kg/m³
    rad_area = 0.25  # effective radiator area [m²]
    T0 = -130.  # equilibrium temperature with heater off; is -130°C due to background sources
    
    t_l = 10.  # thermal lag, after which the heat input per cycle is fully accounted for in T, in seconds
    t_d = 1.  # dead time, before T is affected by heating
    f_k = 2.5  # "thermal conductivity" factor; the higher, the steeper T responds to the heater input, must be strictly larger than 1.

    # Note.- Maximum voltage at the heater in case of failure should be less than 55V, considering a heater resistance of 22.75Ohms and maximum rating current of 2.5Amp.
    # Note .- the definition of the control strategy for the heater power supply is:
    # When, Vcontrol > 3.1V =>	14V ≤ Vheater ≤ 15V; Vcontrol ≤ 0.2V =>	Vheater = 0V

    def __init__(self, T_init, step=.1, speedup=1, record=False, delay_func=sigmoid):

        self.T = T_init

        self.step = step
        self.speedup = speedup

        # "thermal conductivity"
        self.set_delay_func(delay_func)  # normalised distribution function for delay behaviour

        self.htr_pwr = 0
        self.htr_cur = 0

        self.inst_heat = 0  # additional, immediate heat input (e.g., from CCD, etc.)

        self._evolving = False
        self.record = record
        self.log = []
        self._thread = None

    @property
    def T_noisy(self):
        return rng.normal(self.T, ctok(self.T) * self.sigma_T)

    def calc_delay_factors(self, n):
        if self.t_l > 0:
            n0 = int(round(n * (self.t_d / self.t_l)))
        else:
            n0 = 0
        
        df = np.diff(self._delay_func(n-n0+1, 1, self.f_k))
        assert df.sum().round(3) == 1.  # make sure energy is conserved

        return np.concatenate([np.zeros(n0), df])

    def set_delay_func(self, func):
        self._delay_func = func

        n = max(1, int(round(self.t_l / self.step)))
        self.heat_distr = self.calc_delay_factors(n)
        self.heat_pipe = np.zeros(len(self.heat_distr))

    def evolve(self, t1):

        self.T, heatpwr, coolpwr = self.calc_t_new()

        if self.record:
            self.log.append((t1, self.T, heatpwr, coolpwr))

    def cool(self):
        return self.rad_area * self.epsilon * SIGMA_SB * (ctok(self.T)**4 - ctok(self.T0)**4)

    def heat(self):
        self.heat_pipe += self.htr_pwr * self.heat_distr
        addheat = self.heat_pipe[0] + self.inst_heat
        #print(self.heat_pipe, self.heat_pipe.sum(), self.htr_pwr,self.inst_heat)
        self.heat_pipe = np.roll(self.heat_pipe, -1)
        self.heat_pipe[-1] = 0
        return addheat

    def calc_t_new(self):
        heatpwr = self.heat()
        coolpwr = self.cool()
        return self.T + ((heatpwr - coolpwr) * self.step) / (cp_al(ctok(self.T)) * self.mass), heatpwr, coolpwr

    def start(self):

        if self._thread is not None and self._thread.is_alive():
            print('Model already running')
            return

        self._evolving = True
        self._thread = threading.Thread(target=self._stepper, name='stepper_thread')
        self._thread.daemon = True
        self._thread.start()

    def _stepper(self):
        print('Started T simulation (step = {} s)'.format(self.step))
        while self._evolving:
            t1 = time.time()
            self.evolve(t1)
            dt = time.time() - t1
            if (self.step/self.speedup - dt) > 0:
                time.sleep(self.step - dt)
            else:
                print('Step execution time exceeding step period! ({})'.format(dt))

        print('T simulation terminated')

    def stop(self):
        self._evolving = False

    def set_heater_power(self, vctrl=None, ihtr=None):

        if vctrl is not None:
            vhtr = vctrl_to_vhtr(vctrl)
            self.htr_pwr = (vhtr**2 / self.R_htr) * self.htr_eff
            self.htr_cur = vhtr / self.R_htr

        elif ihtr is not None:
            self.htr_pwr = ihtr**2 * self.R_htr * self.htr_eff
            self.htr_cur = ihtr


class ThermalLoopConnector(com.Connector):

    def __init__(self, model, *args, pool_name='LIVE', apid=321, sid=3, cal_file=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model  # ThermalModel instance
        self.connect()
        self.pool_name = pool_name
        self.apid = apid
        self.sid = sid
        self.cal_file = cal_file
        self.update_period = None
        self._updating = False
        # self.start_receiver()

    @property
    def pwm(self):
        return iwf.ccd_pwm_from_temp(self.model.T, cal_file=self.cal_file)

    def set_ccd_pwm(self):
        cmd = iwf.Command.set_pwm(iwf.Signal.CDD_Thermistor, self.pwm)
        self.send(cmd, rx=False)

    @property
    def adc_i_heater(self):
        return cal.decalibrate(self.model.htr_cur, cal.Psu.ADC_I_HEATER)

    def set_adc_i_heater(self):
        htr_signal = iwf.adu_to_ana_adcihtr(self.adc_i_heater)
        cmd = iwf.Command.set_psu_analogue_value(iwf.Signal.EGSE_I_HEATER, htr_signal)
        self.send(cmd, rx=False)

    def start_updating(self, period):
        self._updating = True
        self.update_period = period
        self._update_thread = threading.Thread(target=self._update_worker, name='update_worker')
        self._update_thread.start()

    def _update_worker(self):

        print('Started updating PWM with a period of {} seconds'.format(self.update_period))
        while self._updating:
            try:
                t1 = time.time()

                self.update_model()  # update model with current htr_pwr

                self.set_ccd_pwm()  # update ADC_TEMP_CCD
                self.set_adc_i_heater()  # update ADC_I_HEATER

                time.sleep(self.update_period - (t1 - time.time()))

            except Exception as err:
                print(err)
                self._updating = False

        print('Stopped updating PWM')

    def stop_updating(self):
        self._updating = False

    def update_model(self):
        vctrl = self.get_vctrl()
        if vctrl is not None:
            self.model.set_heater_power(vctrl=vctrl)
        else:
            print('Failed to get VCTRL from TM')

    def get_vctrl(self):
        hk = filter_rows(get_pool_rows(self.pool_name), st=3, sst=25, apid=self.apid, sid=self.sid, get_last=True)
        if hk is not None:
            vctrl, = struct.unpack('>f', hk.raw[20:24])
            return vctrl


if __name__ == '__main__':

    mod = ThermalModel(-90)
    tmc = ThermalLoopConnector(mod, '', 8089)
