import configparser
import pickle
import struct
import sys
import io
import os
import gi

gi.require_version('Gtk', '3.0')

# with open('.sharedvariables.bin', 'rb') as fdesc:
#     shared = pickle.load(fdesc)
#
# cfg = shared['cfg']
#logger = shared['logger']

#sys.stderr = io.StringIO()
import confignator
cfg = confignator.get_config()