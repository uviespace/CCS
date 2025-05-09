# SCOS 2000 PTC/PFC parameter format translation table

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
    7: {},  # 0: 'vOCT'},
    8: {},  # 0: 'vASCII'},
    9: {17: 'CUC917', 18: 'CUC918'},
    11: {0: 'deduced'},
    'SPARE': {8: '1x', 16: '2x', 24: '3x', 32: '4x'},
    'SPARE_visible': {8: 'B', 16: 'H', 24: 'I24', 32: 'I'},
    'PAD': {8: '1x', 16: '2x', 24: '3x', 32: '4x'}
}


class ParameterTypeLookupTable:

    def __call__(self, ptc, pfc):
        if ptc in DEFAULT_FORMATS:
            if pfc in DEFAULT_FORMATS[ptc]:
                return DEFAULT_FORMATS[ptc][pfc]
            elif pfc == 0:
                raise NotImplementedError('(PTC, PFC) = ({}, {})'.format(ptc, pfc))
            else:
                if ptc in [2, 6]:
                    if pfc > 32:
                        raise NotImplementedError('(PTC, PFC) = ({}, {})'.format(ptc, pfc))
                    return 'uint{}'.format(pfc)
                elif ptc == 7:
                    return 'oct{}'.format(pfc)
                elif ptc == 8:
                    return 'ascii{}'.format(pfc)
                else:
                    raise NotImplementedError('(PTC, PFC) = ({}, {})'.format(ptc, pfc))
        else:
            raise NotImplementedError('PTC = {}'.format(ptc))


class ParameterTypeLookupTableReverse:

    _special_fmts = {'B': (3, 4),
                     'H': (3, 12),
                     'I24': (3, 13),
                     'I': (3, 14)}

    def __init__(self):
        self._reverse_dict = dict()
        for ptc in DEFAULT_FORMATS:
            if isinstance(ptc, int):
                for pfc in DEFAULT_FORMATS[ptc]:
                    if DEFAULT_FORMATS[ptc][pfc] in self._special_fmts:
                        self._reverse_dict[DEFAULT_FORMATS[ptc][pfc]] = self._special_fmts[DEFAULT_FORMATS[ptc][pfc]]
                    else:
                        self._reverse_dict[DEFAULT_FORMATS[ptc][pfc]] = (ptc, pfc)

    def __call__(self, fmt):
        try:
            if fmt in self._reverse_dict:
                return self._reverse_dict[fmt]
            elif fmt.startswith('uint'):
                if int(fmt[4:]) > 32:
                    raise NotImplementedError('Format {} not supported'.format(fmt))
                return tuple((6, int(fmt[4:])))
            elif fmt.startswith('bit'):
                if int(fmt[3:]) > 32:
                    raise NotImplementedError('Format {} not supported'.format(fmt))
                return tuple((6, int(fmt[3:])))
            elif fmt.startswith('oct'):
                return tuple((7, int(fmt[3:])))
            elif fmt.startswith('ascii'):
                return tuple((8, int(fmt[5:])))
            else:
                raise NotImplementedError('Format {} not supported'.format(fmt))
        except ValueError:
            raise NotImplementedError('Format {} not supported'.format(fmt))


ptt = ParameterTypeLookupTable()
ptt_reverse = ParameterTypeLookupTableReverse()
