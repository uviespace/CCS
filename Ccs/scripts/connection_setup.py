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


L020003NumOfParams = 1  # UCAH0054
L020003ParamId = 178349  # UCAH0055
L020003OnbParamVal = bytes([11,22,33,44])  # UCAH0056
cfl.Tcsend_DB('L020003SetParamValues', L020003NumOfParams, L020003ParamId, L020003OnbParamVal, pool_name='LIVE')