import configparser
import pus_datapool
import packets
import poolview_sql

pool_name = "LIVE"

# Load the config file
cfgfile = "egse.cfg"
cfg = configparser.ConfigParser()
cfg.read(cfgfile)
cfg.source = cfgfile

poolmgr = pus_datapool.PUSDatapoolManager(cfg)

ccs = packets.CCScom(cfg, poolmgr)

h = poolmgr.connect_socket(pool_name, '127.0.0.1', 5570)
poolmgr.connect_tc(pool_name, '127.0.0.1', 5571)

pv = poolview_sql.TMPoolView(cfg)
pv.set_ccs(ccs)
pv.set_pool(pool_name)
pv.show_all()

ccs.Tcsend_DB('DPU_IFSW_ENB_HK_DR_GEN', 2, ack='0b1011', pool_name=pool_name)
ccs.TcSetHkRepFreq(2, 32)
