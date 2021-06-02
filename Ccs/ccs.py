#!/usr/bin/env python3

import sys
import os
import editor
import signal
import dbus
import gi
import DBus_Basic
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk,GLib
from dbus.mainloop.glib import DBusGMainLoop
import ccs_function_lib as cfl
#from pydbus import SessionBus

import confignator
cfg = confignator.get_config()

# t = threading.Thread(target=embed_kernel)
# t.daemon = True
# t.start()
win = editor.CcsEditor()
#cfl.start_editor()

if cfg.has_option('init', 'init_script'):
    init_script = cfg.get('init', 'init_script')
    if init_script != '':
        init_cmd = 'exec(open("{}","r").read())\n'.format(init_script)
        # win.ipython_view.text_buffer.insert_at_cursor(init_cmd, len(init_cmd))
        # win.ipython_view._processLine()
        win.ipython_view.feed_child(init_cmd, len(init_cmd))

given_cfg = None
for i in sys.argv:
    if i.endswith('.cfg'):
        given_cfg = i
if given_cfg:
    cfg = confignator.get_config(file_path=given_cfg)
else:
    cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))
# pv = TMPoolView(cfg)
DBusGMainLoop(set_as_default=True)
if len(sys.argv) > 1:
    for fname in sys.argv[1:]:
        if not fname.startswith('-'):
            win.open_file(fname)
else:
    win.open_file(os.path.join(confignator.get_option('paths', 'ccs'), 'getting_started.py'))

Bus_Name = cfg.get('ccs-dbus_names', 'editor')

DBus_Basic.MessageListener(win, Bus_Name, *sys.argv)

Gtk.main()

