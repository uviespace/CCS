# Basic connection setup to IASW sim via PLM SW sim

### Poolmanager ###
cfl.start_pmgr()
POOLNAME='LIVE'

# PLM connection
cfl.connect(POOLNAME, '', 1234, protocol='PUS')
cfl.connect_tc(POOLNAME, '', 1234, protocol='PUS')

### Poolviewer ###
cfl.start_pv()

#! CCS.BREAKPOINT
### Monitor ###
cfl.start_monitor(POOLNAME)
