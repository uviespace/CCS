"""
IWF EGSE communication library

Ref: SMILE-IWF-PL-IF-048
"""

PORT = 8089

EOP = b'\x0D\x0A'  # CR/LF

ERRORCODE = {
    b'\x30': 'Command OK',
    b'\x31': 'Parameter 1 NOT OK',
    b'\x32': 'Parameter 2 NOT OK',
    b'\x33': 'Parameter 3 NOT OK',
    b'\x34': 'Parameter 4 NOT OK',
    b'\x35': 'Parameter 5 NOT OK',
    b'\x36': 'Parameter 6 NOT OK',
    b'\x37': 'Command NOT ALLOWED',
    b'\x38': 'Command lenght NOT OK',
    b'\x39': 'Command UNKNOWN'
}

RESPONSE_ID = {
    b's': ('currentStatus', 10),
    b'x': ('execReset', 4),
    b'a': ('settledNewDelay', 4),
    b'b': ('handledErrorInjection', 4),
    b'c': ('settledRSERegValue', 4),
    b'd': ('receivedRSEData', 28),
    b'e': ('changedPSUReportPeriod', 4),
    b'f': ('settledPSUOK', 4),
    b'g': ('settledPSUAnalogueValue', 4),
    b'h': ('settledPWM', 4),
    b'k': ('newPSUStatus', 26),
    b'm': ('changedFEEReportPeriod', 4),
    b'n': ('newFEEStatus', 13),
    b'p': ('newFEEPWRStatus', 11),
    b'q': ('settledMaxLoads', 4),
    b'r': ('settledRSMEndSwitch', 4),
    b't': ('newRSMStatus', 13),
    b'u': ('newPSUEBOXStatus', 9),
    b'v': ('changedFEEPWRReportPeriod', 4),
    b'w': ('changedRSEReportPeriod', 4)
}


class Command:

    # GENERAL
    @staticmethod
    def get_status():
        """
        The general status of the IWF EGSE is requested with this command.

        :return:
        """

        return 'S'.encode('ascii') + EOP

    @staticmethod
    def reset():
        """
        The FPGA in the IWF_EGSE is reset.

        :return:
        """

        return 'X'.encode('ascii') + EOP

    ### DPU EGSE Interface ###
    # RSE
    @staticmethod
    def set_new_delay(delay):
        """
        RSE Interface
        With this command the delay between the received command and the generated response can be changed. (The default value after power-on is 2 baud)

        :param delay: Contains the 2Byte Unsigned-Integer as ASCII coded hexadecimal value to set
        :return:
        """

        delay = _hexasciify(delay, 4)

        return 'A'.encode('ascii') + delay.encode('ascii') + EOP

    @staticmethod
    def inject_errors(error_type, apply_to, num_errors, error_reg, error_resp, byte_sel):
        """
        With this command errors can be injected to the serial communication RSE - DPU (it can be used to abort the error injection, too).

        :param error_type: Selects the error type to inject
        :param apply_to: Selects when to apply error injection
        :param num_errors: Selects the number of errors to inject. Use '-1' to inject the error endless. Contains the 4Byte Signed-Integer as ASCII coded hexadecimal number.
        :param error_reg: Contains the defined address as 1Byte Unsigned-Integer as ASCII coded hexadecimal. Only used, if ApplyTO is 'defined address only'
        :param error_resp: Contains the error response as 1Byte Unsigned-Integer as ASCII coded hexadecimal. Only used, if ErrorType is “send an error response”
        :param byte_sel: Selects the bytes to inject frame or parity errors
        :return:
        """

        error_type = _hexasciify(error_type, 1)
        apply_to = _hexasciify(apply_to, 1)
        num_errors = _hexasciify(num_errors, 4, signed=True)
        error_reg = _hexasciify(error_reg, 2)
        error_resp = _hexasciify(error_resp, 2)
        byte_sel = _hexasciify(byte_sel, 1)

        params = ''.join([error_type, apply_to, num_errors, error_reg, error_resp, byte_sel])

        return 'B'.encode('ascii') + params.encode('ascii') + EOP

    @staticmethod
    def set_rse_reg_value(register_address, value):
        """
        A new value is set to a register address in the myRIO FPGA.

        :param register_address: Contains the 1Byte Unsigned-Integer as ASCII coded hexadecimal address of the register
        :param value:  Contains the 1Byte Unsigned-Integer as ASCII coded hexadecimal value to set
        :return:
        """

        register_address = _hexasciify(register_address, 2)
        value = _hexasciify(value, 2)

        params = ''.join([register_address, value])

        return 'C'.encode('ascii') + params.encode('ascii') + EOP

    # PSU
    @staticmethod
    def change_psu_report_period(newperiod):
        """
        The default report period of 1 second can be changed with this command.

        :param newperiod: Contains the new period in ms as 2Byte Unsigned-Integer as ASCII coded hexadecimal
        :return:
        """

        newperiod = _hexasciify(newperiod, 4)

        return 'E'.encode('ascii') + newperiod.encode('ascii') + EOP

    @staticmethod
    def set_psu_ok_signal(ok_signal, output):
        """
        The output of an IWF_EGSE_xxx_OK signal is set as selected with this command.

        :param ok_signal: Selects the signal
        :param output: Selects the value
        :return:
        """

        ok_signal = _hexasciify(ok_signal, 1)
        output = _hexasciify(output, 1)

        params = ''.join([ok_signal, output])

        return 'F'.encode('ascii') + params.encode('ascii') + EOP

    @staticmethod
    def set_psu_analogue_value(i_signal, output):
        """
        The analogue output IWF_EGSE_I_xxx is set as selected with this command.

        :param i_signal: Selects the signal
        :param output: Selects the value (lower 12Bits are used). Value as digital value in the range from 0 (≙ 0V) to 3276 (≙ 4V)
        :return:
        """

        ok_signal = _hexasciify(i_signal, 1)
        output = _hexasciify(output, 4)

        params = ''.join([ok_signal, output])

        return 'G'.encode('ascii') + params.encode('ascii') + EOP

    @staticmethod
    def set_pwm(thermistor, value):
        """
        The PWM for the OTA thermistor or CDD thermistor is as selected with this command. If no command is sent after a power-up, the PWM_MODE “automatic” is used by default.

        :param thermistor: Selects the thermistor
        :param value: Sets the current value for the PWM in thousandth (0 ≙ 0‰, 4000 ≙ 1000‰) as 2Byte Unsigned Integer, if mode is manual
        :return:
        """

        thermistor = _hexasciify(thermistor, 1)
        spare = '0'
        value = _hexasciify(value, 4)

        params = ''.join([thermistor, spare, value])

        return 'H'.encode('ascii') + params.encode('ascii') + EOP

    # FEE
    @staticmethod
    def change_fee_report_period(new_period):
        """
        The default report period of 1 second can be changed with this command.

        :param new_period: Contains the new period in ms as 2Byte Unsigned Int as ASCII coded hexadecimal
        :return:
        """

        new_period = _hexasciify(new_period, 4)

        return 'M'.encode('ascii') + new_period.encode('ascii') + EOP

    ### EBOX EGSE Interface ###
    # FEE Power
    @staticmethod
    def set_max_loads(ccd_max, an1_max, an2_max, an3_max, clk_max, dig_spw_max, dig_fpga_max):
        """
        The maximum loads at the LoadSim can be enabled or disabled with this command. If they are disabled, the nominal loads are active.

        :param ccd_max: Enables or disables the maximum load for IWF_EGSE_FEE_CCD
        :param an1_max: Enables or disables the maximum load for IWF_EGSE_FEE_AN1
        :param an2_max: Enables or disables the maximum load for IWF_EGSE_FEE_AN2
        :param an3_max: Enables or disables the maximum load for IWF_EGSE_FEE_AN3
        :param clk_max: Enables or disables the maximum load for IWF_EGSE_FEE_CLK
        :param dig_spw_max: Enables or disables the maximum load for IWF_EGSE_FEE_DIG_SPW
        :param dig_fpga_max: Enables or disables the maximum load for IWF_EGSE_FEE_DIG_FPGA
        :return:
        """

        spare = '0'

        ccd_max = _hexasciify(ccd_max, 1)
        an1_max = _hexasciify(an1_max, 1)
        an2_max = _hexasciify(an2_max, 1)
        an3_max = _hexasciify(an3_max, 1)
        clk_max = _hexasciify(clk_max, 1)
        dig_spw_max = _hexasciify(dig_spw_max, 1)
        dig_fpga_max = _hexasciify(dig_fpga_max, 1)

        params = ''.join([spare, ccd_max, an1_max, an2_max, an3_max, clk_max, dig_spw_max, dig_fpga_max])

        return 'Q'.encode('ascii') + params.encode('ascii') + EOP

    @staticmethod
    def change_fee_pwr_report_period(new_period):
        """
        The default report period of 1 second can be changed with this command.

        :param new_period: Contains the new period in ms as 2Byte Unsigned Int as ASCII coded hexadecimal
        :return:
        """

        new_period = _hexasciify(new_period, 4)

        return 'V'.encode('ascii') + new_period.encode('ascii') + EOP

    # RSM
    @staticmethod
    def change_rsm_report_period(new_period):
        """
        The default report period of 1 second can be changed with this command.

        :param new_period: Contains the new period in ms as 2Byte Unsigned Int as ASCII coded hexadecimal
        :return:
        """

        new_period = _hexasciify(new_period, 4)

        return 'W'.encode('ascii') + new_period.encode('ascii') + EOP

    @staticmethod
    def set_rsm_end_switch(open_pos, close_pos):
        """
        The end switches (open or close) can be set with this command.

        :param open_pos: Enables or disables the signal IWF_EGSE_OPEN_POS
        :param close_pos: Enables or disables the signal IWF_EGSE_CLOSE_POS
        :return:
        """

        open_pos = _hexasciify(open_pos, 1)
        close_pos = _hexasciify(close_pos, 1)

        params = ''.join([open_pos, close_pos])

        return 'R'.encode('ascii') + params.encode('ascii') + EOP


class Response:
    pass


def _hexasciify(value, nchars, signed=False):
    """
    Returns an int as a hexadecimal string of length *nchars*

    :param value:
    :param nchars:
    :return:
    """
    if isinstance(value, int):
        if signed:
            return value.to_bytes(nchars // 2, 'big', signed=True).hex().upper()
        else:
            return '{:0{nc}X}'.format(value, nc=nchars)
    else:
        return value


def response_proc_func(rawdata):
    pkts = rawdata.split(EOP)
    pkts.remove(b'')
    proc_pkts = [(RESPONSE_ID.get(pkt[0:1], 'UKNOWN'), pkt.decode('ascii', errors='replace')) for pkt in pkts]
    return proc_pkts
