"""
Calibration functions and utilities for raw/engineering conversions in SMILE

Data from SMILE-IWF-PL-UM-147-d0-3_SXI_EBox_User_Manual (ID 5233) and SMILE-IWF-PL-UM-147-i1-0_SXI_EBox_User_Manual (ID 5233)
"""

import os
import numpy as np
import scipy as sp

# constants
T_ZERO = 273.15

# common ADC coefficients
ADC_INPRNG = 7.34783  # V
ADC_OFFSET = -1.69565  # V

# PFM
# # nom
# ADC_INPRNG = 7.58261  # V
# ADC_OFFSET = -1.76956  # V
# # red
# ADC_INPRNG = 7.54783  # V
# ADC_OFFSET = -1.77391  # V


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

    # PFM
    # # nom
    # CCD = 2.5688
    # TEMP1 = 2.5599
    # FEE = 1.2749
    # # red
    # CCD = 2.5547
    # TEMP1 = 2.5649
    # FEE = 1.2779


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

# PFM
# # nom
# CCD_TEMP_TABLE = [
#     (-140.0, 1.123, 6250, 0x186A),
#     (-135.0, 1.176, 6364, 0x18DC),
#     (-130.0, 1.229, 6478, 0x194E),
#     (-125.0, 1.281, 6592, 0x19C0),
#     (-120.0, 1.334, 6705, 0x1A31),
#     (-115.0, 1.386, 6818, 0x1AA2),
#     (-110.0, 1.438, 6931, 0x1B13),
#     (-105.0, 1.491, 7044, 0x1B84),
#     (-100.0, 1.542, 7156, 0x1BF4),
#     (-95.0, 1.594, 7268, 0x1C64),
#     (-90.0, 1.646, 7380, 0x1CD4),
#     (-85.0, 1.698, 7491, 0x1D43),
#     (-80.0, 1.749, 7602, 0x1DB2),
#     (-75.0, 1.800, 7713, 0x1E21),
#     (-70.0, 1.852, 7824, 0x1E90),
#     (-65.0, 1.903, 7935, 0x1EFF),
#     (-60.0, 1.954, 8045, 0x1F6D),
#     (-55.0, 2.005, 8155, 0x1FDB),
#     (-50.0, 2.056, 8265, 0x2049),
#     (-45.0, 2.107, 8375, 0x20B7),
#     (-40.0, 2.157, 8484, 0x2124),
#     (-35.0, 2.208, 8594, 0x2192),
#     (-30.0, 2.258, 8703, 0x21FF),
#     (-25.0, 2.309, 8812, 0x226C),
#     (-20.0, 2.359, 8921, 0x22D9)
# ]
#
# # red
# CCD_TEMP_TABLE = [
#     (-140.0, 1.121, 6283, 0x188B),
#     (-135.0, 1.174, 6398, 0x18FE),
#     (-130.0, 1.226, 6512, 0x1970),
#     (-125.0, 1.279, 6626, 0x19E2),
#     (-120.0, 1.331, 6740, 0x1A54),
#     (-115.0, 1.383, 6853, 0x1AC5),
#     (-110.0, 1.436, 6966, 0x1B36),
#     (-105.0, 1.488, 7079, 0x1BA7),
#     (-100.0, 1.539, 7192, 0x1C18),
#     (-95.0, 1.591, 7304, 0x1C88),
#     (-90.0, 1.643, 7416, 0x1CF8),
#     (-85.0, 1.694, 7528, 0x1D68),
#     (-80.0, 1.746, 7639, 0x1DD7),
#     (-75.0, 1.797, 7750, 0x1E46),
#     (-70.0, 1.848, 7861, 0x1EB5),
#     (-65.0, 1.899, 7972, 0x1F24),
#     (-60.0, 1.950, 8083, 0x1F93),
#     (-55.0, 2.001, 8193, 0x2001),
#     (-50.0, 2.052, 8304, 0x2070),
#     (-45.0, 2.102, 8414, 0x20DE),
#     (-40.0, 2.153, 8523, 0x214B),
#     (-35.0, 2.203, 8633, 0x21B9),
#     (-30.0, 2.254, 8742, 0x2226),
#     (-25.0, 2.304, 8852, 0x2294),
#     (-20.0, 2.354, 8961, 0x2301)
# ]


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

# PFM
# PSU_TEMP = [
#     (-50.0, 3.237, 10998, 0x2AF6),
#     (-40.0, 3.187, 10887, 0x2A86),
#     (-20.0, 2.960, 10380, 0x288C),
#     (0.0, 2.487, 9326, 0x246D),
#     (20.0, 1.816, 7830, 0x1E95),
#     (25.0, 1.643, 7444, 0x1D13),
#     (40.0, 1.169, 6387, 0x18F3),
#     (60.0, 0.703, 5348, 0x14E4),
#     (80.0, 0.417, 4710, 0x1266),
#     (90.0, 0.323, 4501, 0x1194),
#     (100.0, 0.252, 4343, 0x10F6)
# ]


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

# PFM
# K_PSU = {
#     Psu.ADC_I_FEE_ANA: 0.3058,
#     Psu.ADC_I_FEE_DIG: 0.1528,
#     Psu.ADC_I_DPU: 0.603,
#     Psu.ADC_I_RSE: 0.844,
#     Psu.ADC_I_HEATER: 0.4349
# }

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
# IASW coefs for PFM nom: ['-4.02587E+02', '4.33198E-02', '-9.26990E-07', '1.53423E-10', '-6.16102E-15']
# IASW coefs for PFM red: ['-3.78077E+02', '2.99914E-02', '1.66375E-06', '-7.20486E-11', '1.17412E-15']
POLY_DEG = 4
_ccd_temp_adu_array = np.array(CCD_TEMP_TABLE).T  # (degC, ADC_V, ADU_dec, ADU_hex)
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


def cal_pt1000(temp):
    return cal_ptx(temp, 1000)


def cal_pt2000(temp):
    return cal_ptx(temp, 2000)


def cal_ptx(temp, R0):
    """
    Standard DIN EN 60751 PTX transfer curve (-200 - 850°C)

    :param temp: temperature in °C
    :return: resistance in Ohm
    """
    A = 3.9083e-3
    B = -5.775e-7
    C = -4.183e-12

    def subzero():
        return R0 * (1 + A*temp + B*temp**2 + C*(temp - 100)*temp**3)

    def abovezero():
        return R0 * (1 + A*temp + B*temp**2)

    if (np.array(temp) < -200).any() or (np.array(temp) > 850).any():
        print("WARNING: Value(s) outside calibrated range (-200 - 850°C)!")

    return np.where(temp > 0, abovezero(), subzero())


_ptx = np.arange(-200, 851)
_pty = cal_pt1000(_ptx)
_pt1000_curve_inv = sp.interpolate.interp1d(_pty, _ptx, kind='cubic', fill_value='extrapolate')  # inverse PT1000 curve for Ohm to °C conversion

# quadratic fit to PT1000 curve in custom range to get
# inverse formula parameters for Ohms to °C conversion (used in on-board FEE temp calculation)
# -140 - -20°C: [ 9.99495990e+02,  3.88482301e+00, -8.51690296e-04]
_FEE_TEMP_MIN = -140
_FEE_TEMP_TMAX = -20
_trng = np.arange(_FEE_TEMP_MIN, _FEE_TEMP_TMAX, .1)
_rrng = cal_pt1000(_trng)
_fee_temp_p2fit = np.polynomial.polynomial.Polynomial.fit(_trng, _rrng, 2).convert()


def t_ccd_fee_adu_to_deg(adu, ccd):
    """
    For CCD temperature reported in FEE HK. Uses PT1000!

    :param adu:
    :param ccd:
    :return:
    """
    if ccd == 2:
        return _pt1000_curve_inv(adu * FEE_CCD2TsA_gain + FEE_CCD2TsA_offset)
    elif ccd == 4:
        return _pt1000_curve_inv(adu * FEE_CCD4TsB_gain + FEE_CCD4TsB_offset)
    else:
        raise ValueError("CCD must be either 2 or 4!")


def t_ccd_fee_deg_to_adu(t, ccd):
    """
    For CCD temperature reported in FEE HK

    :param t:
    :param ccd:
    :return:
    """
    if ccd == 2:
        return np.rint((cal_pt1000(t) - FEE_CCD2TsA_offset) / FEE_CCD2TsA_gain).astype(int)
    elif ccd == 4:
        return np.rint((cal_pt1000(t) - FEE_CCD4TsB_offset) / FEE_CCD4TsB_gain).astype(int)
    else:
        raise ValueError("CCD must be either 2 or 4!")


class Fee:

    CCD2_TS_A = "FRMHKccd2TsA"
    CCD4_TS_B = "FRMHKccd4TsB"
    PRT1 = "FRMHKprt1"
    PRT2 = "FRMHKprt2"
    PRT3 = "FRMHKprt3"
    PRT4 = "FRMHKprt4"
    PRT5 = "FRMHKprt5"
    CCD4_VOD_MON_E = "FRMHKccd4VodMonE"
    CCD4_VOG_MON = "FRMHKccd4VogMon"
    CCD4_VRD_MON_E = "FRMHKccd4VrdMonE"
    CCD2_VOD_MON_E = "FRMHKccd2VodMonE"
    CCD2_VOG_MON = "FRMHKccd2VogMon"
    CCD2_VRD_MON_E = "FRMHKccd2VrdMonE"
    CCD4_VRD_MON_F = "FRMHKccd4VrdMonF"
    CCD4_VDD_MON = "FRMHKccd4VddMon"
    CCD4_VGD_MON = "FRMHKccd4VgdMon"
    CCD2_VRD_MON_F = "FRMHKccd2VrdMonF"
    CCD2_VDD_MON = "FRMHKccd2VddMon"
    CCD2_VGD_MON = "FRMHKccd2VgdMon"
    VCCD = "FRMHKvccd"
    VRCLK_MON = "FRMHKvrclkMon"
    VICLK = "FRMHKviclk"
    CCD4_VOD_MON_F = "FRMHKccd4VodMonF"
    P5VB_POS_MON = "FRMHK5vbPosMon"
    P5VB_NEG_MON = "FRMHK5vbNegMon"
    P3V3B_MON = "FRMHK3v3bMon"
    P2V5A_MON = "FRMHK2v5aMon"
    P3V3D_MON = "FRMHK3v3dMon"
    P2V5D_MON = "FRMHK2v5dMon"
    P1V2D_MON = "FRMHK1v2dMon"
    P5VREF_MON = "FRMHK5vrefMon"
    VCCD_POS_RAW = "FRMHKvccdPosRaw"
    VCLK_POS_RAW = "FRMHKvclkPosRaw"
    VAN1_POS_RAW = "FRMHKvan1PosRaw"
    VAN3_NEG_MON = "FRMHKvan3NegMon"
    VAN2_POS_RAW = "FRMHKvan2PosRaw"
    VDIG_RAW = "FRMHKvdigRaw"
    IG_HI_MON = "FRMHKigHiMon"
    CCD2_VOD_MON_F = "FRMHKccd2VodMonF"


# FEE HK gains/offsets
# EQM
#     Fee.CCD2_TS_A: (0.048589970854, 326.709603726099),
#     Fee.CCD4_TS_B: (0.048346071846, 317.545999899085),
#     Fee.PRT1: (0.049337666752, 310.304954966437),
#     Fee.PRT2: (0.048871723231, 322.563832689621),
#     Fee.PRT3: (0.048882740559, 322.418053560869),
#     Fee.PRT4: (0.048777132761, 322.321990156487),
#     Fee.PRT5: (0.048683458078, 323.746239172483),

FEE_GAIN_OFFSET = {
    Fee.CCD2_TS_A: (0.0143896, 507.7463659),
    Fee.CCD4_TS_B: (0.0143869, 508.0853237),
    Fee.PRT1: (0.013942679, 511.4689646),
    Fee.PRT2: (0.014066366, 520.9910997),
    Fee.PRT3: (0.014075819, 520.1841103),
    Fee.PRT4: (0.013816741, 535.4382444),
    Fee.PRT5: (0.014074936, 520.4885901),
    Fee.CCD4_VOD_MON_E: (0.000563088127, -0.00209746042908421),
    Fee.CCD4_VOG_MON: (0.000135181804, -0.166559933290103),
    Fee.CCD4_VRD_MON_E: (0.000563174116, 0.0193461050916852),
    Fee.CCD2_VOD_MON_E: (0.000563015464, -0.0097318620270066),
    Fee.CCD2_VOG_MON: (0.000135565734, -0.164272515606305),
    Fee.CCD2_VRD_MON_E: (0.000562914749, 0.0221158942564337),
    Fee.CCD4_VRD_MON_F: (0.000563425754, 0.00833790912991361),
    Fee.CCD4_VDD_MON: (0.000816121249, 0),
    Fee.CCD4_VGD_MON: (0.000562165835, 0.0483795532258782),
    Fee.CCD2_VRD_MON_F: (0.000563631207, -0.00437775179765865),
    Fee.CCD2_VDD_MON: (0.000815982604, 0),
    Fee.CCD2_VGD_MON: (0.000556683023, 0.225687270717021),
    Fee.VCCD: (0.000756606970, 0),
    Fee.VRCLK_MON: (0.000360316440, 0),
    Fee.VICLK: (0.000360364766, 0),
    Fee.CCD4_VOD_MON_F: (0.000562995879, 0.00807772719949895),
    Fee.P5VB_POS_MON: (0.000092728181, 0),
    Fee.P5VB_NEG_MON: (-0.000125745208, 0),
    Fee.P3V3B_MON: (0.000062672872, 0),
    Fee.P2V5A_MON: (0.000062623239, 0),
    Fee.P3V3D_MON: (0.000062667814, 0),
    Fee.P2V5D_MON: (0.000062623117, 0),
    Fee.P1V2D_MON: (0.000031361075, 0),
    Fee.P5VREF_MON: (0.000097218804, 0),
    Fee.VCCD_POS_RAW: (0.000756449617, 0),
    Fee.VCLK_POS_RAW: (0.000360291117, 0),
    Fee.VAN1_POS_RAW: (0.000163267788, 0),
    Fee.VAN3_NEG_MON: (-0.000208630551, 0),
    Fee.VAN2_POS_RAW: (0.000163196727, 0),
    Fee.VDIG_RAW: (0.000097250522, 0),
    Fee.IG_HI_MON: (0.000186900810, 0),
    Fee.CCD2_VOD_MON_F: (0.000562860544, -0.00642286504851342)
}

FEE_CCD2TsA_gain, FEE_CCD2TsA_offset = FEE_GAIN_OFFSET[Fee.CCD2_TS_A]
FEE_CCD4TsB_gain, FEE_CCD4TsB_offset = FEE_GAIN_OFFSET[Fee.CCD4_TS_B]


def cal_fee_hk(adu, signal):
    """
    Calibrate raw FEE HK reading to engineering value

    @param signal:
    @param adu:
    @return:
    """

    if signal not in FEE_GAIN_OFFSET:
        raise ValueError('Unknown signal "{}"'.format(signal))

    gain, offset = FEE_GAIN_OFFSET[signal]
    val = adu * gain + offset

    if signal in [Fee.CCD2_TS_A, Fee.CCD4_TS_B, Fee.PRT1, Fee.PRT2, Fee.PRT3, Fee.PRT4, Fee.PRT5]:
        val = _pt1000_curve_inv(val)

    return val


def calibrate_ext(adu, signal, exception=False):
    """
    Provide unified access to customised calibrations outside MIB.
    This function shall expose all calibrations in this module that should be accessible by other CCS modules.

    :param adu:
    :param signal:
    :param exception:
    :return:
    """

    try:
        return cal_fee_hk(adu, signal)
    except ValueError:
        return adu if not exception else None

    # to disable calibration
    # return adu if not exception else None


# class _BadPixelMask2:
#     """
#     Convenience functions for handling the SMILE SXI bad pixel mask stored in MRAM
#     """
#
#     NROWS = 639
#     NCOLS = 384
#
#     CCD2_MASK_ADDR = 0x40654C00
#     CCD4_MASK_ADDR = 0x4065CC00
#
#     @classmethod
#     def from_bytes(cls, buffer):
#         return np.unpackbits(bytearray(buffer)).reshape((cls.NROWS, cls.NCOLS))
#
#     @classmethod
#     def to_bytes(cls, mask: np.ndarray):
#
#         assert isinstance(mask, np.ndarray)
#
#         if mask.size != cls.NROWS * cls.NCOLS:
#             raise ValueError("Mask must be array of size {}, is {}.".format(cls.NROWS * cls.NCOLS, mask.size))
#
#         return bytes(np.packbits(mask))
#
#     @classmethod
#     def gen_mask_array(cls):
#         return np.zeros((cls.NROWS, cls.NCOLS), dtype=int)


class BadPixelMask:

    NROWS = 639
    NCOLS = 384

    CCD2E_MASK_ADDR = 0x40644C00
    CCD2F_MASK_ADDR = 0x4064CC00
    CCD4E_MASK_ADDR = 0x40654C00
    CCD4F_MASK_ADDR = 0x4065CC00

    def __init__(self):
        self._bin_len = int((self.NROWS * self.NCOLS) / 8)
        self._bin = bytes(self._bin_len)

    @property
    def binary(self):
        return self._bin

    @binary.setter
    def binary(self, data: bytes):

        assert isinstance(data, bytes)
        assert len(data) == self._bin_len

        self._bin = data

    @property
    def array(self):
        return np.unpackbits(bytearray(self._bin)).reshape((self.NROWS, self.NCOLS))

    @array.setter
    def array(self, arr: np.ndarray):

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (self.NROWS, self.NCOLS)

        self._bin = bytes(np.packbits(arr))

    def mask_pixel(self, row, col):
        mask = self.array
        mask[row, col] = 1
        self.array = mask

    def unmask_pixel(self, row, col):
        mask = self.array
        mask[row, col] = 0
        self.array = mask


class RowColCorrection:

    ROW_CORR_ADDR = 0x40664C00
    COL_CORR_ADDR = 0x40665C00

    ROW_CORR_SIZE = 4096
    COL_CORR_SIZE = 2048

    def __init__(self):
        self._row_corr = bytearray(self.ROW_CORR_SIZE)
        self._col_corr = bytearray(self.COL_CORR_SIZE)

        self.ccd2_e_rows = bytearray(self.ROW_CORR_SIZE // 4)
        self.ccd2_f_rows = bytearray(self.ROW_CORR_SIZE // 4)
        self.ccd4_e_rows = bytearray(self.ROW_CORR_SIZE // 4)
        self.ccd4_f_rows = bytearray(self.ROW_CORR_SIZE // 4)

        self.ccd2_e_cols = bytearray(self.COL_CORR_SIZE // 4)
        self.ccd2_f_cols = bytearray(self.COL_CORR_SIZE // 4)
        self.ccd4_e_cols = bytearray(self.COL_CORR_SIZE // 4)
        self.ccd4_f_cols = bytearray(self.COL_CORR_SIZE // 4)

    @property
    def row_corr(self):
        self._row_corr[::4] = self.ccd4_e_rows
        self._row_corr[1::4] = self.ccd4_f_rows
        self._row_corr[2::4] = self.ccd2_e_rows
        self._row_corr[3::4] = self.ccd2_f_rows
        
        return bytes(self._row_corr)

    @row_corr.setter
    def row_corr(self, binary):
        assert len(binary) == self.ROW_CORR_SIZE
        self._row_corr = bytearray(binary)

        self.ccd4_e_rows = self._row_corr[::4]
        self.ccd4_f_rows = self._row_corr[1::4]
        self.ccd2_e_rows = self._row_corr[2::4]
        self.ccd2_f_rows = self._row_corr[3::4]

    @property
    def col_corr(self):
        self._col_corr[::4] = self.ccd4_e_cols
        self._col_corr[1::4] = self.ccd4_f_cols
        self._col_corr[2::4] = self.ccd2_e_cols
        self._col_corr[3::4] = self.ccd2_f_cols

        return bytes(self._col_corr)

    @col_corr.setter
    def col_corr(self, binary):
        assert len(binary) == self.COL_CORR_SIZE
        self._col_corr = bytearray(binary)

        self.ccd4_e_cols = self._col_corr[::4]
        self.ccd4_f_cols = self._col_corr[1::4]
        self.ccd2_e_cols = self._col_corr[2::4]
        self.ccd2_f_cols = self._col_corr[3::4]


if __name__ == '__main__':

    import matplotlib.pyplot as plt

    ct = CalibrationTables()
    ct._plot(Temp.ADC_TEMP_CCD)
    # ct.write_to_files('/home/marko/space/CCS/calibrations')
    lmt = LimitTables()
