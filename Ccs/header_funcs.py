"""
Auxiliary functions for building PUS packet headers
"""
import importlib

from database import config_db
from database.tm_db import scoped_session_maker

import confignator

scoped_session_idb = scoped_session_maker('IDB', idb_version=config_db.idb_schema_name)
cfg = confignator.get_config(check_interpolation=False)
project = cfg.get('ccs-database', 'project')

PCPREFIX = 'packet_config_'
pc = importlib.import_module(PCPREFIX + str(project).upper())

try:
    SEQCNT_TAGS = pc.SEQCNT_TAGS
    PKTLEN_TAGS = pc.PKTLEN_TAGS
    SRCID_TAGS = pc.SRCID_TAGS

except AttributeError as err:
    SEQCNT_TAGS = ["SeqCnt"]
    PKTLEN_TAGS = ["PktLen"]
    SRCID_TAGS = ["SrcId"]


def get_tc_struct_from_mib(pktid, mib=None):

    if mib is not None:
        idb_session = scoped_session_maker('IDB', idb_version=mib)
    else:
        idb_session = scoped_session_idb

    que = 'SELECT pcdf_desc, pcdf_type, pcdf_len, pcdf_bit, pcdf_value, pcdf_radix from pcdf WHERE pcdf_tcname="{}" ORDER BY pcdf_bit'.format(pktid)
    res = idb_session.execute(que).fetchall()

    idb_session.close()

    return res


def _radix_num(x, radix):

    if radix == 'D':
        return int(x, 10)
    elif radix == 'H':
        return int(x, 16)
    elif radix == 'O':
        return int(x, 8)
    else:
        return int(x)


def mk_mib_pus_tc_header(pktid, apid=0, sc=0, pktl=0, ack=0, st=0, sst=0, srcid=0, mib=None):

    head_pars = get_tc_struct_from_mib(pktid, mib=mib)

    if not head_pars:
        raise ValueError('Could not find TC header definition for {}'.format(pktid))

    hdr = 0
    for pdesc, ptype, plen, pbit, pvalue, pradix in head_pars:

        if ptype == 'F':
            x = _radix_num(pvalue, pradix)
        elif ptype == 'A':
            x = apid
        elif ptype == 'K':
            x = ack
        elif ptype == 'T':
            x = st
        elif ptype == 'S':
            x = sst
        elif ptype == 'P':
            if pdesc in SEQCNT_TAGS:
                x = sc
            elif pdesc in PKTLEN_TAGS:
                x = pktl
            elif pdesc in SRCID_TAGS:
                x = srcid
            else:
                raise ValueError('Unknown header parameter "{}"'.format(pdesc))
        else:
            raise ValueError('Unknown header parameter type "{}"'.format(ptype))

        hdr = (hdr << plen) | (x & (2**plen - 1))

    return hdr.to_bytes((plen+pbit) // 8, 'big')
