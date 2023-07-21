"""
Calibration functions and utilities for raw/engineering conversions in SMILE

Data from SMILE-IWF-PL-UM-147-d0-3_SXI_EBox_User_Manual (ID 5233)
"""

import os
import numpy as np
import scipy as sp

# constants
T_ZERO = 273.15

# common ADC coefficients
ADC_INPRNG = 7.34783  # V
ADC_OFFSET = -1.69565  # V


class Dpu:

    _unit = "V"

    ADC_P3V9 = "HK_ADC_P3V9"
    ADC_P3V3 = "HK_ADC_P3V3"
    ADC_P3V3_LVDS = "HK_ADC_P3V3_LVDS"
    ADC_P2V5 = "HK_ADC_P2V5"
    ADC_P1V8 = "HK_ADC_P1V8"
    ADC_P1V2 = "HK_ADC_P1V2"
    ADC_REF = "HK_ADC_REF"


K_DPU = {
    Dpu.ADC_P3V9: 2,
    Dpu.ADC_P3V3: 1,
    Dpu.ADC_P3V3_LVDS: 1,
    Dpu.ADC_P2V5: 1,
    Dpu.ADC_P1V8: 1,
    Dpu.ADC_P1V2: 1,
    Dpu.ADC_REF: 1
}


class Temp:

    _unit = "degC"

    ADC_TEMP1 = "HK_ADC_TEMP1"
    ADC_TEMP_FEE = "HK_ADC_TEMP_FEE"
    ADC_TEMP_CCD = "HK_ADC_TEMP_CCD"
    ADC_PSU_TEMP = "HK_ADC_PSU_TEMP"


# Signal specific coefficients
class V_T0:
    CCD = 2.5650
    TEMP1 = 2.5770
    FEE = 1.2800


class K_T:
    CCD = 0.00385
    TEMP1 = 0.00385
    FEE = 0.00385


# interpolation table for nominal operation CCD temperature
# (degC, ADC_V, ADU_dec, ADU_hex)
CCD_TEMP_TABLE = [
    (-140.0, 1.125, 6288, 0x1890),
    (-135.0, 1.178, 6407, 0x1906),
    (-130.0, 1.231, 6524, 0x197C),
    (-125.0, 1.283, 6642, 0x19F1),
    (-120.0, 1.336, 6759, 0x1A66),
    (-115.0, 1.388, 6876, 0x1ADB),
    (-110.0, 1.440, 6992, 0x1B50),
    (-105.0, 1.493, 7109, 0x1BC4),
    (-100.0, 1.545, 7225, 0x1C38),
    (-95.0, 1.596, 7340, 0x1CAC),
    (-90.0, 1.648, 7456, 0x1D1F),
    (-85.0, 1.700, 7571, 0x1D92),
    (-80.0, 1.751, 7686, 0x1E05),
    (-75.0, 1.803, 7800, 0x1E78),
    (-70.0, 1.854, 7915, 0x1EEA),
    (-65.0, 1.905, 8029, 0x1F5D),
    (-60.0, 1.957, 8143, 0x1FCF),
    (-55.0, 2.008, 8257, 0x2040),
    (-50.0, 2.059, 8371, 0x20B2),
    (-45.0, 2.109, 8484, 0x2123),
    (-40.0, 2.160, 8597, 0x2195),
    (-35.0, 2.211, 8710, 0x2206),
    (-30.0, 2.261, 8823, 0x2276),
    (-25.0, 2.312, 8936, 0x22E7),
    (-20.0, 2.362, 9048, 0x2358)
]

# interpolation table for PSU temperature
# (degC, ADC_V, ADU_dec, ADU_hex)
PSU_TEMP = [
    (-50.0, 3.237, 10998, 0x2AF6),
    (-40.0, 3.187, 10887, 0x2A86),
    (-20.0, 2.960, 10380, 0x288C),
    (0.0, 2.487, 9326, 0x246D),
    (20.0, 1.816, 7830, 0x1E95),
    (25.0, 1.643, 7444, 0x1D13),
    (40.0, 1.169, 6387, 0x18F3),
    (60.0, 0.703, 5348, 0x14E4),
    (80.0, 0.417, 4710, 0x1266),
    (90.0, 0.323, 4501, 0x1194),
    (100.0, 0.252, 4343, 0x10F6)
]


class Psu:

    _unit = "A"

    ADC_I_FEE_ANA = "HK_ADC_I_FEE_ANA"
    ADC_I_FEE_DIG = "HK_ADC_I_FEE_DIG"
    ADC_I_DPU = "HK_ADC_I_DPU"
    ADC_I_RSE = "HK_ADC_I_RSE"
    ADC_I_HEATER = "HK_ADC_I_HEATER"


K_PSU = {
    Psu.ADC_I_FEE_ANA: 0.3058,
    Psu.ADC_I_FEE_DIG: 0.1528,
    Psu.ADC_I_DPU: 0.4913,
    Psu.ADC_I_RSE: 0.844,
    Psu.ADC_I_HEATER: 0.4349
}

PSU_OFFSET = {
    Psu.ADC_I_FEE_ANA: 0,
    Psu.ADC_I_FEE_DIG: 0,
    Psu.ADC_I_DPU: 0,
    Psu.ADC_I_RSE: 0,
    Psu.ADC_I_HEATER: -0.3701
}


class Rse:

    _unit = "degC"

    RSE_MOTOR_TEMP = "HK_RSE_MOTOR_TEMP"
    RSE_ELEC_TEMP = "HK_RSE_ELEC_TEMP"


# fit polynomial of degree POLY_DEG through CCD ADU-degC relation (operational range)
_ccd_temp_adu_array = np.array(CCD_TEMP_TABLE).T  # (degC, ADC_V, ADU_dec, ADU_hex)
POLY_DEG = 4
_ccd_temp_fit_adu = np.polynomial.polynomial.Polynomial.fit(_ccd_temp_adu_array[2], _ccd_temp_adu_array[0],
                                                            POLY_DEG).convert()
_ccd_temp_fit_adu_inv = np.polynomial.polynomial.Polynomial.fit(_ccd_temp_adu_array[0], _ccd_temp_adu_array[2],
                                                                POLY_DEG).convert()

# cubic-spline interpolation of PSU ADU-degC relation (nominal values)
_psu_temp_adu_array = np.array(PSU_TEMP).T  # (degC, ADC_V, ADU_dec, ADU_hex)
_psu_temp_interp = sp.interpolate.interp1d(_psu_temp_adu_array[2], _psu_temp_adu_array[0],
                                           kind='cubic', fill_value='extrapolate')
_psu_temp_interp_inv = sp.interpolate.interp1d(_psu_temp_adu_array[0], _psu_temp_adu_array[2], kind='cubic',
                                               fill_value='extrapolate')


def t_ccd_adu_to_deg_oper(adu, warn=True):
    if not ((_ccd_temp_adu_array[2].min() <= adu) & (adu <= _ccd_temp_adu_array[2].max())).all() and warn:
        print('WARNING! Value(s) outside operational range ({:.0f}-{:.0f})!'.format(_ccd_temp_adu_array[2].min(),
                                                                                    _ccd_temp_adu_array[2].max()))
    return _ccd_temp_fit_adu(adu)


def t_ccd_deg_to_adu_oper(t, warn=True):
    if not ((_ccd_temp_adu_array[0].min() <= t) & (t <= _ccd_temp_adu_array[0].max())).all() and warn:
        print('WARNING! Value(s) outside operational range ({} - {})!'.format(_ccd_temp_adu_array[0].min(),
                                                                              _ccd_temp_adu_array[0].max()))
    return np.rint(_ccd_temp_fit_adu_inv(t)).astype(int)


def t_ccd_adu_to_deg_nonoper(adu):
    return (adu * ADC_INPRNG / (2 ** 14 - 1) + ADC_OFFSET - V_T0.CCD) / (V_T0.CCD * K_T.CCD)


def t_ccd_deg_to_adu_nonoper(t):
    return np.rint(((t * V_T0.CCD * K_T.CCD - ADC_OFFSET + V_T0.CCD) * (2 ** 14 - 1)) / ADC_INPRNG).astype(int)


def t_ccd_adu_to_deg(adu):
    return np.where(adu <= _ccd_temp_adu_array[2].max(), t_ccd_adu_to_deg_oper(adu, warn=False), t_ccd_adu_to_deg_nonoper(adu))


def t_ccd_deg_to_adu(t):
    return np.where(t <= _ccd_temp_adu_array[0].max(), t_ccd_deg_to_adu_oper(t, warn=False), t_ccd_deg_to_adu_nonoper(t))


def t_ccd_fee_adu_to_deg(adu):
    """
    For CCD temperature reported in FEE HK

    :param adu:
    :return:
    """
    return adu / 65535 * 4.096 * 338.581 - T_ZERO


def t_ccd_fee_deg_to_adu(t):
    """
    For CCD temperature reported in FEE HK

    :param t:
    :return:
    """
    return np.rint((t + T_ZERO) / (4.096 * 338.581) * 65535).astype(int)


def t_temp1_adu_to_deg(adu):
    return (adu * ADC_INPRNG / (2 ** 14 - 1) + ADC_OFFSET - V_T0.TEMP1) / (V_T0.TEMP1 * K_T.TEMP1)


def t_temp1_deg_to_adu(t):
    return np.rint(((t * V_T0.TEMP1 * K_T.TEMP1 - ADC_OFFSET + V_T0.TEMP1) * (2 ** 14 - 1)) / ADC_INPRNG).astype(int)


def t_fee_adu_to_deg(adu):
    return (adu * ADC_INPRNG / (2 ** 14 - 1) + ADC_OFFSET - V_T0.FEE) / (V_T0.FEE * K_T.FEE)


def t_fee_deg_to_adu(t):
    return np.rint(((t * V_T0.FEE * K_T.FEE - ADC_OFFSET + V_T0.FEE) * (2 ** 14 - 1)) / ADC_INPRNG).astype(int)


def t_rse_adu_to_deg(adu):
    return (3.908 - np.sqrt(17.59246 - (76.56 / (4096 / adu - 1)))) / 0.00116


def t_rse_deg_to_adu(t):
    return np.rint(4096 / (76.56 / (17.59246 - (3.908 - 0.00116 * t) ** 2) + 1)).astype(int)


def t_psu_adu_to_deg(adu):
    return _psu_temp_interp(adu)


def t_psu_deg_to_adu(t):
    return _psu_temp_interp_inv(t)


def t_adu_to_deg(adu, signal):
    if signal == Temp.ADC_TEMP_CCD:
        t = t_ccd_adu_to_deg(adu)
    elif signal == Temp.ADC_TEMP1:
        t = t_temp1_adu_to_deg(adu)
    elif signal == Temp.ADC_TEMP_FEE:
        t = t_fee_adu_to_deg(adu)
    elif signal == Temp.ADC_PSU_TEMP:
        t = t_psu_adu_to_deg(adu)
    elif signal in (Rse.RSE_MOTOR_TEMP, Rse.RSE_ELEC_TEMP):
        t = t_rse_adu_to_deg(adu)
    else:
        raise ValueError("Unknown signal '{}'".format(signal))

    return t


def t_deg_to_adu(t, signal):
    if signal == Temp.ADC_TEMP_CCD:
        adu = t_ccd_deg_to_adu(t)
    elif signal == Temp.ADC_TEMP1:
        adu = t_temp1_deg_to_adu(t)
    elif signal == Temp.ADC_TEMP_FEE:
        adu = t_fee_deg_to_adu(t)
    elif signal == Temp.ADC_PSU_TEMP:
        adu = t_psu_deg_to_adu(t)
    elif signal in (Rse.RSE_MOTOR_TEMP, Rse.RSE_ELEC_TEMP):
        adu = t_rse_deg_to_adu(t)
    else:
        raise ValueError("Unknown signal '{}'".format(signal))

    return adu


def u_dpu_adu_to_volt(adu, signal):
    return ((adu * ADC_INPRNG) / (2 ** 14 - 1) + ADC_OFFSET) * K_DPU[signal]


def u_dpu_volt_to_adu(u, signal):
    return np.rint(((u / K_DPU[signal] - ADC_OFFSET) * (2 ** 14 - 1)) / ADC_INPRNG).astype(int)


def i_psu_adu_to_amp(adu, signal):
    return ((adu * ADC_INPRNG) / (2 ** 14 - 1) + ADC_OFFSET) * K_PSU[signal] + PSU_OFFSET[signal]


def i_psu_amp_to_adu(i, signal):
    return np.rint((((i - PSU_OFFSET[signal]) / K_PSU[signal] - ADC_OFFSET) * (2 ** 14 - 1)) / ADC_INPRNG).astype(int)


def calibrate(adu, signal):
    """

    :param adu:
    :param signal:
    :return:
    """

    if signal in SIGNAL_IASW_DBS:
        signal = SIGNAL_IASW_DBS[signal]

    if signal in Dpu.__dict__.values():
        x = u_dpu_adu_to_volt(adu, signal)
    elif signal in Temp.__dict__.values() or signal in Rse.__dict__.values():
        x = t_adu_to_deg(adu, signal)
    elif signal in Psu.__dict__.values():
        x = i_psu_adu_to_amp(adu, signal)
    else:
        raise ValueError("Unknown signal '{}'".format(signal))

    return x


def decalibrate(x, signal):
    """

    :param x:
    :param signal:
    :return:
    """

    if signal in SIGNAL_IASW_DBS:
        signal = SIGNAL_IASW_DBS[signal]

    if signal in Dpu.__dict__.values():
        adu = u_dpu_volt_to_adu(x, signal)
    elif signal in Temp.__dict__.values() or signal in Rse.__dict__.values():
        adu = t_deg_to_adu(x, signal)
    elif signal in Psu.__dict__.values():
        adu = i_psu_amp_to_adu(x, signal)
    else:
        raise ValueError("Unknown signal '{}'".format(signal))

    return adu


class CalibrationTables:
    # default ADC limits
    BOUND_L = 0
    BOUND_U = 0x3FFE

    BOUND_RSE_L = 0x01
    BOUND_RSE_U = 0xCD

    def __init__(self):

        # temperatures
        # x = np.linspace(self.BOUND_L, self.BOUND_U, 60, dtype=int)
        self.temperature = {}
        for sig in vars(Temp):
            # CCD TEMP
            if sig == 'ADC_TEMP_CCD':
                label = getattr(Temp, sig)
                lmts = getattr(Limits, sig)
                x = np.linspace(6000, 11700, 60, dtype=int)
                self.temperature[label] = np.array([x, t_adu_to_deg(x, label)])
            # PSU TEMP
            elif sig == 'ADC_PSU_TEMP':
                label = getattr(Temp, sig)
                lmts = getattr(Limits, sig)
                x = np.linspace(int(lmts[0]*0.9), 11650, 50, dtype=int)
                self.temperature[label] = np.array([x, t_adu_to_deg(x, label)])
            elif sig.startswith('ADC'):
                label = getattr(Temp, sig)
                lmts = getattr(Limits, sig)
                x = np.linspace(int(lmts[0]*0.9), int(lmts[-1]*1.1), 50, dtype=int)
                self.temperature[label] = np.array([x, t_adu_to_deg(x, label)])

        x = np.linspace(self.BOUND_RSE_L, self.BOUND_RSE_U, 50, dtype=int)
        for sig in vars(Rse):
            if sig.startswith('RSE'):
                label = getattr(Rse, sig)
                self.temperature[label] = np.array([x, t_adu_to_deg(x, label)])

        x = np.linspace(self.BOUND_L, self.BOUND_U, 2, dtype=int)  # two points suffice for linear voltage and current calibrations
        # voltages
        self.voltage = {}
        for sig in vars(Dpu):
            if sig.startswith('ADC'):
                label = getattr(Dpu, sig)
                self.voltage[label] = np.array([x, u_dpu_adu_to_volt(x, label)])

        # currents
        self.current = {}
        for sig in vars(Psu):
            if sig.startswith('ADC'):
                label = getattr(Psu, sig)
                self.current[label] = np.array([x, i_psu_adu_to_amp(x, label)])

    def write_to_files(self, path):

        for k in self.temperature:
            np.savetxt(os.path.join(path, k + '.dat'), self.temperature[k].T, header=k, fmt=('%5d', '%6.1f'))

        for k in self.voltage:
            np.savetxt(os.path.join(path, k + '.dat'), self.voltage[k].T, header=k, fmt=('%5d', '%6.3f'))

        for k in self.current:
            np.savetxt(os.path.join(path, k + '.dat'), self.current[k].T, header=k, fmt=('%5d', '%6.3f'))

        print("Calibration tables written to {}".format(path))

    def _plot(self, signal, xmin=BOUND_L, xmax=BOUND_U):

        if 'plt' not in globals():
            raise ModuleNotFoundError("This only works in stand-alone mode")

        sig = signal[3:]

        if sig in vars(Dpu):
            xy = self.voltage[signal]
            ylabel = 'Voltage [V]'
        elif sig in vars(Temp):
            xy = self.temperature[signal]
            ylabel = 'Temperature [°C]'
        elif sig in vars(Psu):
            xy = self.current[signal]
            ylabel = 'Current [A]'
        else:
            raise ValueError("Unknown signal '{}'".format(sig))

        xref = np.linspace(xmin, xmax, 1000)
        yref = calibrate(xref, signal)

        limits = np.array((np.array(getattr(Limits, sig)), calibrate(np.array(getattr(Limits, sig)), signal))).T
        print(limits)
        fl, wl, wu, fu = limits
        plt.axvspan(xmin, fl[0], alpha=0.25, color='red')
        plt.axvspan(fl[0], wl[0], alpha=0.5, color='orange')
        plt.axvspan(wu[0], fu[0], alpha=0.5, color='orange')
        plt.axvspan(fu[0], xmax, alpha=0.25, color='red')

        for i in limits:
            plt.axhline(i[1], ls=':', color='grey')

        plt.plot(xref, yref, color='grey', lw=0.5)
        plt.plot(*xy, 'k.', label=signal, ms=4)
        # plt.legend()
        plt.xlabel('ADU')
        plt.ylabel(ylabel)
        plt.title(signal)
        plt.grid(True)
        plt.show()


class Limits:
    # raw operational limits (FAIL_L, WARN_L, WARN_U, FAIL_U)
    ADC_P3V9 = (0x1D8D, 0x1E67, 0x2119, 0x21F3)
    ADC_P3V3 = (0x27A2, 0x2912, 0x2DF2, 0x2F62)
    ADC_P3V3_LVDS = (0x27A2, 0x2912, 0x2DF2, 0x2F62)
    ADC_P2V5 = (0x215D, 0x2274, 0x26A1, 0x27B8)
    ADC_P1V8 = (0x1BE0, 0x1CA9, 0x203A, 0x2103)
    ADC_P1V2 = (0x172C, 0x17B2, 0x1ABE, 0x1B43)
    ADC_REF = (0x215D, 0x2274, 0x26A1, 0x27B8)
    ADC_TEMP1 = (0x210F, 0x2259, 0x2B37, 0x2C12)
    ADC_TEMP_FEE = (0x17EA, 0x188E, 0x1CFD, 0x1D6B)
    ADC_TEMP_CCD = (0x1968, 0x19DD, 0x1D20, 0x1D93)
    ADC_I_FEE_ANA = (0xDC4, 0xDC4, 0x1D70, 0x1ECE)
    ADC_I_FEE_DIG = (0xDC4, 0xDC4, 0x20FB, 0x22B4)
    ADC_I_DPU = (0xDC4, 0xDC4, 0x20B7, 0x2269)
    ADC_I_RSE = (0xDC4, 0xDC4, 0x1EA8, 0x2025)
    ADC_I_HEATER = (0x152E, 0x152E, 0x23B2, 0x24F2)
    ADC_PSU_TEMP = (0x12A5, 0x13E4, 0x298C, 0x2B08)

    # raw upper RSE limits
    RSE_MOTOR_TEMP = 0x96
    RSE_ELEC_TEMP = 0x96

    # raw ambient CCD limits
    ADC_TEMP_CCD_AMB = (0x1968, 0x19DD, 0x29DB, 0x2A49)


class LimitTables:

    def __init__(self):

        # temperatures
        self.temperature = {}
        for sig in vars(Temp):
            if sig.startswith('ADC'):
                label = getattr(Temp, sig)
                adu_limits = np.array(getattr(Limits, sig))
                self.temperature[label] = np.array([adu_limits, t_adu_to_deg(adu_limits, label)])

        for sig in vars(Rse):
            if sig.startswith('RSE'):
                label = getattr(Rse, sig)
                adu_limits = np.array(getattr(Limits, sig))
                self.temperature[label] = np.array([adu_limits, t_adu_to_deg(adu_limits, label)])

        # voltages
        self.voltage = {}
        for sig in vars(Dpu):
            if sig.startswith('ADC'):
                label = getattr(Dpu, sig)
                adu_limits = np.array(getattr(Limits, sig))
                self.voltage[label] = np.array([adu_limits, u_dpu_adu_to_volt(adu_limits, label)])

        # currents
        self.current = {}
        for sig in vars(Psu):
            if sig.startswith('ADC'):
                label = getattr(Psu, sig)
                adu_limits = np.array(getattr(Limits, sig))
                self.current[label] = np.array([adu_limits, i_psu_adu_to_amp(adu_limits, label)])


# lookup table for DBS vs IASW naming
SIGNAL_IASW_DBS = {
    "AdcP3V9": Dpu.ADC_P3V9,
    "AdcP3V3": Dpu.ADC_P3V3,
    "AdcP3V3LVDS": Dpu.ADC_P3V3_LVDS,
    "AdcP2V5": Dpu.ADC_P2V5,
    "AdcP1V8": Dpu.ADC_P1V8,
    "AdcP1V2": Dpu.ADC_P1V2,
    "AdcRef": Dpu.ADC_REF,
    "AdcTemp1": Temp.ADC_TEMP1,
    "AdcTempFee": Temp.ADC_TEMP_FEE,
    "AdcTempCcd": Temp.ADC_TEMP_CCD,
    "AdcPsuTemp": Temp.ADC_PSU_TEMP,
    "AdcIFeeAna": Psu.ADC_I_FEE_ANA,
    "AdcIFeeDig": Psu.ADC_I_FEE_DIG,
    "AdcIDpu": Psu.ADC_I_DPU,
    "AdcIRse": Psu.ADC_I_RSE,
    "AdcIHeater": Psu.ADC_I_HEATER,
    "RseMotorTemp": Rse.RSE_MOTOR_TEMP,
    "RseElecTemp": Rse.RSE_ELEC_TEMP
}

SIGNAL_DBS_IASW = {SIGNAL_IASW_DBS[k]: k for k in SIGNAL_IASW_DBS}

if __name__ == '__main__':

    import matplotlib.pyplot as plt

    ct = CalibrationTables()
    ct._plot(Temp.ADC_PSU_TEMP)
    # ct.write_to_files('/home/marko/space/CCS/calibrations')
    lmt = LimitTables()
