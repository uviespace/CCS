import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


def onMenuButtonPress(self, widget):
    # uncomment below to recreate the original behavior
    # expander.set_expanded(not expander.get_expanded())
    return True


def on_menu_button_press(self, *args):
    print('you pressed the button')

builder = Gtk.Builder()
builder.add_from_file("expander.ui")

window = builder.get_object("window1")
menu = builder.get_object("menub")
expander = builder.get_object("expander1")

expander.connect("button-press-event", onMenuButtonPress)
menu.connect('button-press-event', on_menu_button_press)

window.connect("destroy", Gtk.main_quit)
window.show_all()

Gtk.main()