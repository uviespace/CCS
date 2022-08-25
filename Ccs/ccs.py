#!/usr/bin/env python3

import os
import sys
import editor
import gi
import DBus_Basic

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from dbus.mainloop.glib import DBusGMainLoop

import ccs_function_lib as cfl
import confignator

cfg = confignator.get_config()


def run():
    global cfg
    global files_to_open

    win = editor.CcsEditor()

    if cfg.has_option('ccs-init', 'init_script'):
        init_script = cfg.get('ccs-init', 'init_script')
        if init_script != '':
            init_cmd = 'exec(open("{}","r").read())\n'.format(init_script)
            win.ipython_view.feed_child(init_cmd, len(init_cmd))

    DBusGMainLoop(set_as_default=True)
    if files_to_open:
        for fname in files_to_open:
            win.open_file(fname)
    else:
        win.open_file(os.path.join(confignator.get_option('paths', 'ccs'), 'getting_started.py'))

    bus_name = cfg.get('ccs-dbus_names', 'editor')
    DBus_Basic.MessageListener(win, bus_name, *sys.argv)


if __name__ == "__main__":

    if '--setup' in sys.argv:
        cfl.ProjectDialog()
        Gtk.main()
        sys.argv.remove('--setup')

    files_to_open = [fn for fn in sys.argv[1:] if not fn.startswith('-')]

    run()
    Gtk.main()
