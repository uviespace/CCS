# SCOS 2000 PTC/PFC parameter format translation table

ptt_legacy = {
    1: {0: 'bit1'},
    2: {1: 'bit1', 2: 'bit2', 3: 'bit3', 4: 'bit4', 5: 'bit5', 6: 'bit6', 7: 'bit7', 8: 'B', 9: 'bit9', 10: 'bit10',
        11: 'bit11', 12: 'bit12', 13: 'bit13', 14: 'bit14', 15: 'bit15', 16: 'H', 17: 'bit17', 18: 'bit18',
        19: 'bit19', 20: 'bit20', 21: 'bit21', 22: 'bit22', 23: 'bit23', 24: 'I24', 25: 'bit25', 26: 'bit26',
        27: 'bit27', 28: 'bit28', 29: 'bit29', 30: 'bit30', 31: 'bit31', 32: 'I'},
    3: {0: 'bit4', 1: 'bit5', 2: 'bit6', 3: 'bit7', 4: 'B', 5: 'bit9', 6: 'bit10', 7: 'bit11', 8: 'bit12',
        9: 'bit13', 10: 'bit14', 11: 'bit15', 12: 'H', 13: 'I24', 14: 'I'},
    4: {0: 'sbit4', 1: 'sbit5', 2: 'sbit6', 3: 'sbit7', 4: 'b', 5: 'sbit9', 6: 'sbit10', 7: 'sbit11', 8: 'sbit12',
        9: 'sbit13', 10: 'sbit14', 11: 'sbit15', 12: 'h', 13: 'i24', 14: 'i'},
    5: {1: 'f', 2: 'd'},
    6: {1: 'bit1', 2: 'bit2', 3: 'bit3', 4: 'bit4', 5: 'bit5', 6: 'bit6', 7: 'bit7', 8: 'B', 9: 'bit9', 10: 'bit10',
        11: 'bit11', 12: 'bit12', 13: 'bit13', 14: 'bit14', 15: 'bit15', 16: 'H', 17: 'bit17', 18: 'bit18',
        19: 'bit19', 20: 'bit20', 21: 'bit21', 22: 'bit22', 23: 'bit23', 24: 'I24', 25: 'bit25', 26: 'bit26',
        27: 'bit27', 28: 'bit28', 29: 'bit29', 30: 'bit30', 31: 'bit31', 32: 'I'},
    7: {0: 'vOCT', 382: '382s'},
    8: {0: 'vASCII', 382: '382s'},
    9: {17: 'CUC917'},
    11: {0: 'deduced'}
}

ptt = {
    1: {0: 'uint1'},
    2: {1: 'uint1', 2: 'uint2', 3: 'uint3', 4: 'uint4', 5: 'uint5', 6: 'uint6', 7: 'uint7', 8: 'B', 9: 'uint9', 10: 'uint10',
        11: 'uint11', 12: 'uint12', 13: 'uint13', 14: 'uint14', 15: 'uint15', 16: 'H', 17: 'uint17', 18: 'uint18',
        19: 'uint19', 20: 'uint20', 21: 'uint21', 22: 'uint22', 23: 'uint23', 24: 'I24', 25: 'uint25', 26: 'uint26',
        27: 'uint27', 28: 'uint28', 29: 'uint29', 30: 'uint30', 31: 'uint31', 32: 'I'},
    3: {0: 'uint4', 1: 'uint5', 2: 'uint6', 3: 'uint7', 4: 'B', 5: 'uint9', 6: 'uint10', 7: 'uint11', 8: 'uint12',
        9: 'uint13', 10: 'uint14', 11: 'uint15', 12: 'H', 13: 'I24', 14: 'I'},
    4: {0: 'int4', 1: 'int5', 2: 'int6', 3: 'int7', 4: 'b', 5: 'int9', 6: 'int10', 7: 'int11', 8: 'int12',
        9: 'int13', 10: 'int14', 11: 'int15', 12: 'h', 13: 'i24', 14: 'i'},
    5: {1: 'f', 2: 'd'},
    6: {1: 'uint1', 2: 'uint2', 3: 'uint3', 4: 'uint4', 5: 'uint5', 6: 'uint6', 7: 'uint7', 8: 'B', 9: 'uint9', 10: 'uint10',
        11: 'uint11', 12: 'uint12', 13: 'uint13', 14: 'uint14', 15: 'uint15', 16: 'H', 17: 'uint17', 18: 'uint18',
        19: 'uint19', 20: 'uint20', 21: 'uint21', 22: 'uint22', 23: 'uint23', 24: 'I24', 25: 'uint25', 26: 'uint26',
        27: 'uint27', 28: 'uint28', 29: 'uint29', 30: 'uint30', 31: 'uint31', 32: 'I'},
    7: {0: 'vOCT', 1: 'placeholder', 12: 'placeholder', 382: '382s'},
    8: {0: 'vASCII', 382: '382s'},
    9: {17: 'CUC917', 18: 'CUC918'},
    11: {0: 'deduced'},
    'SPARE': {8: '1x', 16: '2x', 24: '3x', 32: '4x'},
    'SPARE_visible': {8: 'B', 16: 'H', 24: 'I24', 32: 'I'},
    'PAD': {8: '1x', 16: '2x', 24: '3x', 32: '4x'}
}

ptype_parameters = ()

ptype_values = {}

# from packet_config_SMILE import *