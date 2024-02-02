#--------------------------------------------
# BasicBsw
# Basic Operation Under BSW Control
# Specification Version: x.x
# Software Version: 
# Author: UVIE
# Date: 2024-02-02
#--------------------------------------------

# COMMENT: Switch on instrument to remain under BSW control, perform basic checks on its operation under nominal conditions and then switch instrument off


# Precond.
# Instrument switched off and configured to remain under BSW control
#! CCS.BREAKPOINT

# STEP 1.0
# (100) Run the FCP InstSwitchOnCoc (Instrument Switch-On for CoCa) to start the BSW in MAINTENANCE Mode
# todo for platform commands
# VERIFICATION: (1) FCP InstSwitchOnCoc (Instrument Switch-On for CoCa): start BSW branch under nominal conditions
# COMMENT: only platform commands

#! CCS.BREAKPOINT

# STEP 2.0
# (200) TODO Run the FCP CheckConfig (Check Configuration) to verify the BSW configuration
# skip for first test implementation
# VERIFICATION: 
# COMMENT: TODO

#! CCS.BREAKPOINT

# STEP 3.0
# (300) TODO Basic BSW Telemetry Checks
# skip for first test implementation
# VERIFICATION: 
# COMMENT: TODO

#! CCS.BREAKPOINT

# STEP 4.0
# (400) Perform Connection Test
cfl.Tcsend_DB('L017001PerfConnTest', pool_name='LIVE')
# wait for report generation
import time
time.sleep(0.1) # 100ms
# VERIFICATION: Send command Tst:Cnct and verify that report Tst:CnctRep is generated within 100 ms from the reception of the command

#! CCS.BREAKPOINT

# STEP 5.0
# (500) Acquire and Check Boot Report
cfl.Tcsend_DB('L170010GenBootRep', pool_name='LIVE')
# wait for report generation
import time
time.sleep(0.1) # 100ms
# VERIFICATION: Run FCP CometIntFcp:TrigBootRep to trigger generation of the boot report and verify that: (a) Report Log:BootRep is generated within 100 ms of command Log:GenBootRep (b) Verify that the reset type information in the boot report is consistent with the instrument having been powered up (c) Verify that the context information is all zero (instrument was powered up)

#! CCS.BREAKPOINT

# STEP 6.0
# (700) Telemetry Jitter and Sequence Counters
import time
time.sleep(20*60) # 20min
# VERIFICATION: Collect a periodically generated TM packet for 20 minutes and then: (a) Verify that the time-stamp of the first and the last packets differ by no more than 20 min + 10 ms (b) Verify that maximum jitter on the time-stamps is below 10 ms (c) Verify that there are no gaps in the sequence counters of the packets

#! CCS.BREAKPOINT

# STEP 7.0
# (800) Instrument Switch-Off
# todo for platform commands
# VERIFICATION: 
# COMMENT: only platform commands

#! CCS.BREAKPOINT

# Postcond.
# 
