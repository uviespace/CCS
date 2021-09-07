#!/usr/bin/env python3
import gi


gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "3.0")
from gi.repository import Gtk, Gdk, GtkSource
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl


dictionary_of_tms = cfl.get_tm_id()


tm_list = list(dictionary_of_tms.keys())


















tc_type = None


dictionary_of_commands = cfl.get_tc_list()
read_in_list_of_commands = list(dictionary_of_commands.keys())
list_of_commands = []
type_list = []
subtype_list = []

descr_list = []
calibrations_list = []
minval_list = []
maxval_list = []
altxt_list = []
alval_list = []


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






class TmTable(Gtk.Grid):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_size_request(500,500)

        self.telemetry_liststore = Gtk.ListStore(int, int, int, int, str)
        for telemetry_ref in tm_list:
            self.telemetry_liststore.append(list(telemetry_ref))
        self.current_filter_telemetry = None

        # Creating the filter, feeding it with the liststore model
        self.telemetry_filter = self.telemetry_liststore.filter_new()
        # setting the filter function
        self.telemetry_filter.set_visible_func(self.telemetry_filter_func)

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

        # creating the treeview, making it use the filter a model, adding columns
        self.treeview = Gtk.TreeView.new_with_model(Gtk.TreeModelSort(self.telemetry_filter))
        for i, column_title in enumerate(
            ["#TYPE", "SUBTYPE", "APID", "PI1_VALUE", "PID DESCR"]
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
            # print(number)
            self.current_filter_telecommand = int(number)

        self.telecommand_filter.refilter()


    def on_clear_button_clicked(self, widget):
        self.current_filter_telecommand = None
        self.telecommand_filter.refilter()

    def item_selected(self, selection):
        pass




    def telemetry_filter_func(self, model, iter, data):

        if (
                self.current_filter_telemetry is None
                or self.current_filter_telemetry == "None"
        ):
            return True
        else:
            return model[iter][0] == self.current_filter_telemetry

    def on_drag_data_get(self, treeview, drag_context, selection_data, info, time, *args):
        treeselection = treeview.get_selection()
        model, my_iter = treeselection.get_selected()
        selection_data.set_text(cfl.make_tc_template(descr, comment=False), -1)

    def on_drag_begin(self, *args):
        pass
