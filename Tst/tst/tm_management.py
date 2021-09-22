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
tm_type_list = []

tm_type_sub_list = []



for counter in tm_list:
    if counter[0] not in tm_type_list:
        tm_type_list.append(counter[0])
    else:
        pass


def get_tm_type_sublist(tm_descr):
    tm_type_sub_list.clear()
    for key in dictionary_of_tms:
        if tm_descr in key:
            for counter in dictionary_of_tms[key]:
                pid_tpsc = str(counter[0])
                pid_spid = str(counter[1])
                pcf_name = str(counter[2])
                pcf_descr = str(counter[3])
                pcf_curtx = str(counter[4])
                txp_from = str(counter[5])
                txp_altxt = str(counter[6])
                plf_offpy = str(counter[7])


                tm_type_sub_list.append([pid_tpsc, pid_spid, pcf_name, pcf_descr, pcf_curtx, txp_from, txp_altxt])

    return tm_type_sub_list




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
        for type_ref in tm_type_list:
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

        self.telemetry_entry = Gtk.Entry()
        self.telemetry_entry.set_placeholder_text("<Telemetry Variables>")
        self.attach_next_to(self.telemetry_entry, self.scrollable_treelist, Gtk.PositionType.BOTTOM, 8, 1)

        self.secondary_box = TmSecondaryTable()
        self.attach_next_to(self.secondary_box, self.telemetry_entry, Gtk.PositionType.BOTTOM, 8, 5)




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
            self.current_filter_telemetry = int(number)

        self.telemetry_filter.refilter()


    def on_clear_button_clicked(self, widget):
        self.current_filter_telemetry = None
        self.telemetry_filter.refilter()

    def item_selected(self, selection):
        model, row = selection.get_selected()
        if row is not None:
            tm_descr = model[row][4]
            global tm_type_sub_list
            tm_type_sub_list = get_tm_type_sublist(tm_descr)
            self.secondary_box.refresh_secondary_treelist()














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






class TmSecondaryTable(Gtk.Box):
    def __init__(self):

        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        # self.set_hexpand(False)


        self.secondary_liststore = Gtk.ListStore(str, str, str, str, str, str, str)
        for tm_type_sub_ref in tm_type_sub_list:
            self.secondary_liststore.append(list(tm_type_sub_ref))
        self.current_filter_secondary = None

        # Creating filter, feeding it with liststore model
        self.secondary_filter = self.secondary_liststore.filter_new()
        # setting the filter function
        self.secondary_filter.set_visible_func(self.secondary_filter_func)
            
        self.secondary_treeview = Gtk.TreeView(model=self.secondary_filter)

        for i, column_title in enumerate(
            ["pid_tpsc", "pid_spic", "pcf_name", "pcf_descr", "pcf_curtx", "txp_from", "txp_altxt"]
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            self.secondary_treeview.append_column(column)


        self.scrollable_secondary_tm_treelist = Gtk.ScrolledWindow()
        self.pack_start(self.scrollable_secondary_tm_treelist, True, True, 0)

        self.scrollable_secondary_tm_treelist.add(self.secondary_treeview)
        
        

             
        
    def secondary_filter_func(self, model, iter, data):
        if (
            self.current_filter_secondary is None
            or self.current_filter_secondary == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_descr

    def refresh_secondary_treelist(self):
        self.secondary_liststore.clear()
        self.secondary_liststore = Gtk.ListStore(str, str, str, str, str, str, str)
        for tm_type_sub_ref in tm_type_sub_list:
            self.secondary_liststore.append(list(tm_type_sub_ref))
        self.secondary_treeview.set_model(self.secondary_liststore)






