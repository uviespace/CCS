#!/usr/bin/env python3
import logging
import sys
import os
import time
import importlib
import threading

sys.path.append(os.path.realpath('test_specs'))
from testlib import tools
from testlib import report
from testlib import tm
from testlib import tc
from testlib import tcid
from testlib import precond
from testlib import testing_logger
from testlib import sim

import ${testSpecFileName}_verification

# create logger
logger = logging.getLogger(__name__)
