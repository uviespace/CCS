#!/usr/bin/env python3
"""Open a small GTK window to verify container-to-XQuartz forwarding."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


initialized, _ = Gtk.init_check()
if not initialized:
    raise SystemExit(
        "GTK is installed but cannot reach XQuartz. On the Mac, quit XQuartz, "
        "run: defaults write org.xquartz.X11 nolisten_tcp -bool false; "
        "restart XQuartz; then run: /opt/X11/bin/xhost +localhost"
    )


window = Gtk.Window(title="CCS dev container")
window.set_default_size(360, 100)
window.add(Gtk.Label(label="Ubuntu 24.04 + GTK 3 + XQuartz works"))
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
