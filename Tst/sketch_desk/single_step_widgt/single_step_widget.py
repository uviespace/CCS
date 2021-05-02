import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import view
from tst import tst


class AWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="Label Example")

        # self.vbox = Gtk.Box()
        # self.vbox.set_orientation(Gtk.Orientation.VERTICAL)
        new_test = tst.TestInstance(self)
        self.step_widget = view.StepWidget(model=new_test.model,
                                           step_number=1,
                                           app=None, board=None)

        self.add(self.step_widget)


window = AWindow()
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
