import pickle
import struct
import sys
import io
import os
import gi
import dbus
import dbus.service
import ccs_function_lib as cfl

gi.require_version('Gtk', '3.0')

# try:
#     with open('.sharedvariables.bin', 'rb') as fdesc:
#         shared = pickle.load(fdesc)
#     cfg = shared['cfg']
# except:
#     pass
# finally:
#     fdesc.close()
#logger = shared['logger']

#sys.stderr = io.StringIO()
#Connect to every open DBus,
dbus_type = dbus.SessionBus()
import confignator
cfg = confignator.get_config()

def kwargs(arguments={}):
    return dbus.Dictionary({'kwargs': dbus.Dictionary(arguments, signature='sv')})


'''
# Now done in editor.py
# Connect to all open applications
try:
    Bus_Name_poolviewer = cfg.get('dbus_names', 'poolviewer')
    pv = dbus_type.get_object(Bus_Name_poolviewer, '/MessageListener')
except:
    pass
try:
    Bus_Name_poolmgr = cfg.get('dbus_names', 'poolmanager')
    pmgr = dbus.SessionBus().get_object(Bus_Name_poolmgr, '/MessageListener')
except:
    pass
try:
    Bus_Name_monitor = cfg.get('dbus_names', 'monitor')
    monitor = dbus.SessionBus().get_object(Bus_Name_monitor, '/MessageListener')
except:
    pass
try:
    Bus_Name_plotter = cfg.get('dbus_names', 'plotter')
    plotter = dbus.SessionBus().get_object(Bus_Name_plotter, '/MessageListener')
except:
    pass
'''