#!/usr/bin/env python3
import logging
import sys
import os
import time
import importlib
import threading
from datetime import datetime
import confignator
ccs_path = confignator.get_option('paths', 'ccs')
sys.path.append(ccs_path)
sys.path.append(confignator.get_option('tst-paths', 'testing_library'))

import ccs_function_lib as cfl

from testlib import tools
from testlib.tools import TestVars as var
from testlib import report
from testlib import tm
from testlib import tc
from testlib import tcid
from testlib import precond
from testlib import testing_logger
from testlib import sim

${customImports}

import ${testSpecFileName}_verification

# create logger
logger = logging.getLogger(__name__)
