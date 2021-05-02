import configparser
import pus_datapool
import packets
import poolview_sql

poolname = "TM"

# Load the config file
cfgfile = "egse.cfg"
cfg = configparser.ConfigParser()
cfg.read(cfgfile)
cfg.source = cfgfile

poolmgr = pus_datapool.PUSDatapoolManager(cfg)

ccs = packets.CCScom(cfg, poolmgr)

h = poolmgr.connect_socket(poolname, '127.0.0.1', 5570)
poolmgr.connect_tc(poolname, '127.0.0.1', 5571)

pv = poolview_sql.TMPoolView(cfg)
pv.set_ccs(ccs)
pv.set_pool(poolname)

import sys
import os
# Add the current ccs path. Thus Python can find the modules.
sys.path.append(os.path.realpath('../../acceptance_tests/v0.6'))

import subprocess
import IASW_39
subprocess.Popen('IASW_39.IntegrationTestIasw39().run(ccs=ccs, pool_name=poolname)',stdin=None, stderr=None, stdout=None)

import threads
thread.start_new_thread(IASW_39.IntegrationTestIasw39().run(ccs=ccs, pool_name=poolname), ())

import subprocess
cmd1 = 'xfce4-terminal --title="test" --working-directory="../../IFSW/acceptance_tests/v0.6" -e "python3 IASW_39.py"'
test = subprocess.Popen("exec " + cmd1, stdin=None, stdout=None, stderr=None, shell=True)


from multiprocessing import Process
p = Process(IASW_39.IntegrationTestIasw39().run(ccs=ccs, pool_name=poolname))
p.start()


