#!/usr/bin/env python3
"""
The verification script
"""
import logging
import sys
import os
import confignator
ccs_path = confignator.get_option('paths', 'ccs')
sys.path.append(ccs_path)
sys.path.append(confignator.get_option('tst-paths', 'testing_library'))

import ccs_function_lib as cfl
from  Tst.testing_library.testlib import tm

from datetime import datetime
from testlib import report
from testlib import analyse_command_log
from testlib import testing_logger

# create logger
logger = logging.getLogger(__name__)
