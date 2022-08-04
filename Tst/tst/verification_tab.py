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

import time
import sys
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import DBus_Basic


from typing import NamedTuple
import confignator
import gi


import verification as ver


verification_list = [
    ("Get TC Verification", 1, 7),
    ("Await TC Verification", 1, 7)
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
        self.scrollable_treelist.set_hexpand(True)
        self.grid.attach(self.scrollable_treelist, 0, 0, 8, 10)
        self.scrollable_treelist.add(self.treeview)


        # handle selection
        self.selected_row = self.treeview.get_selection()
        self.selected_row.connect("changed", self.item_selected)


        # Set up Drag and Drop
        self.treeview.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self.treeview.drag_source_set_target_list(None)
        self.treeview.drag_source_add_text_targets()

        self.treeview.connect("drag-data-get", self.on_drag_data_get)
        self.treeview.connect("drag-begin", self.on_drag_begin)

        self.show_all()

    def verification_filter_func(self, model, iter, data):
        if(
                self.current_filter_verification is None
                or self.current_filter_verification == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_verification






    # drag and drop

    def item_selected(self, selection):
        model, row = selection.get_selected()
        if row is not None:

            global verification_name
            global ST
            global SST

            verification_name = model[row][0]
            ST = model[row][1]
            SST = model[row][2]
            global selected_data_for_drag_drop


            selected_data_for_drag_drop = ver.verification_template("Verification_1")
                # str(verification_name) + "\n ST = " + str(ST) + "\n SST = " + str(SST) + "\n Time = 2"
            # selected_data_for_drag_drop = "{} ({}, {})".format((name, ST, SST))

        else:
            pass



    def on_drag_data_get(self, treeview, drag_context, selection_data, info, time, *args):
        treeselection = treeview.get_selection()
        model, my_iter = treeselection.get_selected()
        global selected_data_for_drag_drop
        selection_data.set_text(selected_data_for_drag_drop, -1)



    def on_drag_begin(self, *args):
        pass










"""

def make_verification_template(pool_name="LIVE", preamble="verification.Verification", options="", comment=False):


    prcfg = ""

    return
    
    
    def verification(self):

        # if st_variable == 1 and sst_variable == 7:

            pool_rows = cfl.get_pool_rows("PLM")

            system_time = time.clock_gettime(0)

            entry_1_data = pool_rows.all()[-1]

            time_1 = entry_1_data.timestamp

            if time_1 == "":

                first_raw_digits = ""  # this string will contain the first bytes of raw data

                telecommand = entry_1_data
                telecommand_time = telecommand.timestamp
                telecommand_raw = telecommand.raw.hex()

                # Variable to generate new telecommand timestamp, other than telecommand_time
                telecommand_verification_timestamp = time.clock_gettime(0)
                verification_time = telecommand_verification_timestamp + 2

                for i in telecommand_raw:
                    first_raw_digits += str(i)
                    if len(first_raw_digits) > 7:
                        break

                # print("After Loop telecommand_first_digits: ", first_raw_digits)

                while system_time < verification_time and system_time != verification_time:
                    system_time = time.clock_gettime(0)

                    if system_time >= verification_time:
                        verification_running = self.type_comparison(first_raw_digits)





    def type_comparison(comparison_data):
        pool_rows = cfl.get_pool_rows("PLM")

        st_list = []
        sst_list = []
        x = 0
        header_counter = 0
        while header_counter < 2:
            x += 1
            entry = pool_rows.all()[-x]

            if entry.data.hex() == comparison_data:
                st_list.append(entry.stc)
                sst_list.append(entry.sst)

                # print("ST Entry_" + str(x) + ": ", entry.stc)
                # print("SST Entry_" + str(x) + ": ", entry.sst)
                # print("Timestamp entry_" + str(x) + ": ", entry.timestamp)
                header_counter += 1


        st_list_reverse = [st_list[1], st_list[0]]
        sst_list_reverse = [sst_list[1], sst_list[0]]

        if sst_list_reverse == [1, 7]:
            print("Verification successful")
        else:
            print("Verification unsuccessful")

        return False


    def get_drop_verification(self):
        global verification_name
        global ST
        global SST

        return

    def verification_table(self, name, subtype, subsubtype):

"""




















