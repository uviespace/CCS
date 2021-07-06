#!/usr/bin/env python3
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "3.0")
from gi.repository import Gtk, GtkSource
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl


tc_type = None



def get_variables(tc_type):


    pas_numbr = ""
    pas_altxt = ""
    pas_alval = ""
    prv_numbr = ""
    prv_minval = ""
    prv_maxval = ""

    for key in dictionary_of_commands:
        # print(key)
        if tc_type in key:
            for value_list in dictionary_of_commands[key]:

                pas_numbr += str(value_list[3]) + " "
                pas_altxt += str(value_list[4]) + " "
                pas_alval += str(value_list[5]) + " "
                prv_numbr += str(value_list[6]) + " "
                prv_minval += str(value_list[7]) + " "
                prv_maxval += str(value_list[8]) + " "
                # print(value_list[0])

    pas_numbr_list = list(pas_numbr.split(" "))
    pas_numbr_list.pop()
    pas_altxt_list = list(pas_altxt.split(" "))
    pas_altxt_list.pop()
    pas_alval_list = list(pas_alval.split(" "))
    pas_alval_list.pop()
    prv_numbr_list = list(prv_numbr.split(" "))
    prv_numbr_list.pop()
    prv_minval_list = list(prv_minval.split(" "))
    prv_minval_list.pop()
    prv_maxval_list = list(prv_maxval.split(" "))
    prv_maxval_list.pop()

    # print("pas_numbr: ", pas_numbr_list)
    # print("pas_altxt: ", pas_altxt_list)
    # print("pas_alval: ", pas_alval_list)
    # print("prv_numbr: ", prv_numbr_list)
    # print("prv_minval: ", prv_minval_list)
    # print("prv_maxval: ", prv_maxval_list)

    return pas_numbr_list, pas_altxt_list, pas_alval_list, prv_numbr_list, prv_minval_list, prv_maxval_list


# print(get_variables("SASW LoadCmd"))

dictionary_of_variables = cfl.get_tc_calibration_and_parameters()

def get_cpc_descr(tc_type):


    # read_in_list_of_variables = list(dictionary_of_variables.keys())

    cpc_descr = []

    for key in dictionary_of_variables:
        if tc_type in key:
            cpc_descr.append(key[3])
    cpc_descr = [[list_element] for list_element in cpc_descr]
    return cpc_descr


def get_calibrations(tc_type, cpc_descr):
    treeview_tuple_list = []
    for key in dictionary_of_variables:
        if tc_type in key and cpc_descr in key:
            for counter in dictionary_of_variables[key]:


                prv_minval = counter[2]
                prv_maxval = counter[3]
                pas_altxt = counter[4]
                pas_alval = counter[5]

                if prv_minval == None:
                    prv_minval = "None"
                if prv_maxval == None:
                    prv_maxval = "None"
                if pas_altxt == None:
                    pas_altxt = "None"
                if pas_alval == None:
                    pas_alval = "None"

                treeview_tuple = tuple([prv_minval, prv_maxval, pas_altxt, pas_alval])
                treeview_tuple_list.append(treeview_tuple)
    return treeview_tuple_list





descr_list = []
calibrations_list = []
minval_list = []
maxval_list = []
altxt_list = []
alval_list = []



class CommandDescriptionBox(Gtk.Box):
    def __init__(self):

        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.HORIZONTAL)


        # first treeview for commands
        self.descr_liststore = Gtk.ListStore(str)
        for descr_ref in descr_list:
            self.descr_liststore.append(list(descr_ref))
        self.current_filter_descr = None

        # Creating filter, feeding it with liststore model
        self.descr_filter = self.descr_liststore.filter_new()
        # setting the filter function
        self.descr_filter.set_visible_func(self.descr_filter_func)

        self.treeview = Gtk.TreeView(model=self.descr_filter)


        for i, column_title in enumerate(
            [1]
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.colnr = i
            self.treeview.append_column(column)


        # item selection
        # self.treeview.connect("button-press-event", self.on_cell_clicked)
        self.selected_row = self.treeview.get_selection()
        self.selected_row.connect("changed", self.item_selected)


        self.scrollable_treelist = Gtk.ScrolledWindow()
        self.scrollable_treelist.set_vexpand(True)
        self.pack_start(self.scrollable_treelist, True, True, 0)

        self.scrollable_treelist.add(self.treeview)



        # second treeview for calibrations
        self.cal_liststore = Gtk.ListStore(str, str, str, str)
        for cal_ref in calibrations_list:
            self.cal_liststore.append(list(cal_ref))
        self.current_filter_descr = None

        # Creating filter, feeding it with liststore model
        self.cal_filter = self.cal_liststore.filter_new()
        # setting the filter function
        self.cal_filter.set_visible_func(self.cal_filter_func)

        self.cal_treeview = Gtk.TreeView(model=self.descr_filter)

        for i, column_title in enumerate(
                ["prv_minval", "prv_maxval", "pas_altxt", "pas_alval"]
        ):
            calibrations_renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, calibrations_renderer, text=i)
            column.colnumbr = i
            self.cal_treeview.append_column(column)

        self.scrollable_calibrations_treelist = Gtk.ScrolledWindow()
        self.scrollable_calibrations_treelist.set_vexpand(True)
        self.pack_start(self.scrollable_calibrations_treelist, True, True, 0)

        self.scrollable_calibrations_treelist.add(self.cal_treeview)





    def descr_filter_func(self, model, iter, data):
        if (
            self.current_filter_descr is None
            or self.current_filter_descr == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_descr


    def item_selected(self, selection):
        model, row = selection.get_selected()
        if row is not None:
            # print("item_selected")
            # print(model[row][0])
            calibrations_list.clear()
            calibrations_list.append(get_calibrations(tc_type, model[row][0]))
            # calibrations_list = get_calibrations(tc_type, model[row][0])
            self.refresh_cal_treeview()





    def refresh_descr_treeview(self):
        self.descr_liststore.clear()
        self.descr_liststore = Gtk.ListStore(str)
        for descr_ref in descr_list:
            self.descr_liststore.append(tuple(descr_ref))
        self.treeview.set_model(self.descr_liststore)


    def cal_filter_func(self, model, iter, data):
        if (
            self.current_filter_descr is None
            or self.current_filter_descr == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_descr

    def refresh_cal_treeview(self):
        self.cal_liststore = Gtk.ListStore(str, str, str, str)

        if calibrations_list == [] or calibrations_list == [[]]:
            pass
        else:
            for cal_ref in calibrations_list[0]:
                self.cal_liststore.append(list(cal_ref))


        # self.cal_treeview.set_model(self.cal_liststore)


        self.cal_treeview.set_model(self.cal_liststore)









        # self.show_all()