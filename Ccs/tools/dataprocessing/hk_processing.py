import ctypes
import io
import logging
import os
import struct
import packetstruct as pstruct
from packetstruct import timepack, timecal, APID, TM_HEADER_LEN, PEC_LEN, PI1W
from s2k_partypes import ptt
import timeformats

MIBDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mib')
PIC_TAB = os.path.join(MIBDIR, 'pic.dat')
PID_TAB = os.path.join(MIBDIR, 'pid.dat')
PLF_TAB = os.path.join(MIBDIR, 'plf.dat')
VPD_TAB = os.path.join(MIBDIR, 'vpd.dat')
PCF_TAB = os.path.join(MIBDIR, 'pcf.dat')


def str_to_int(x):
    if x == '':
        return 0
    else:
        return int(x)


class PktStructs:

    def __init__(self):
        self.pus_tabs = PusTabs()
        self.structs = {}

    def __call__(self, *args, **kwargs):
        return

    def mk_struct(self, key):
        spid, pktdescr, tpsd = self.pus_tabs.pid[key]

        fmts = []
        params = []

        if tpsd == -1:
            # only try if there are any parameters defined
            if spid in self.pus_tabs.plf:
                for plf in self.pus_tabs.plf[spid]:
                    name, offby, offbi = plf
                    descr, ptc, pfc, _ = self.pus_tabs.pcf[name]
                    fmts.append(ptt(ptc, pfc))
                    params.append((name, descr, offby, offbi, ptc, pfc))
        else:
            for vpd in self.pus_tabs.vpd[spid]:
                pos, name, grp, fixrep = vpd
                descr, ptc, pfc, width = self.pus_tabs.pcf[name]
                params.append((name, descr, ptc, pfc, None, width, grp, fixrep))

        pktstruct = {'pktdescr': pktdescr, 'fmts': fmts, 'params': params, 'tpsd': tpsd}

        return pktstruct

    def get_struct(self, key):
        if key not in self.structs:
            self.structs[key] = self.mk_struct(key)

        return self.structs[key]


class PusTabs:

    def __init__(self):

        self.pic = self.load_table(PIC_TAB)
        self.pid = self.load_table(PID_TAB)
        self.plf = self.load_table(PLF_TAB)
        self.vpd = self.load_table(VPD_TAB)
        self.pcf = self.load_table(PCF_TAB)

    def load_table(self, fname):

        with open(fname, 'r') as fd:
            lines = fd.readlines()

        lines = [x.strip('\n').split('\t') for x in lines]

        if fname == PIC_TAB:
            lines = {tuple(map(int, x[:2])): int(x[2]) for x in lines}
        elif fname == PID_TAB:
            lines = {(tuple(x[:4])): [int(x[5]), x[6], int(x[8])] for x in lines}
        elif fname == PLF_TAB:
            ldict = {}
            for line in lines:
                x = int(line[1])
                if x in ldict:
                    ldict[x].append((line[0], int(line[2]), int(line[3])))
                else:
                    ldict[x] = [(line[0], int(line[2]), int(line[3]))]

            for k in ldict:
                ldict[k].sort(key=lambda x: (x[1], x[2]))
            lines = ldict

        elif fname == VPD_TAB:
            ldict = {}
            for line in lines:
                x = int(line[0])
                if x in ldict:
                    ldict[x].append((int(line[1]), line[2], str_to_int(line[3]), str_to_int(line[4])))
                else:
                    ldict[x] = [(int(line[1]), line[2], str_to_int(line[3]), str_to_int(line[4]))]

            for k in ldict:
                ldict[k].sort(key=lambda x: x[0])
            lines = ldict
        elif fname == PCF_TAB:
            lines = {x[0]: [x[1], int(x[4]), int(x[5]), int(x[6])] for x in lines}

        return lines


pkt_structs = PktStructs()
# print(1)


def proc_hk(pkt):

    timestamp = timecal(pkt[pstruct.CUC_OFFSET:pstruct.CUC_OFFSET + pstruct.timepack[1]], string=False)

    pktkey, pktstruct = get_struct(pkt)
    if pktstruct is not None:
        descr, ps, fmts, var = pktstruct['pktdescr'], pktstruct['params'], pktstruct['fmts'], pktstruct['tpsd']
    else:
        procpkt = pkt[TM_HEADER_LEN:-PEC_LEN]
        return pktkey, None, procpkt, timestamp, False

    try:
        if var == -1:
            procpkt = (var, ps, decode_pus(pkt[TM_HEADER_LEN:-PEC_LEN], ps, fmts), fmts)
        else:
            procpkt = (var, ps, read_variable_pckt(pkt[TM_HEADER_LEN:-PEC_LEN], ps), fmts)
        decoded = True
    except Exception as err:
        logging.warning("Decoding failed for {}".format(descr))
        procpkt = pkt[TM_HEADER_LEN:-PEC_LEN]
        decoded = False

    return pktkey, descr, procpkt, timestamp, decoded


def get_struct(pkt):
    pi1val = 0
    st, sst = pkt[pstruct.ST_OFF], pkt[pstruct.SST_OFF]

    if (st, sst) not in pkt_structs.pus_tabs.pic:
        return None, None

    if pkt_structs.pus_tabs.pic[(st, sst)] != -1:
        pi1off = int(pkt_structs.pus_tabs.pic[(st, sst)])
        pi1val = int.from_bytes(pkt[pi1off:pi1off + PI1W], 'big')

    key = (str(st), str(sst), str(APID), str(pi1val))

    try:
        pktstruct = pkt_structs.get_struct(key)
    except Exception as err:
        pktstruct = None

    return key, pktstruct


def read_variable_pckt(tm_data, parameters):
    """
    Read parameters from a variable length packet

    :param tm_data:
    :param parameters:
    :return:
    """
    tms = io.BytesIO(tm_data)
    result = []

    result = read_stream_recursive(tms, parameters, decoded=result)

    return result


def read_stream_recursive(tms, parameters, decoded=None, bit_off=0):
    """
    Recursively operating function for decoding variable length packets

    :param tms:
    :param parameters:
    :param decoded:
    :param bit_off:
    :param tc:
    :return:
    """

    decoded = [] if decoded is None else decoded

    skip = 0
    for par_idx, par in enumerate(parameters):
        if skip > 0:
            skip -= 1
            continue
        grp = par[-2]

        if grp is None:  # None happens for UDEF
            grp = 0

        fmt = ptt(par[2], par[3])
        if fmt == 'deduced':
            raise NotImplementedError('Deduced parameter type PTC=11')

        fixrep = par[-1]

        # don't use fixrep in case of a TC, since it is only defined for TMs
        if grp and fixrep:
            value = fixrep
            # logger.debug('{} with fixrep={} used'.format(par[1], value))
        else:
            bits = par[5]
            unaligned = bits % 8

            value = read_stream(tms, fmt, offbi=bit_off)

            bit_off = (bit_off + unaligned) % 8
            # re-read byte if read position is bit-offset after previous parameter
            if bit_off:
                tms.seek(tms.tell() - 1)

            decoded.append((value, par))

        if grp != 0:
            skip = grp
            rep = value
            while rep > 0:
                decoded = read_stream_recursive(tms, parameters[par_idx + 1:par_idx + 1 + grp], decoded, bit_off=bit_off)
                rep -= 1

    return decoded


def read_stream(stream, fmt, pos=None, offbi=0, none_on_fail=False):
    """

    :param stream:
    :param fmt:
    :param pos:
    :param offbi:
    :return:
    """
    if pos is not None:
        stream.seek(int(pos))

    readsize = csize(fmt, offbi)
    data = stream.read(readsize)

    if not data:
        if none_on_fail:
            # logger.debug('No data left to read from [{}]!'.format(fmt))
            return
        else:
            raise BufferError('No data left to read from [{}]!'.format(fmt))

    if fmt == 'I24':
        x = int.from_bytes(data, 'big')
    elif fmt == 'i24':
        x = int.from_bytes(data, 'big', signed=True)
    # for bit-sized unsigned parameters:
    elif fmt.startswith('uint'):
        bitlen = int(fmt[4:])
        # bitsize = (bitlen // 8 + 1) * 8
        bitsize = len(data) * 8
        x = (int.from_bytes(data, 'big') & (2 ** (bitsize - offbi) - 1)) >> (bitsize - offbi - bitlen)
    elif fmt.startswith('oct'):
        x = struct.unpack('>{}s'.format(fmt[3:]), data)[0]
    elif fmt.startswith('ascii'):
        x = struct.unpack('>{}s'.format(fmt[5:]), data)[0]
        try:
            x = x.decode('ascii')
        except UnicodeDecodeError as err:
            # logger.warning(err)
            x = x.decode('utf-8', errors='replace')
    elif fmt == timepack[0]:
        x = timecal(data)
    elif fmt.startswith('CUC'):
        x = timeformats.cuctime.get(fmt).calc_time(data)
    else:
        x = struct.unpack('>' + fmt, data)[0]

    return x


def csize(fmt, offbi=0):
    """
    Returns the amount of bytes required for the input format

    :param fmt: Input String that defines the format
    :param offbi:
    :return:
    """

    if fmt in ('i24', 'I24'):
        return 3
    elif fmt.startswith('uint'):
        return (int(fmt[4:]) + offbi - 1) // 8 + 1
    elif fmt == timepack[0]:
        return timepack[1] - timepack[3]
    elif fmt.startswith('CUC'):
        try:
            return timeformats.cuctime.get(fmt).cize
        except AttributeError:
            raise NotImplementedError('Unknown format {}'.format(fmt))
    elif fmt.startswith('oct'):
        return int(fmt[3:])
    elif fmt.startswith('ascii'):
        return int(fmt[5:])
    else:
        try:
            return struct.calcsize(fmt)
        except struct.error:
            raise NotImplementedError('Unknown format {}'.format(fmt))


def decode_pus(tm_data, parameters, fmts):
    """

    :param tm_data:
    :param parameters:
    :param fmts:
    :return:
    """
    # fmts = [ptt(par[4], par[5]) for par in parameters]

    try:
        # return list(zip(struct.unpack('>' + ''.join(fmts), tm_data), parameters))
        return struct.unpack('>' + ''.join(fmts), tm_data)
    except struct.error:
        tms = io.BytesIO(tm_data)
        return [read_stream(tms, fmt, pos=par[2] - TM_HEADER_LEN, offbi=par[3]) for fmt, par in zip(fmts, parameters)]
        # return [(read_stream(tms, fmt, pos=par[2] - TM_HEADER_LEN, offbi=par[3]), par) for fmt, par in zip(fmts, parameters)]
