# !/usr/bin/env python3
import gi


gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "3.0")
from gi.repository import Gtk, Gdk, GtkSource
from gi.repository.GdkPixbuf import Pixbuf
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
import s2k_partypes as s2k



verification_list = [
    ("Verification", 1, 7),
    ("Other Verification", 0, 0)
]






class VerificationTable(Gtk.Grid):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_size_request(500,500)


        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(True)
        self.add(self.grid)

        # Creating ListStore model
        self.verification_liststore = Gtk.ListStore(str, int, int)
        for verification_ref in verification_list:
            self. verification_liststore.append(list(verification_ref))
        self.current_filter_verification = None

        # Creating filter, feeding it with liststore model
        self.verification_filter = self.verification_liststore.filter_new()
        # setting the filter function
        self.verification_filter.set_visible_func(self.verification_filter_func)

        # Creating treeview
        self.treeview = Gtk.TreeView(model=self.verification_filter)
        for i, column_title in enumerate(
            ["Verification", "ST", "SST"]
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            self.treeview.append_column(column)

        # setting up layout
        self.scrollable_treelist = Gtk.ScrolledWindow()
        self.scrollable_treelist.set_vexpand(True)
        self.grid.attach(self.scrollable_treelist, 0, 0, 8, 10)
        self.scrollable_treelist.add(self.treeview)




        self.show_all()

    def verification_filter_func(self, model, iter, data):
        if(
                self.current_filter_verification is None
                or self.current_filter_verification == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_verification