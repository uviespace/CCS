import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "3.0")
from gi.repository import Gtk, Gdk, GtkSource
import confignator
import sys
import logging

sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
import s2k_partypes as s2k

try:
    DP_ITEMS_SRC_FILE = confignator.get_option('database', 'datapool-items')
except confignator.config.configparser.NoOptionError:
    DP_ITEMS_SRC_FILE = None

logger = logging.getLogger()


def reload_dp_data():
    global DP_ITEMS_SRC_FILE
    global dictionary_of_data_pool
    global list_of_data_pool
    global data_pool_sublist

    try:
        dictionary_of_data_pool = cfl.get_data_pool_items(src_file=DP_ITEMS_SRC_FILE)
    except FileNotFoundError:
        logger.warning('Could not load data pool from file: {}. Using MIB instead.'.format(DP_ITEMS_SRC_FILE))
        dictionary_of_data_pool = cfl.get_data_pool_items()

    if not isinstance(dictionary_of_data_pool, list):
        list_of_data_pool = list(dictionary_of_data_pool.keys())
        data_pool_sublist = get_data_pool_sublist()
    else:
        data_pool_sublist = dictionary_of_data_pool


def get_data_pool_sublist():
    for counter in list_of_data_pool:
        pcf_pid = str(counter[0])
        pcf_descr = str(counter[1])
        pcf_ptc = counter[2]
        pcf_pfc = counter[3]

        if pcf_ptc is None:
            data_type = "None"
        else:
            data_type = s2k.ptt[pcf_ptc][pcf_pfc]

        data_pool_sublist.append([pcf_pid, pcf_descr, data_type, '', '', ''])

    return data_pool_sublist


data_pool_sublist = []
try:
    dictionary_of_data_pool = cfl.get_data_pool_items(src_file=DP_ITEMS_SRC_FILE)
except FileNotFoundError:
    logger.warning('Could not load data pool from file: {}. Using MIB instead.'.format(DP_ITEMS_SRC_FILE))
    dictionary_of_data_pool = cfl.get_data_pool_items()

if not isinstance(dictionary_of_data_pool, list):
    list_of_data_pool = list(dictionary_of_data_pool.keys())
    data_pool_sublist = get_data_pool_sublist()
else:
    data_pool_sublist = dictionary_of_data_pool


class DataPoolTable(Gtk.Grid):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.data_pool_liststore = Gtk.ListStore(str, str, str, str, str, str)
        for data_pool_ref in data_pool_sublist:
            self.data_pool_liststore.append(list(data_pool_ref))
        self.current_filter_data_pool = None

        # Creating the filter, feeding it with the liststore model
        self.data_pool_filter = self.data_pool_liststore.filter_new()
        # setting the filter function
        self.data_pool_filter.set_visible_func(self.data_pool_filter_func)

        self.pid = None

        # Create ListStores for the ComboBoxes
        # self.pid_liststore = Gtk.ListStore(str)
        # for pid_ref in pid_list:
        #     self.pid_liststore.append([pid_ref, ])
        # self.current_filter_type = None

        # creating the treeview, making it use the filter a model, adding columns
        self.treeview = Gtk.TreeView.new_with_model(Gtk.TreeModelSort(self.data_pool_filter))
        for i, column_title in enumerate(["PID", "NAME", "DATATYPE", "MULT", "PAR/VAR", "DESCR"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.set_sort_column_id(i)
            self.treeview.append_column(column)

        # Handle selection
        self.selected_row = self.treeview.get_selection()
        #self.selected_row.connect("changed", self.item_selected)

        # setting up layout, treeview in scrollwindow
        self.scrollable_treelist = Gtk.ScrolledWindow()
        self.scrollable_treelist.set_vexpand(True)
        self.scrollable_treelist.set_hexpand(True)
        self.attach(self.scrollable_treelist, 0, 1, 8, 10)

        self.scrollable_treelist.add(self.treeview)

        # Set up Drag and Drop
        self.treeview.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self.treeview.drag_source_set_target_list(None)
        self.treeview.drag_source_add_text_targets()

        self.treeview.connect("drag-data-get", self.on_drag_data_get)
        self.treeview.connect("drag-begin", self.on_drag_begin)

        self.show_all()

    def on_pid_combo_changed(self, combo):
        combo_iter = combo.get_active_iter()
        if combo_iter is not None:
            model = combo.get_model()
            number = model[combo_iter][0]
            self.current_filter_data_pool = int(number)

        self.data_pool_filter.refilter()

    def on_clear_button_clicked(self, widget):
        self.current_filter_data_pool = None
        self.data_pool_filter.refilter()

    def item_selected(self, selection):
        model, row = selection.get_selected()
        if row is not None:
            self.pid = model[row][:2]

    def data_pool_filter_func(self, model, iter, data):

        if (
                self.current_filter_data_pool is None
                or self.current_filter_data_pool == "None"
        ):
            return True
        else:
            return model[iter][0] == self.current_filter_data_pool

    def on_drag_data_get(self, treeview, drag_context, selection_data, info, time, *args):
        treeselection = treeview.get_selection()
        model, my_iter = treeselection.get_selected()
        if model is not None and my_iter is not None:
            selection_data.set_text(model[my_iter][0], -1)

    def on_drag_begin(self, *args):
        pass
