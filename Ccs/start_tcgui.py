import configparser
import pus_datapool
import packets
import poolview_sql

poolname = "LIVE"

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
pv.show_all()

import tcgui
tc=tcgui.TcGui(cfg,ccs)
tc.set_pool(poolname)
