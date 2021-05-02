# Execute this script to recover packets obtained during the last *pool_name* session

import pus_datapool
poolmgr = pus_datapool.PUSDatapoolManager(cfg)

# write DB content to file
pool_name = 'LIVE'
dump_file = 'recovery.tmpool'
poolmgr.recover_from_db(pool_name=pool_name, dump=dump_file)

#! CCS.BREAKPOINT
# load recovered data into pool
import poolview_sql
import packets
ccs = packets.CCScom(cfg, poolmgr)
pv = poolview_sql.TMPoolView(cfg, ccs)

pv.load_pool(filename=dump_file)
