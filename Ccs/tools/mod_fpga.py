#!/usr/bin/env python3
"""
Set ADC values in FPGA file read out by SMILE SXI simulator.
"""

import sys

FPGA_FILE = 'FPGA.bin'

ADC_ADDR = {"ADC_P3V3_LVDS": 0x0102,
            "ADC_P3V9": 0x0100,
            "ADC_P2V5": 0x0106,
            "ADC_P3V3": 0x0104,
            "ADC_P1V2": 0x010A,
            "ADC_P1V8": 0x0108,
            "ADC_TEMP_DPU": 0x010E,
            "ADC_REF_2V5": 0x010C,
            "ADC_TEMP_CCD": 0x0112,
            "ADC_TEMP_FEE": 0x0110,
            "ADC_I_FFE_DIG": 0x0116,
            "ADC_I_FFE_ANA": 0x0114,
            "ADC_I_RSE": 0x011A,
            "ADC_I_DPU": 0x0118,
            "ADC_PSU_TEMP": 0x011E,
            "ADC_I_HEATER": 0x011C}


def wr_fpga(addr, val, bsize=2):
    with open(FPGA_FILE, 'r+b') as fd:
        fd.seek(addr)
        fd.write(val.to_bytes(bsize, 'little'))


if __name__ == '__main__':

    if len(sys.argv) < 3:
        print('Usage: sudo ./mod_fpga.py <ADDR|ADC_NAME> <VALUE>')
        print('ADC_NAME can be one of the following:\n\t{}'.format('\n\t'.join([k for k in ADC_ADDR])))
        sys.exit()
        
    addr, val = sys.argv[1:3]

    if addr.strip() in ADC_ADDR:
        addr = ADC_ADDR[addr.strip()]
    else:
        addr = int(addr, 0)

    wr_fpga(addr, int(val, 0))

