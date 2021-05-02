#!/usr/bin/env python3
import os
import sys
sys.path.append(os.path.realpath('../../acceptance_tests/v0.6'))
import packets
import poolview_sql
import pus_datapool
from testlib import tools


def start_it(config, ccs, pool_name):
    poolview_sql.TMPoolView(cfg=config, ccs=ccs, pool_name=pool_name, standalone=True)


if __name__ == '__main__':

    # load the configuration file
    config = tools.read_config_file()
    # poolmanager
    poolmanager = pus_datapool.PUSDatapoolManager(config)
    # get a instance of ccs
    ccs = packets.CCScom(config, poolmanager)

    # delete the entries of table 'tm' in the database
    # num_del_rows = tm_db.truncate_tm_table()

    start_it(config=config, ccs=ccs, pool_name=None)
