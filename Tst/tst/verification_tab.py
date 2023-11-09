# !/usr/bin/env python3
import gi
import os

gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "3.0")
from gi.repository import Gtk, Gdk, GtkSource
from gi.repository.GdkPixbuf import Pixbuf
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
sys.path.append(os.path.join(confignator.get_option("paths", "Tst"), "testing_library/testlib"))
sys.path.append('/home/sebastian/CCS/Tst/testing_library/testlib')  # notwendig damit tm als Modul erkannt wird
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
# print(sys.path)
import inspect


import tm

Verification_1 = "tm." + tm.get_tc_acknow.__name__ + str(inspect.signature((tm.get_tc_acknow)))
Verification_2 = "tm." + tm.await_tc_acknow.__name__ + str(inspect.signature((tm.await_tc_acknow)))
Verification_3 = "tm." + tm.get_5_1_tc_acknow.__name__ + str(inspect.signature((tm.get_5_1_tc_acknow)))
tc_identifier = "identified_tc = tm." + tm.get_tc_identifier.__name__ + str(inspect.signature((tm.get_tc_identifier)))
Verification_4 = "tm." + tm.get_frequency_of_hk.__name__ + str(inspect.signature((tm.get_frequency_of_hk)))
Verification_5 = "tm." + tm.get_dpu_mode.__name__ + str(inspect.signature((tm.get_dpu_mode)))
Verification_6 = "tm." + tm.get_packet_length.__name__ + str(inspect.signature((tm.get_packet_length)))
Verification_7 = "tm." + tm.get_version_number.__name__ + str(inspect.signature((tm.get_version_number)))
Verification_8 = "tm." + tm.get_data_of_last_tc.__name__ + str(inspect.signature((tm.get_data_of_last_tc)))
Verification_9 = "tm." + tm.verify_no_more_hk.__name__ + str(inspect.signature((tm.verify_no_more_hk)))




# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

# Descriptions

descr_8 = "Get Timestamp of TM before last TC, get IID of last TC, get first 4 bytes of TC raw data."
descr_9 = "Check if there are no more HK packets"



verification_list = [
    ("Get TC Verification", 1, 7, "descr", Verification_1),
    ("Await TC Verification", 1, 7, "descr", tc_identifier + "\n" + Verification_2),
    ("Get TC Verification", 5, 1, "descr", Verification_3),
    ("Get HK frequency", None, None, "descr", Verification_4),
    ("Get DPU Mode", None, None, "descr", Verification_5),
    ("Get Packet Length", None, None, "descr", Verification_6),
    ("Get Version Number", None, None, "descr", Verification_7),
    ("Get Data of last TC", None, None, descr_8, Verification_8),
    ("Test if there are no more HK packets", None, None, descr_9, Verification_9)
]






def translate_drag_data(data):


    translated = "kla"

    return translated


class VerificationTable(Gtk.Grid):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_size_request(500,500)


        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(True)
        self.add(self.grid)

        # Creating ListStore model
        self.verification_liststore = Gtk.ListStore(str, int, int, str, str)
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
            ["Verification", "ST", "SST", "Description"]
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
            global descr
            global name_string

            verification_name = model[row][0]
            ST = model[row][1]
            SST = model[row][2]
            descr = model[row][3]
            name_string = model[row][4]

            global selected_data_for_drag_drop
            # print(verification_name)
            # print(name_string)

            selected_data_for_drag_drop = name_string
            # ToDo: selected_data_for_drag_drop = "result = " + name_string
            # selected_data_for_drag_drop = cfl.verification_template(name_string)
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




















