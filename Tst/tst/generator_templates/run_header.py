#!/usr/bin/env python3
# this script should provide an easy way to execute single steps of the test IASW_1_DB
import logging
import threading
import os
import sys
import importlib
import time
print('current working directory: {}'.format(os.getcwd()))
import confignator
ccs_path = confignator.get_option('paths', 'ccs')
sys.path.append(ccs_path)
sys.path.append(confignator.get_option('tst-paths', 'testing_library'))
from testlib import tools
from testlib import report
from testlib import tm
from testlib import tc
from testlib import precond
from testlib import testing_logger
from testlib import sim
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
import ${testSpecFileName}_command
import ${testSpecFileName}_verification

# re-import the script after changes have been made
importlib.reload(${testSpecFileName}_command)
importlib.reload(${testSpecFileName}_verification)

# create a instance of the test and the verification
testinstance = ${testSpecFileName}_command.${testSpecClassName}(do_verification=True)
verification_instance = ${testSpecFileName}_verification.${testSpecClassName}Verification()

# define the pool name
pool_name = 'new_tmtc_pool'

#! CCS.BREAKPOINT
# run the whole test
threading.Thread(target=testinstance.run,
                 kwargs={'pool_name': pool_name},
                 daemon=True).start()

if False:
    # Save the pool to a file
    threading.Thread(target=testinstance.save_pool_in_file,
                     kwargs={'pool_name': pool_name,
                             'save_pool': True},
                     daemon=True).start()
if False:
    # do Verification of command log file and saved pool
    threading.Thread(target=verification_instance.verify,
                     kwargs={'command_log_file':'logs_test_runs/Simple_Example_command_cmd.log',
                             'saved_pool_file': 'logs_test_runs/Simple_Example.tmpool'},
                     daemon=True).start()

# -----------------------------------------------------------------------------------------------

# Run the test step by step

#! CCS.BREAKPOINT
# Exectute the preconditions
threading.Thread(target=testinstance.establish_preconditions, kwargs={'pool_name': pool_name}, daemon=True).start()
