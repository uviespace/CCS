#!/usr/bin/env python3

import datetime
import json
import sys
sys.path.insert(0, '..')

import ccs_function_lib as cfl
POOLNAME='BLA'

PY_CMD_STR = "cfl.Tcsend_DB"

TCL_CMD_STR = "tcsend {} {} checks ALL ackFlags 15"

TCL_PKT_VER_STR_subscr = 'subscribepacket {} referby {}'
TCL_PKT_VER_STR_syslog = 'waitfor {} -timeout {}\nsyslog "{} received"'
TCL_PKT_VER_STR_unsub = 'unsubscribepacket {}'

TCL_PKT_VER_STR = 'subscribepacket {} referby {}\nwaitfor {} -timeout {}\nsyslog "{} received"\nunsubscribepacket {}'

tclcode = 'TCLCODEDUMMY'

def get_cname(cdescr):
    try:
        descr, = cfl.scoped_session_idb.execute('select ccf_cname from ccf where ccf_descr="{}"'.format(cdescr)).fetchall()[0]
    except IndexError:
        descr = cdescr
    finally:
        cfl.scoped_session_idb.close()
    return descr

def get_tm_info(st, sst, pi1):
    return cfl.scoped_session_idb.execute('select pid_spid, pid_descr from pid where pid_type="{}" and pid_stype="{}" and pid_pi1_val="{}"'.format(st, sst, pi1)).fetchall()[0]

def build_tcl_cmd(cmd, *args, **kwargs):
    global tclcode
    cdescr, params, values = cfl.Tcbuild(cmd, *args, fmt='tcl', **kwargs)
    cname = get_cname(cdescr)

    ed_pars = [param for param in params if param[5] not in ['A', 'F']]
    if len(ed_pars) != len(values):
        raise ValueError('Wrong number of parameters: Expected {}, but got {}.\n{}'.format(len(ed_pars), len(values), ', '.join(x[10] for x in ed_pars)))


    pconfig = [(p[12], v) for p, v in zip(ed_pars, values)]
    pstr = ["{{{} {}}}".format(*pv) for pv in pconfig]

    tclcode = TCL_CMD_STR.format(cname, " ".join(pstr))
    return TCL_CMD_STR.format(cname, " ".join(pstr))

def build_tcl_pkt_ver(st, sst, pi1, wait=5.):

    spid, descr = get_tm_info(st, sst, pi1)

    subscr = TCL_PKT_VER_STR_subscr.format(spid, descr)
    syslog =  TCL_PKT_VER_STR_syslog.format(descr, wait, descr)
    unsub = TCL_PKT_VER_STR_unsub.format(spid)

    # return TCL_PKT_VER_STR_subscr.format(spid, descr, descr, wait, descr, spid)
    return subscr, syslog, unsub

def parse_json(fname):
    j = json.load(open(fname, 'r'))
    steps = j['sequences'][0]['steps']
    name = j.get('_name')
    descr = j.get('_description')
    return name, descr, steps

def _convert_tc(cmd):
    global tclcode
    cmd = cmd.replace(PY_CMD_STR, 'build_tcl_cmd')
    exec(cmd)
    print(tclcode)

    return tclcode

def _convert_ver(ver):
    ver = ver.split('\n')
    tmsub = []
    tmsys = []
    tmunsub = []

    for tmtc in ver:
        try:
            tm = _parse_tm(tmtc)
            if tm is not None:
                st, sst, pi1 = tm
                sub, syslog, unsub = build_tcl_pkt_ver(st, sst, pi1)
                tmsub.append(sub)
                tmsys.append(syslog)
                tmunsub.append(unsub)
        except:
            tmsub.append('# FAILED converting "{}"'.format(tmtc))
            tmsys.append('# FAILED converting "{}"'.format(tmtc))
            tmunsub.append('# FAILED converting "{}"'.format(tmtc))

    return '\n'.join(tmsub) + '\n\n' + '\n'.join(tmsys) + '\n\n' + '\n'.join(tmunsub)

def _parse_tm(tmtc):

    tm = tmtc.strip()
    if not tm.startswith('TM('):
        return

    res = tm.split('(')[1].split(')')[0].split(',')
    if len(res) == 3:
        st, sst, pi1 = res
    else:
        st, sst = res
        pi1 = 0

    return int(st), int(sst), int(pi1)

def _get_step_descr(step):
    nmb = '# {}'.format(step.get('_step_number'))
    descr = step.get('_description').split('\n')
    descr = '\n'.join(['# {}'.format(d) for d in descr])

    return nmb + '\n' + descr

def convert(fname):
    name, descr, jj = parse_json(fname)
    script = []

    script.append('# TCL script generated from {} on {}\n'.format(fname, datetime.datetime.isoformat(datetime.datetime.now(), timespec='seconds')))
    script.append('# {}'.format(name))
    script.append('# {}'.format(descr))

    for step in jj:

        try:
            script.append(_get_step_descr(step))
            cmd = step.get('_command_code')
            if cmd:
                script.append(_convert_tc(cmd))

            ver = step.get('_tmtc_comment')
            if ver:
                res = _convert_ver(ver)
                if res.strip():
                    script.append(res)
        except NotImplementedError:
            script.append('# AUTOMATIC CONVERSION OF STEP FAILED! MANUAL EDIT REQUIRED.')

    script = '\n\n'.join(script) + '\n'
    ofile = fname.replace('json', 'tcl')
    with open(ofile, 'w') as fd:
        fd.write(script)

        print('TCL written to', ofile)


if __name__ == '__main__':
    # fname = sys.argv[1]
    # convert(fname)
    convert('/home/marko/space/ariel/FSW/Documents/testspec/tst/BSW_FFT/BSW-SRV-17_1-TS-1.json')


# MemoryID16 = "MRAM"  # JA0H0124
# # N_16 = 1  # JA0H0042 [NOT EDITABLE]
# StartAddress = 0x80000  # JA0H0125
# Length = 8  # JA0H0123
# Data = b'DEADBEEF'  # JA0H0122
# tc=build_tcl_cmd('BSW_SetParamValue', 2818572294, 42, pool_name='LIVE')
# pass