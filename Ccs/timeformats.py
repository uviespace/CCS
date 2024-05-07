"""
Utilities for CUC time format definitions from SCOS2000 DB Import ICD
"""


class CUCAbsolute:

    ptc = 9

    def __init__(self, pfc, coarse, fine, res=None):
        self.pfc = int(pfc)
        self.nbytes_coarse_t = int(coarse)
        self.nbytes_fine_t = int(fine)
        self._custom_res = res

    @property
    def csize(self):
        return self.nbytes_coarse_t + self.nbytes_fine_t

    @property
    def t_res(self):
        if self._custom_res is None:
            return 2**(self.nbytes_fine_t * 8)
        else:
            return self._custom_res

    @property
    def name(self):
        return 'CUC{}{}'.format(self.ptc, self.pfc)

    def calc_time(self, tbytes):

        t = int.from_bytes(tbytes, 'big')
        ctime = t >> (self.nbytes_fine_t * 8)
        ftime = (t & (2**(self.nbytes_fine_t * 8) - 1)) / self.t_res if self.nbytes_fine_t > 0 else 0

        return ctime + ftime

    def calc_bytes(self, t):

        ctime = int(t)
        ftime = round(t % 1 * self.t_res)
        if ftime == self.t_res:
            ctime += 1
            ftime = 0

        return ctime.to_bytes(self.nbytes_coarse_t, 'big') + ftime.to_bytes(self.nbytes_fine_t, 'big')


class CUCRelative:

    ptc = 10


cuctime = {'CUC93': CUCAbsolute(3, 1, 0),
           'CUC94': CUCAbsolute(4, 1, 1),
           'CUC95': CUCAbsolute(5, 1, 2),
           'CUC96': CUCAbsolute(6, 1, 3),
           'CUC97': CUCAbsolute(7, 2, 0),
           'CUC98': CUCAbsolute(8, 2, 1),
           'CUC99': CUCAbsolute(9, 2, 2),
           'CUC910': CUCAbsolute(10, 2, 3),
           'CUC911': CUCAbsolute(11, 3, 0),
           'CUC912': CUCAbsolute(12, 3, 1),
           'CUC913': CUCAbsolute(13, 3, 2),
           'CUC914': CUCAbsolute(14, 3, 3),
           'CUC915': CUCAbsolute(15, 4, 0),
           'CUC916': CUCAbsolute(16, 4, 1),
           'CUC917': CUCAbsolute(17, 4, 2),
           'CUC918': CUCAbsolute(18, 4, 3)}

cuctime = cuctime
