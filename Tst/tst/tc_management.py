#!/usr/bin/env python3
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





tc_type = None

dictionary_of_commands = cfl.get_tc_list()
read_in_list_of_commands = list(dictionary_of_commands.keys())
list_of_commands = []
type_list = []
subtype_list = []

descr_list = []
calibrations_list = []



for command in read_in_list_of_commands:
    command = list(command)
    del command[0]
    myorder = [2, 3, 0, 1]
    command = [command[i] for i in myorder]
    command[0] = int(command[0])
    command[1] = int(command[1])
    list_of_commands.append(command)
    if command[0] not in type_list:
        type_list.append(command[0])


type_list.sort()
subtype_list.sort()





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

                cpc_ptc = counter[0]
                cpc_pfc = counter[1]
                prv_minval = counter[2]
                prv_maxval = counter[3]
                pas_altxt = counter[4]
                pas_alval = counter[5]

                if cpc_ptc == None:
                    cpc_ptc = "None"
                if cpc_pfc == None:
                    cpc_pfc = "None"
                if prv_minval == None:
                    prv_minval = "None"
                if prv_maxval == None:
                    prv_maxval = "None"
                if pas_altxt == None:
                    pas_altxt = "None"
                if pas_alval == None:
                    pas_alval = "None"


                if cpc_ptc == "None":
                    data_type = "None"
                    pass
                else:
                    data_type = s2k.ptt[cpc_ptc][cpc_pfc]

                treeview_tuple = tuple([prv_minval, prv_maxval, pas_altxt, pas_alval, data_type])
                treeview_tuple_list.append(treeview_tuple)
    return treeview_tuple_list





class TcTable(Gtk.Grid):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_size_request(500,500)
        # self.set_orientation(Gtk.Orientation.VERTICAL)
        # self.grid = Gtk.Grid

        self.telecommand_liststore = Gtk.ListStore(int, int, str, str)
        for telecommand_ref in list_of_commands:
            self.telecommand_liststore.append(list(telecommand_ref))
        self.current_filter_telecommand = None
        self.current_filter_longdescr = None
        self.current_filter_descr = None

        # Creating the filter, feeding it with the liststore model
        self.telecommand_filter = self.telecommand_liststore.filter_new()
        # setting the filter function
        self.telecommand_filter.set_visible_func(self.telecommand_filter_func)
        # self.telecommand_filter.set_visible_func(self.search_filter_func)

        # Create ListStores for the ComboBoxes
        self.type_liststore = Gtk.ListStore(int)
        for type_ref in type_list:
            self.type_liststore.append([type_ref, ])
        # self.current_filter_type = None

        self.type_combo = Gtk.ComboBox.new_with_model(self.type_liststore)
        self.type_combo.connect("changed", self.on_type_combo_changed)
        renderer_text = Gtk.CellRendererText()
        self.type_combo.pack_start(renderer_text, True)
        self.type_combo.add_attribute(renderer_text, "text", 0)
        self.attach(self.type_combo, 0, 0, 1, 1)

        self.clear_button = Gtk.Button(label="Clear")
        self.clear_button.connect("clicked", self.on_clear_button_clicked)
        self.attach_next_to(
            self.clear_button, self.type_combo, Gtk.PositionType.RIGHT, 1, 1
        )

        """
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("<search>")
        self.attach_next_to(
            self.search_entry, self.clear_button, Gtk.PositionType.RIGHT, 1, 1
        )

        self.search_button = Gtk.ToolButton()
        self.search_button.set_icon_name("search")
        self.search_button.set_tooltip_text("Search")
        self.search_button.connect("clicked", self.on_search)
        self.attach_next_to(
            self.search_button, self.search_entry, Gtk.PositionType.RIGHT, 1, 1
        )
        """


        # creating the treeview, making it use the filter a model, adding columns
        self.treeview = Gtk.TreeView.new_with_model(Gtk.TreeModelSort(self.telecommand_filter))
        for i, column_title in enumerate(
            ["#TYPE", "SUBTYPE", "DESCR", "LONGDESCR"]
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.set_sort_column_id(i)
            self.treeview.append_column(column)

        # Handle selection
        self.selected_row = self.treeview.get_selection()
        self.selected_row.connect("changed", self.item_selected)

        # setting up layout, treeview in scrollwindow
        self.scrollable_treelist = Gtk.ScrolledWindow()
        self.scrollable_treelist.set_vexpand(True)
        self.scrollable_treelist.set_hexpand(True)
        self.attach(self.scrollable_treelist, 0, 1, 8, 10)

        self.scrollable_treelist.add(self.treeview)

        self.command_entry = Gtk.Entry()
        self.command_entry.set_placeholder_text("<Command Variables>")
        self.attach_next_to(self.command_entry, self.scrollable_treelist, Gtk.PositionType.BOTTOM, 8, 1)

        self.variable_box = CommandDescriptionBox()
        self.attach_next_to(self.variable_box, self.command_entry, Gtk.PositionType.BOTTOM, 8, 5)

        # Set up Drag and Drop
        self.treeview.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self.treeview.drag_source_set_target_list(None)
        self.treeview.drag_source_add_text_targets()

        self.treeview.connect("drag-data-get", self.on_drag_data_get)
        self.treeview.connect("drag-begin", self.on_drag_begin)

        self.show_all()


    def on_type_combo_changed(self, combo):
        combo_iter = combo.get_active_iter()
        if combo_iter is not None:
            model = combo.get_model()
            number = model[combo_iter][0]
            self.current_filter_telecommand = int(number)

        self.telecommand_filter.refilter()


    def on_clear_button_clicked(self, widget):
        self.current_filter_telecommand = None
        self.telecommand_filter.refilter()


    def item_selected(self, selection):
        model, row = selection.get_selected()
        if row is not None:
            global descr
            descr = model[row][2]
            self.command_entry.set_text(cfl.make_tc_template(descr, comment=False))
            global tc_type
            tc_type = descr
            cpc_descr = get_cpc_descr(tc_type)
            global descr_list
            descr_list.clear()
            descr_list = cpc_descr
            self.variable_box.refresh_descr_treeview()
            calibrations_list.clear()
            self.variable_box.refresh_cal_treeview()
        else:
            pass


    def telecommand_filter_func(self, model, iter, data):
        # print("test telecommand filter")
        if (
                self.current_filter_telecommand is None
                or self.current_filter_telecommand == "None"
        ):
            return True
        else:
            return model[iter][0] == self.current_filter_telecommand


    def on_drag_data_get(self, treeview, drag_context, selection_data, info, time, *args):
        treeselection = treeview.get_selection()
        model, my_iter = treeselection.get_selected()
        selection_data.set_text(cfl.make_tc_template(descr, comment=False, add_parcfg=True), -1)


    def on_drag_begin(self, *args):
        pass


    def on_search(self, *args):
        data_from_search_entry = self.search_entry.get_text()

        self.telecommand_filter = self.telecommand_liststore.filter_new()
        # setting the filter function
        self.telecommand_filter.set_visible_func(self.search_filter_func)

        self.telecommand_filter.refilter()

        print(data_from_search_entry)
        print("search started")


    def search_filter_func(self, model, iter, data):
        print("test search filter")
        if (
                self.current_filter_longdescr is None
                or self.current_filter_longdescr == "None"
        ):
            return True
        else:
            return model[iter][3] == self.current_filter_longdescr




class CommandDescriptionBox(Gtk.Box):
    def __init__(self):

        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        # self.set_hexpand(False)



        # first treeview for commands
        self.descr_liststore = Gtk.ListStore(str)
        for descr_ref in descr_list:
            self.descr_liststore.append(list(descr_ref))
        self.current_filter_descr = None

        # Creating filter, feeding it with liststore model
        self.descr_filter = self.descr_liststore.filter_new()
        # setting the filter function
        self.descr_filter.set_visible_func(self.descr_filter_func)

        self.descr_treeview = Gtk.TreeView(model=self.descr_filter)


        for i, column_title in enumerate(
            [1]
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.colnr = i
            self.descr_treeview.append_column(column)


        # item selection
        # self.treeview.connect("button-press-event", self.on_cell_clicked)
        self.selected_row = self.descr_treeview.get_selection()
        self.selected_row.connect("changed", self.item_selected)


        self.scrollable_treelist = Gtk.ScrolledWindow()
        # self.scrollable_treelist.set_vexpand(True)
        # self.scrollable_treelist.set_hexpand(20)
        self.pack_start(self.scrollable_treelist, True, True, 5)

        self.scrollable_treelist.add(self.descr_treeview)



        # second treeview for calibrations
        self.cal_liststore = Gtk.ListStore(str, str, str, str, str)
        for cal_ref in calibrations_list:
            self.cal_liststore.append(list(cal_ref))
        self.current_filter_descr = None

        # Creating filter, feeding it with liststore model
        self.cal_filter = self.cal_liststore.filter_new()
        # setting the filter function
        self.cal_filter.set_visible_func(self.cal_filter_func)

        self.cal_treeview = Gtk.TreeView(model=self.cal_filter)

        for i, column_title in enumerate(
                ["prv_minval", "prv_maxval", "pas_altxt", "pas_alval", "data-type"]
        ):
            calibrations_renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, calibrations_renderer, text=i)
            column.colnumbr = i
            self.cal_treeview.append_column(column)


        self.scrollable_calibrations_treelist = Gtk.ScrolledWindow()
        # self.scrollable_calibrations_treelist.set_vexpand(True)
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
            self.refresh_cal_treeview()





    def refresh_descr_treeview(self):
        self.descr_liststore.clear()
        self.descr_liststore = Gtk.ListStore(str)
        for descr_ref in descr_list:
            self.descr_liststore.append(tuple(descr_ref))
        self.descr_treeview.set_model(self.descr_liststore)


    def cal_filter_func(self, model, iter, data):
        if (
            self.current_filter_descr is None
            or self.current_filter_descr == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_descr

    def refresh_cal_treeview(self):

        self.cal_liststore = Gtk.ListStore(str, str, str, str, str)

        if calibrations_list == [] or calibrations_list == [[]]:
            pass
        else:
            for cal_ref in calibrations_list[0]:
                self.cal_liststore.append(list(cal_ref))


        # self.cal_treeview.set_model(self.cal_liststore)


        self.cal_treeview.set_model(self.cal_liststore)

