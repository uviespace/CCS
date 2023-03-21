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


logger = logging.getLogger()
DP_ITEMS_SRC_FILE = cfl.DP_ITEMS_SRC_FILE


def reload_dp_data():
    global DP_ITEMS_SRC_FILE
    # global dictionary_of_data_pool
    global list_of_data_pool
    global data_pool_sublist

    try:
        list_of_data_pool, _src = cfl.get_data_pool_items(src_file=DP_ITEMS_SRC_FILE)
    except (FileNotFoundError, ValueError):
        logger.warning('Could not load data pool from file: {}. Using MIB instead.'.format(DP_ITEMS_SRC_FILE))
        list_of_data_pool, _src = cfl.get_data_pool_items()

    # check if DP items are from MIB or CSV
    if not _src:
        data_pool_sublist = get_data_pool_sublist()
    else:
        data_pool_sublist = list_of_data_pool

    # if not isinstance(list_of_data_pool, list):
    #     data_pool_sublist = get_data_pool_sublist()
    # else:
    #     data_pool_sublist = dictionary_of_data_pool


def get_data_pool_sublist():
    for counter in list_of_data_pool:
        pcf_pid = str(int(counter[0]))  # cast PID to int in case data type is wrong in MIB SQL (e.g. in CHEOPS)
        pcf_descr = str(counter[1])
        pcf_ptc = counter[2]
        pcf_pfc = counter[3]

        if pcf_ptc is None:
            data_type = "None"
        else:
            data_type = s2k.ptt(pcf_ptc, pcf_pfc)

        data_pool_sublist.append([pcf_pid, pcf_descr, data_type, '', '', ''])

    return data_pool_sublist


data_pool_sublist = []
try:
    list_of_data_pool, _src = cfl.get_data_pool_items(src_file=DP_ITEMS_SRC_FILE)
except (FileNotFoundError, ValueError):
    logger.warning('Could not load data pool from file: {}. Using MIB instead.'.format(DP_ITEMS_SRC_FILE))
    list_of_data_pool, _src = cfl.get_data_pool_items()

# check if DP items are from MIB or CSV
if not _src:
    data_pool_sublist = get_data_pool_sublist()
else:
    data_pool_sublist = list_of_data_pool

# if not isinstance(list_of_data_pool, list):
#     data_pool_sublist = get_data_pool_sublist()
# else:
#     data_pool_sublist = list_of_data_pool


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

        # filter entry
        self.filter_entry = Gtk.SearchEntry()
        self.filter_entry.connect('search-changed', self.do_filter)
        self.attach(self.filter_entry, 0, 0, 8, 1)

        # creating the treeview, making it use the filter a model, adding columns
        self.treeview = Gtk.TreeView.new_with_model(Gtk.TreeModelSort(self.data_pool_filter))
        for i, column_title in enumerate(["PID", "NAME", "DATATYPE", "MULT", "PAR/VAR", "DESCR"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            column.set_sort_column_id(i)
            self.treeview.append_column(column)

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

        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.rcl_menu = TreeRightClickMenu(cruf=self)
        self.treeview.connect("button-press-event", self.on_treeview_clicked)

        self.show_all()

    def do_filter(self, widget, *args):
        self.current_filter_data_pool = widget.get_text()
        self.data_pool_filter.refilter()

    def on_treeview_clicked(self, widget, event):
        if event.button == 3:
            self.rcl_menu.popup_at_pointer()

    def copy_cell_content(self, cell_idx, as_string=False):
        treeselection = self.treeview.get_selection()
        model, it = treeselection.get_selected()
        if model is not None and it is not None:
            if as_string:
                self.clipboard.set_text('"{}"'.format(model[it][cell_idx]), -1)
            else:
                self.clipboard.set_text(model[it][cell_idx], -1)

    def data_pool_filter_func(self, model, iter, data):
        if not self.current_filter_data_pool:
            return True
        else:
            # match search string in PID, NAME, DESCR columns
            return ' '.join([*model[iter][:2], model[iter][5]]).lower().count(self.current_filter_data_pool.lower())

    def on_drag_data_get(self, treeview, drag_context, selection_data, info, time, *args):
        treeselection = treeview.get_selection()
        model, my_iter = treeselection.get_selected()
        if model is not None and my_iter is not None:
            selection_data.set_text(model[my_iter][0], -1)


class TreeRightClickMenu(Gtk.Menu):
    def __init__(self, cruf):
        super(TreeRightClickMenu, self).__init__()

        entry_1 = Gtk.MenuItem('Copy PID')
        self.attach(entry_1, 0, 1, 0, 1)
        entry_1.show()
        entry_2 = Gtk.MenuItem('Copy NAME')
        self.attach(entry_2, 0, 1, 1, 2)
        entry_2.show()
        entry_3 = Gtk.MenuItem('Copy NAME as string')
        self.attach(entry_3, 0, 1, 2, 3)
        entry_3.show()
        entry_1.connect('activate', self.on_copy_pid, cruf)
        entry_2.connect('activate', self.on_copy_name, cruf)
        entry_3.connect('activate', self.on_copy_name_as_string, cruf)

    def on_copy_pid(self, menu_item, cruf, *args):
        cruf.copy_cell_content(0)

    def on_copy_name(self, menu_item, cruf, *args):
        cruf.copy_cell_content(1)

    def on_copy_name_as_string(self, menu_item, cruf, *args):
        cruf.copy_cell_content(1, as_string=True)
