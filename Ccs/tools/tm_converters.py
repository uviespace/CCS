#! /usr/bin/env python3

import io
import sys
sys.path.insert(0, '..')

from database.tm_db import connect_to_db

dbcon = connect_to_db()


def merge_pools(*args, outfile=None, time_sort=False):
    """
    Merge binary TM pools with optional sorting by timestamp
    @param args:
    @param outfile:
    @param time_sort:
    """
    pcktdata = b''.join((open(tmpool, 'rb').read() for tmpool in args))
    if outfile is None:
        outfile = 'merged_pools.tmpool'

    if not time_sort:
        with open(outfile, 'wb') as fd:
            fd.write(pcktdata)
        print('>> TM packets written to {} <<'.format(outfile))
        return
    else:
        print('TIME SORTING NOT YET IMPLEMENTED FOR SMILE')
        return

    pcktstream = io.BytesIO(pcktdata)

    pckts_list = []
    pkt = True
    while pkt is not None:
        pkt = read_pus(pcktstream)
        if pkt is not None:
            pckts_list.append(pkt)

    pckts_list.sort(key=lambda x: get_cuc(x))
    with open(outfile, 'wb') as fd:
        fd.write(b''.join(pckts_list))

    print('>> TM packets written to {}, SORTED BY TIMESTAMP <<'.format(outfile))


def read_pus(data):
    pos = data.tell()
    pus_size = data.read(6)

    if pus_size == b'':
        return

    while len(pus_size) < 6:
        add = data.read(1)
        if add == b'':
            return
        pus_size += add

    data.seek(pos)

    # packet size is header size (6) + pus size field + 1
    pckt_size = int.from_bytes(pus_size[4:6], 'big') + 7

    return data.read(pckt_size)


"""
def get_cuc(tm):
    try:
        ct, ft = struct.unpack('>IH', tm[10:16])
        ft >>= 1
        return ct + ft / 2 ** 15
    except IndexError:
        return -1.
"""


def ha_to_tmpool(filename, save=True, encoding='utf-8'):
    with open(filename, 'r', encoding=encoding) as fd:
        pckts = (line for line in fd.read().split('\n') if not line.startswith('<'))
        tmpool = bytes.fromhex(''.join(pckts))

    # for x in data.split('<LENGTH>')[1:]:
    #     i = x.index('\n')
    #     try:
    #         j = x.index('<REC_DATE>')
    #     except ValueError:
    #         j = x.index('<END_DATA_BLOCK>')
    #     pckts.append(bytes.fromhex(x[i + 1:j].replace('\n', '')))

    if save:
        if isinstance(save, str):
            with open(save, 'wb') as fd:
                fd.write(tmpool)
        else:
            with open(filename + '.tmpool', 'wb') as fd:
                fd.write(tmpool)
                save = fd.name
        return save
    else:
        return tmpool


def _get_cdescr(cname):
    try:
        descr, = dbcon.execute('select ccf_descr from ccf where ccf_cname="{}"'.format(cname)).fetchall()[0]
    except IndexError:
        descr = cname
    finally:
        dbcon.close()
    return descr


def _get_piddescr(pcf_name):
    try:
        descr, = dbcon.execute('select pcf_descr from pcf where pcf_name="{}"'.format(pcf_name)).fetchall()[0]
    except IndexError:
        descr = pcf_name
    finally:
        dbcon.close()
    return descr


def _cuc_to_bytes(cuc, sync='U'):
    if isinstance(cuc, str):
        sync = cuc[-1]
        cuc = float(cuc[:-1])
    coarse = int(cuc)
    fine = int((cuc % 1) * 2 ** 15)
    if sync.upper() == 'S':
        sync = '1'
    else:
        sync = '0'
    c = coarse.to_bytes(4, 'big')
    f = int(bin(fine) + sync, 0).to_bytes(2, 'big')
    return c + f


def _add_quotes(s):
    if isinstance(s, str):
        s = '"' + s + '"'
    return s


def _tc_string(descr, pars=None, ack=None, prefix='ccs.Tcsend_DB', sleep=None):
    if descr.startswith(('ASC', 'CSC', 'RSC')):
        if sleep is None:
            sleep = ''
        else:
            sleep = 'time.sleep({:.3f})'.format(sleep)
        return '# {}\n{}'.format(descr, sleep)
    if ack is None:
        ack = ''
    else:
        ack = ', ack="{}"'.format(ack)
    if sleep is None:
        sleep = ''
    else:
        sleep = ', sleep={:.3f}'.format(sleep)
    pars = ', '.join(map(str, map(_add_quotes, pars)))
    if pars != '':
        pars = ', ' + pars
    return '{}("{}"{}{}{})'.format(prefix, descr, pars, ack, sleep)


def convert_ssf(filename, outfile=None, cmdprefix='ccs.Tcsend_DB'):
    with open(filename, 'r') as fd:
        data = fd.read().split('\n')
        data.remove('')

    nrows = len(data)
    idx = 0
    seq = 1
    cmds = {}
    base_header = ''

    while idx < nrows:
        row = data[idx]
        if not row.startswith('C|'):
            if row.startswith('1|'):
                base_header += row
            idx += 1
            continue
        head = row.split('|')
        cname = head[1]
        npars = int(head[13])
        ack = bin(int(head[26]))
        timestamp = float('.'.join(head[16:18]))
        descr = _get_cdescr(cname)
        cmds[seq] = {'CNAME': cname, 'DESCR': descr, 'ack': ack, 'timestamp': timestamp}
        parameters = []
        for i in range(npars):
            idx += 1
            par_data = data[idx].split('|')
            if int(par_data[2]) in (0, 1):
                value = int(par_data[5])
            elif int(par_data[2]) in (2, 3):
                value = float(par_data[5])
            elif int(par_data[2]) == 4:
                value = str(par_data[5])
            elif int(par_data[2]) == 5:
                value = bytes.fromhex(par_data[5])
            elif int(par_data[2]) == 7:
                time = par_data[5].replace(' ', '.')
                value = _cuc_to_bytes(time)
            elif int(par_data[2]) == 14:
                value = _get_piddescr(par_data[5])
            else:
                value = par_data[5]
            parameters.append(value)
        if npars != len(parameters):
            print(">>> {} parameters found, should be {} [{}]! <<<".format(len(parameters), npars, cname))
        if descr.startswith('DPU_IFSW_UPDT_PAR_'):
            dtype = 'TYPE_' + descr.split('_')[-1]
            for i in range(parameters[0]):
                parameters.insert(2 + (i * 4), dtype)
        cmds[seq]['parameters'] = parameters
        idx += 1
        seq += 1

    script_cmds = []
    for seq in range(1, len(cmds) + 1):
        data = cmds[seq]
        if seq < len(cmds):
            sleep = cmds[seq + 1]['timestamp'] - cmds[seq]['timestamp']
            if sleep < 0:
                print('>>> Negative timestamp difference between commands {} & {} ({:.3f}s)! Setting sleep to 0. <<<'.
                      format(seq, seq + 1, sleep))
                sleep = 0
        else:
            sleep = None
        comment = '# CMD {:d} [{:.6f}]\n'.format(seq, cmds[seq]['timestamp'])
        script_cmds.append(comment + _tc_string(data['DESCR'], data['parameters'], ack=data['ack'], sleep=sleep,
                                                prefix=cmdprefix))

    header = "# Commands generated from file: {}\n".format(filename.split('/')[-1])
    script = header + '# Base header: {}\n\n'.format(base_header) + '\n\n'.join(script_cmds) + '\n'

    if outfile is None:
        outfile = filename[:-4] + '_CCS.py'

    with open(outfile, 'w') as fd:
        fd.write(script)

    return outfile
