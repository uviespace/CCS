### Poolmanager ###
cfl.start_pmgr()

# PLM connection
cfl.connect_tc('LIVE', '', 5571, protocol='PUS')

### Poolviewer ###
cfl.start_pv()