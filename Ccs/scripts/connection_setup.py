# Basic connection setup to IASW sim via PLM SW sim

### Poolmanager ###
cfl.start_pmgr()

# PLM connection
cfl.connect('LIVE', '', 5570, protocol='PUS')
cfl.connect_tc('LIVE', '', 5571, protocol='PUS')

### Poolviewer ###
cfl.start_pv()

#! CCS.BREAKPOINT
### Monitor ###
cfl.start_monitor('LIVE')


