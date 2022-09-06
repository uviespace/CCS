# SCOS 2000 PTC/PFC parameter format translation table

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
    7: {0: 'vOCT', 1: '1s', 12: '12s', 382: '382s'},
    8: {0: 'vASCII', 382: '382s'},
    9: {17: 'CUC917', 18: 'CUC918'},
    11: {0: 'deduced'},
    'SPARE': {8: '1x', 16: '2x', 24: '3x', 32: '4x'},
    'SPARE_visible': {8: 'B', 16: 'H', 24: 'I24', 32: 'I'},
    'PAD': {8: '1x', 16: '2x', 24: '3x', 32: '4x'}
}

ptype_parameters = ()

ptype_values = {}

DEFAULT_FORMATS = {
    1: {0: 'uint1'},
    2: {8: 'B', 16: 'H', 24: 'I24', 32: 'I'},
    3: {0: 'uint4', 1: 'uint5', 2: 'uint6', 3: 'uint7', 4: 'B', 5: 'uint9', 6: 'uint10', 7: 'uint11', 8: 'uint12',
        9: 'uint13', 10: 'uint14', 11: 'uint15', 12: 'H', 13: 'I24', 14: 'I'},
    4: {0: 'int4', 1: 'int5', 2: 'int6', 3: 'int7', 4: 'b', 5: 'int9', 6: 'int10', 7: 'int11', 8: 'int12',
        9: 'int13', 10: 'int14', 11: 'int15', 12: 'h', 13: 'i24', 14: 'i'},
    5: {1: 'f', 2: 'd'},
    6: {8: 'B', 16: 'H', 24: 'I24', 32: 'I'},
    7: {0: 'vOCT'},
    8: {0: 'vASCII'},
    9: {17: 'CUC917', 18: 'CUC918'},
    11: {0: 'deduced'},
    'SPARE': {8: '1x', 16: '2x', 24: '3x', 32: '4x'},
    'SPARE_visible': {8: 'B', 16: 'H', 24: 'I24', 32: 'I'},
    'PAD': {8: '1x', 16: '2x', 24: '3x', 32: '4x'}
}


class ParameterTypeLookupTable:

    def __call__(self, a, b):
        if a in DEFAULT_FORMATS:
            if b in DEFAULT_FORMATS[a]:
                return DEFAULT_FORMATS[a][b]
            else:
                if a in [2, 6]:
                    return 'uint{}'.format(b)
                elif a in [7, 8]:
                    return '{}s'.format(b)
                else:
                    raise NotImplementedError('(PTC, PFC) = ({}, {})'.format(a, b))
        else:
            raise NotImplementedError('PTC = {}'.format(a))


# ptt = ParameterTypeLookupTable()
