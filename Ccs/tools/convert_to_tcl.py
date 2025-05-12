#!/usr/bin/env python3

import sys
sys.path.insert(0, '..')

import ccs_function_lib as cfl

TCL_CMD_STR = "tcsend {} {} checks ALL ackFlags 15"

TCL_PKT_VER_STR = 'subscribepacket {} referby {}\nwaitfor {} -timeout {}\nsyslog "{} received"\nunsubscribepacket {}'

def get_cname(cdescr):
    try:
        descr, = cfl.scoped_session_idb.execute('select ccf_cname from ccf where ccf_descr="{}"'.format(cdescr)).fetchall()[0]
    except IndexError:
        descr = cdescr
    finally:
        cfl.scoped_session_idb.close()
    return descr

def get_tm_info(st, sst, pi1):
    return cfl.scoped_session_idb.execute('select pid_spid from pid where pid_type="{}" and pid_stype="{}" and pid_pi1_val="{}"'.format(st, sst, pi1)).fetchall()[0]

def build_tcl_cmd(cmd, *args, **kwargs):

    cdescr, params, values = cfl.Tcbuild(cmd, *args, fmt='tcl', **kwargs)
    cname = get_cname(cdescr)

    ed_pars = [param for param in params if param[5] not in ['A', 'F']]
    if len(ed_pars) != len(values):
        raise ValueError('Wrong number of parameters: Expected {}, but got {}.\n{}'.format(len(ed_pars), len(values), ', '.join(x[10] for x in ed_pars)))


    pconfig = [(p[12], v) for p, v in zip(ed_pars, values)]
    pstr = ["{{{} {}}}".format(*pv) for pv in pconfig]

    return TCL_CMD_STR.format(cname, " ".join(pstr))

def build_tcl_pkt_ver(st, sst, pi1, wait=5.):

    spid, descr = get_tm_info(st, sst, pi1)

    return TCL_PKT_VER_STR.format(spid, descr, descr, wait, descr, spid)



# MemoryID16 = "MRAM"  # JA0H0124
# # N_16 = 1  # JA0H0042 [NOT EDITABLE]
# StartAddress = 0x80000  # JA0H0125
# Length = 8  # JA0H0123
# Data = b'DEADBEEF'  # JA0H0122
# tc=build_tcl_cmd('BSW_SetParamValue', 2818572294, 42, pool_name='LIVE')
# pass