#!/usr/bin/env python3
import os
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, Gdk
from gi.repository import Gio
import confignator
import logging
import toolbox
import dbus
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()

uni_grau = '#666666'
uni_weiss = '#ffffff'
uni_schwarz = '#000000'
uni_blau = '#0063A6'

uni_weinrot = '#A71C49'
uni_orangerot = '#DD4814'
uni_goldgelb = '#F6A800'
uni_hellgruen = '#94C154'
uni_mintgruen = '#11897A'

# enable the GTK Inspector. Use it with CTRL+SHIFT+D or CTRL+SHIFT+I
setting = Gio.Settings.new("org.gtk.Settings.Debug")
setting.set_boolean("enable-inspector-keybinding", True)

menu_xml = os.path.join(os.path.dirname(__file__), 'menu.xml')
css_file = os.path.join(os.path.dirname(__file__), 'style.css')


log_file_path = confignator.get_option(section='log-viewer-logging', option='log-file-path')

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)
file_hdlr = toolbox.create_file_handler(file=log_file_path)
logger.addHandler(hdlr=file_hdlr)

path_tst = confignator.get_option(section='paths', option='tst')


def apply_css(*args):
    style_provider = Gtk.CssProvider()
    css = open(css_file, 'rb')  # rb needed for python 3 support
    css_data = css.read()
    css.close()
    style_provider.load_from_data(css_data)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                             style_provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    Gtk.StyleContext.reset_widgets(Gdk.Screen.get_default())


class LogViewer(Gtk.Application):

    def __init__(self, application_id, file_path,  flags=Gio.ApplicationFlags.FLAGS_NONE, logger=logger, *args, **kwargs):
        super().__init__(application_id=application_id, flags=flags, **kwargs)
        self.window = None
        self.file_path = file_path

    def do_startup(self):
        Gtk.Application.do_startup(self)

        # action = Gio.SimpleAction.new('about', None)
        # action.connect('activate', self.on_about)
        # self.add_action(action)

        action = Gio.SimpleAction.new('quit', None)
        action.connect('activate', self.on_quit)
        self.add_action(action)

        builder = Gtk.Builder.new_from_file(menu_xml)
        self.set_menubar(builder.get_object('menu-bar'))

    def do_activate(self):
        # only allow a single window and raise any existing ones
        if not self.window:
            # Windows are associated with the application
            # when the last one is closed the application shuts down
            self.window = AppWindow(application=self, title='Log File Viewer', file_path=self.file_path, logger=logger)

        self.window.present()

    def on_about(self, action, param):
        about_dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        about_dialog.present()

    def on_quit(self, action, param):
        self.quit()


class AppWindow(Gtk.ApplicationWindow):

    def __init__(self, file_path, logger=logger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger

        action = Gio.SimpleAction.new('open', None)
        action.connect('activate', self.on_open)
        self.add_action(action)
        action = Gio.SimpleAction.new('close', None)
        action.connect('activate', self.on_close)
        self.add_action(action)
        action = Gio.SimpleAction.new('reload', None)
        action.connect('activate', self.on_reload)
        self.add_action(action)

        # GUI
        self.box = Gtk.Box()
        self.box.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar & place for info bar (see function add_info_bar)
        self.btn_open_file = Gtk.ToolButton()
        self.btn_open_file.set_icon_name('document-open')
        self.btn_open_file.set_tooltip_text('Open file')
        self.btn_open_file.connect('clicked', self.on_open)
        self.btn_reload = Gtk.ToolButton()
        self.btn_reload.set_icon_name('view-refresh-symbolic')
        self.btn_reload.set_tooltip_text('Reload all files')
        self.btn_reload.connect('clicked', self.on_reload)
        self.toolbar = Gtk.Toolbar()
        self.toolbar.insert(self.btn_open_file, 0)
        self.toolbar.insert(self.btn_reload, 1)
        self.box.pack_start(self.toolbar, False, True, 0)
        self.info_bar = None

        # add the notebook for the test specifications
        self.notebook = Gtk.Notebook()
        self.notebook.connect('switch-page', self.on_switch_page)
        self.box.pack_start(self.notebook, True, True, 0)
        self.add(self.box)

        # status bar
        self.stat_bar = Gtk.Statusbar()
        self.box.pack_start(self.stat_bar, False, False, 0)

        self.add_page(file_path)

        apply_css()
        self.maximize()
        self.show_all()

    def add_page(self, filename):
        if filename is not None:
            page_widget = LogView(filename, self)
            label_text = os.path.basename(filename)
            label = self.notebook_page_label(label_text=label_text)
            new_page_index = self.notebook.append_page(child=page_widget, tab_label=label)
            self.show_all()
            self.notebook.set_current_page(new_page_index)
            return new_page_index

        return

    def on_switch_page(self, notebook, page, page_num):
        switched_to = self.notebook.get_nth_page(page_num)
        if switched_to.file_name is not None:
            message = str(switched_to.file_name)
        else:
            message = ''
        self.stat_bar.push(1, message)

    def on_close(self, *args):
        """ Closing the current active page """
        current_page = self.notebook.get_current_page()
        if not current_page == -1:
            # remove the page from the notebook
            self.notebook.remove_page(current_page)
        # self.update_model_viewer()

    def on_open(self, *args):
        dialog = Gtk.FileChooserDialog('Please choose a file',
                                       self,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        # using the last folder from history
        last_folder = confignator.get_option('log-viewer-history', 'last-folder')
        if os.path.isdir(last_folder):
            dialog.set_current_folder(last_folder)
        self.add_filters(dialog)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            confignator.save_option('log-viewer-history', 'last-folder', os.path.dirname(file_selected))
            self.add_page(filename=file_selected)
        dialog.destroy()

    def on_reload(self, *args):
        curr_page_idx = self.notebook.get_current_page()
        curr_page = self.notebook.get_nth_page(curr_page_idx)
        curr_page.reload_data()

    def add_filters(self, dialog):
        filter_text = Gtk.FileFilter()
        filter_text.set_name('Log files')
        filter_text.add_mime_type('text/plain')
        filter_text.add_pattern('.log')
        dialog.add_filter(filter_text)

        filter_any = Gtk.FileFilter()
        filter_any.set_name('Any files')
        filter_any.add_pattern('*')
        dialog.add_filter(filter_any)

    def notebook_page_label(self, label_text):
        box = Gtk.Box()
        box.set_orientation(Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label()
        label.set_text(label_text)
        btn_close = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.BUTTON)
        btn_close.set_tooltip_text('Close')
        btn_close.connect('clicked', self.on_close)
        box.pack_start(label, True, True, 0)
        box.pack_start(btn_close, True, True, 0)
        box.show_all()
        return box

    def add_info_bar(self, message_type, message):
        """
        Adds a InfoBar and moves it below the toolbar

        :param Gtk.MessageType message_type: type of the message which should be shown
        :param str message: The text of the message
        """
        assert type(message_type) is Gtk.MessageType
        assert type(message) is str
        self.info_bar = Gtk.InfoBar()
        self.info_bar.set_show_close_button(True)
        self.info_bar.set_revealed(True)
        self.info_bar.set_message_type(message_type)
        self.box.pack_start(self.info_bar, False, True, 0)
        # move the info bar below the toolbar:
        self.box.reorder_child(self.info_bar, 0)
        # add the text:
        self.info_bar.get_content_area().pack_start(
            Gtk.Label(message),
            False, False, 0)
        self.info_bar.connect('response', self.remove_info_bar)
        self.show_all()

    def remove_info_bar(self, infobar, response_id):
        """
        Removes a item with the provided response_id in the infobar.

        :param infobar:
        :param response_id:
        """
        if response_id == -7:
            infobar.destroy()


class LogView(Gtk.Box):

    def __init__(self, filename, app_win, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_win = app_win
        self.file_name = filename

        if filename is not None:
            self.gfile = Gio.File.new_for_path(self.file_name)
            self.monitor = self.gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor.connect('changed', self.on_file_changed)

        self._filter_lvl_debug = None
        self._filter_lvl_info = None
        self._filter_lvl_warning = None
        self._filter_lvl_error = None
        self._filter_lvl_critical = None
        self._filter_lvl_none = None

        self._filter_columns = {}

        self.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar
        self.toolbar = Gtk.Toolbar()
        self.btn_filter_rows = Gtk.ToolButton()
        self.btn_filter_rows.set_label('Filter Rows')
        self.btn_filter_rows.connect('clicked', self.on_btn_filter_rows)
        self.toolbar.insert(self.btn_filter_rows, 0)

        self.btn_filter_columns = Gtk.ToolButton()
        self.btn_filter_columns.set_label('Filter Columns')
        self.btn_filter_columns.connect('clicked', self.on_btn_filter_columns)
        self.toolbar.insert(self.btn_filter_columns, 1)

        self.btn_clear_log_file = Gtk.ToolButton()
        self.btn_clear_log_file.set_icon_name('user-trash-symbolic')
        self.btn_clear_log_file.set_tooltip_text('Delete all log file entries')
        self.btn_clear_log_file.connect('clicked', self.on_clear_log_file)
        self.toolbar.insert(self.btn_clear_log_file, 2)

        self.pack_start(self.toolbar, False, False, 0)

        # popover for filtering the rows
        def make_list_box_row(label_text, checkbox):
            row = Gtk.ListBoxRow()
            box = Gtk.Box()
            box.set_orientation(Gtk.Orientation.HORIZONTAL)
            box.set_homogeneous(True)
            eventbox = Gtk.EventBox()
            label = Gtk.Label()
            box.pack_start(label, False, False, 0)
            label.set_text(label_text)
            box.pack_start(checkbox, False, False, 0)
            row.add(box)
            return row

        self.checkbox_filter_debug = Gtk.CheckButton()
        self.checkbox_filter_debug.connect('toggled', self.on_toggle_filter_level_debug)
        self.checkbox_filter_info = Gtk.CheckButton()
        self.checkbox_filter_info.connect('toggled', self.on_toggle_filter_level_info)
        self.checkbox_filter_warning = Gtk.CheckButton()
        self.checkbox_filter_warning.connect('toggled', self.on_toggle_filter_level_warning)
        self.checkbox_filter_error = Gtk.CheckButton()
        self.checkbox_filter_error.connect('toggled', self.on_toggle_filter_level_error)
        self.checkbox_filter_critical = Gtk.CheckButton()
        self.checkbox_filter_critical.connect('toggled', self.on_toggle_filter_level_critical)
        self.checkbox_filter_none = Gtk.CheckButton()
        self.checkbox_filter_none.connect('toggled', self.on_toggle_filter_level_none)
        self.btn_save_filters = Gtk.Button()
        self.btn_save_filters.set_label('Save')
        self.btn_save_filters.connect('clicked', self.on_btn_save_filters)
        # read the values of the filters out of the configuration file
        self.filter_level_debug = confignator.get_bool_option('log-viewer-filter', 'level-debug')
        self.filter_level_info = confignator.get_bool_option('log-viewer-filter', 'level-info')
        self.filter_level_warning = confignator.get_bool_option('log-viewer-filter', 'level-warning')
        self.filter_level_error = confignator.get_bool_option('log-viewer-filter', 'level-error')
        self.filter_level_critical = confignator.get_bool_option('log-viewer-filter', 'level-critical')
        self.filter_level_none = confignator.get_bool_option('log-viewer-filter', 'level-none')

        # load data into the Liststore and filter
        self.data = None
        self.data_filtered = None
        self.load_data()

        # popover for filtering the rows
        self.popover_filter_rows = Gtk.Popover()
        self.popover_filter_rows.set_position(Gtk.PositionType.BOTTOM)
        # set the checkboxes of the filter popover
        self.checkbox_filter_debug.set_active(self.filter_level_debug)
        self.checkbox_filter_info.set_active(self.filter_level_info)
        self.checkbox_filter_warning.set_active(self.filter_level_warning)
        self.checkbox_filter_error.set_active(self.filter_level_error)
        self.checkbox_filter_critical.set_active(self.filter_level_critical)
        self.checkbox_filter_none.set_active(self.filter_level_none)
        # add the checkboxes to the popover for filtering the rows
        self.listbox_levels = Gtk.ListBox()
        self.listbox_levels.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box_row_debug = make_list_box_row('DEBUG', self.checkbox_filter_debug)
        list_box_row_info = make_list_box_row('INFO', self.checkbox_filter_info)
        list_box_row_warning = make_list_box_row('WARNING', self.checkbox_filter_warning)
        list_box_row_error = make_list_box_row('ERROR', self.checkbox_filter_error)
        list_box_row_critical = make_list_box_row('CRITICAL', self.checkbox_filter_critical)
        list_box_row_none = make_list_box_row('No level', self.checkbox_filter_none)
        list_box_row_save = make_list_box_row('Save filters', self.btn_save_filters)
        self.listbox_levels.add(list_box_row_debug)
        self.listbox_levels.add(list_box_row_info)
        self.listbox_levels.add(list_box_row_warning)
        self.listbox_levels.add(list_box_row_error)
        self.listbox_levels.add(list_box_row_critical)
        self.listbox_levels.add(list_box_row_none)
        self.listbox_levels.add(list_box_row_save)
        self.popover_filter_rows.add(self.listbox_levels)

        # popover for filtering the columns
        self.popover_filter_columns = Gtk.Popover()
        self.popover_filter_columns.set_position(Gtk.PositionType.BOTTOM)
        # add the checkboxes to the popover for filtering the columns
        self.listbox_columns = Gtk.ListBox()
        self.listbox_columns.set_selection_mode(Gtk.SelectionMode.NONE)
        # read the values of the filters out of the configuration file
        filter_values = []
        for item in toolbox.extract_descriptions():
            value = confignator.get_bool_option('log-viewer-filter', item)
            if value is None:
                # ToDo: add a Infobar to notify the user, that no entry was found in the configuration
                value = True
            filter_values.append((item, value))
        self.filter_columns = filter_values
        # set the checkboxes of the filter popover
        column_headers = toolbox.extract_descriptions()
        for idx, head in enumerate(column_headers):
            checkbox_filter_column = Gtk.CheckButton()
            checkbox_filter_column.set_active(self.filter_columns[head])
            checkbox_filter_column.connect('toggled', self.on_toggle_filter_column, head)
            list_box_row_column = make_list_box_row(head, checkbox_filter_column)
            self.listbox_columns.add(list_box_row_column)
        self.btn_save_filters_columns = Gtk.Button()
        self.btn_save_filters_columns.set_label('Save')
        self.btn_save_filters_columns.connect('clicked', self.on_btn_save_filters)
        list_box_row_save = make_list_box_row('Save filters', self.btn_save_filters_columns)
        self.listbox_columns.add(list_box_row_save)
        self.popover_filter_columns.add(self.listbox_columns)

        # tree view for the showing the log messages
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.ALWAYS)
        self.tree = Gtk.TreeView()
        self.tree.set_rules_hint(True)
        self.tree.set_grid_lines(Gtk.TreeViewGridLines.VERTICAL)
        self.tree.set_enable_tree_lines(True)
        self.tree.connect('size-allocate', self.on_treeview_changed)
        self.fill_treeview()

        self.scroller.add(self.tree)
        self.pack_start(self.scroller, True, True, 0)

    @property
    def filter_columns(self):
        return self._filter_columns

    @filter_columns.setter
    def filter_columns(self, value: list):
        assert isinstance(value, list)
        for item in value:
            assert isinstance(item, tuple)
            assert isinstance(item[0], str)
            assert isinstance(item[1], bool)
            self._filter_columns[item[0]] = item[1]

    @property
    def filter_level_debug(self):
        return self._filter_lvl_debug

    @filter_level_debug.setter
    def filter_level_debug(self, value: bool):
        assert isinstance(value, bool)
        self._filter_lvl_debug = value

    @property
    def filter_level_info(self):
        return self._filter_lvl_info

    @filter_level_info.setter
    def filter_level_info(self, value: bool):
        assert isinstance(value, bool)
        self._filter_lvl_info = value

    @property
    def filter_level_warning(self):
        return self._filter_lvl_warning

    @filter_level_warning.setter
    def filter_level_warning(self, value: bool):
        assert isinstance(value, bool)
        self._filter_lvl_warning = value

    @property
    def filter_level_error(self):
        return self._filter_lvl_error

    @filter_level_error.setter
    def filter_level_error(self, value: bool):
        assert isinstance(value, bool)
        self._filter_lvl_error = value

    @property
    def filter_level_critical(self):
        return self._filter_lvl_critical

    @filter_level_critical.setter
    def filter_level_critical(self, value: bool):
        assert isinstance(value, bool)
        self._filter_lvl_critical = value

    @property
    def filter_level_none(self):
        return self._filter_lvl_none

    @filter_level_none.setter
    def filter_level_none(self, value: bool):
        assert isinstance(value, bool)
        self._filter_lvl_none = value

    def set_column_visibility(self, column_name):
        for col_num in range(0, self.tree.get_n_columns()):
            col = self.tree.get_column(col_num)
            col_name = col.get_name()
            if col_name == column_name:
                col.set_visible(self.filter_columns[column_name])

    def load_data_into_liststore(self, data: list):
        # figure out how many columns are at maximum in a log message line
        column_cnt = [str for clmn in toolbox.extract_descriptions()]
        column_cnt.append(str)  # for background color

        liststore = Gtk.TreeStore(*column_cnt)
        last_added = None
        for line in data:
            # fill the line up with empty strings
            while len(line) < len(column_cnt)-1:
                line.append('')
            # add element in the list for the background color
            background = '#767d89'
            background = None
            line.append(background)
            if len(line) != len(column_cnt):
                raise ValueError
            # if it is a traceback make it a child, otherwise just append the line
            if line[0] == 'TRACEBACK':
                line[0] = ''
                liststore.append(parent=last_added, row=line)
            else:
                last_added = liststore.append(parent=None, row=line)

        modelfilter = liststore.filter_new()

        def visible_func(model, iter, user_data):
            is_visible = True

            first_column_val = model[iter][0]

            if self.filter_level_debug is False:
                if first_column_val == logging.getLevelName(logging.DEBUG):
                    is_visible = False

            if self.filter_level_info is False:
                if first_column_val == logging.getLevelName(logging.INFO):
                    is_visible = False

            if self.filter_level_warning is False:
                if first_column_val == logging.getLevelName(logging.WARNING):
                    is_visible = False

            if self.filter_level_error is False:
                if first_column_val == logging.getLevelName(logging.ERROR):
                    is_visible = False

            if self.filter_level_critical is False:
                if first_column_val == logging.getLevelName(logging.CRITICAL):
                    is_visible = False

            if self.filter_level_none is False:
                if first_column_val == '':
                    is_visible = False

            return is_visible

        modelfilter.set_visible_func(func=visible_func, data=None)

        return modelfilter

    def load_data_from_log_file(self, file: str) -> list:
        """
        Loads the data from a logfile which was written by a logger from the Python module logging.
        The entries of the lines should have a tab as separator.
        :param file: Log file to read
        :return: The lines of the log file
        :rtype: list
        """
        lines = []
        seperator = '\t'
        with open(file, 'r') as file:
            for line in file:
                row = []
                column_cnt = 0
                start_idx = 0
                if line.find(seperator, start_idx) == -1:
                    if line != '\n':
                        if line.rfind('\n') != -1:  # remove a trailing newline
                            line = line[:line.rfind('\n')]
                        row = ['TRACEBACK', '', line]
                        lines.append(row)
                else:
                    while line.find(seperator, start_idx) != -1:
                        sep = line.find(seperator, start_idx)
                        column = line[start_idx:sep]
                        row.append(column)
                        column_cnt += 1
                        start_idx = sep + 1
                    column = line[start_idx:]
                    if len(column) > 0:
                        if column.rfind('\n') != -1:  # remove a trailing newline
                            column = column[:column.rfind('\n')]
                            if len(column) > 0:
                                row.append(column)
                                column_cnt += 1
                    if len(row) > 0:
                        lines.append(row)
        return lines

    def fill_treeview(self):
        for col in self.tree.get_columns():
            self.tree.remove_column(col)

        self.tree.set_model(self.data_filtered)
        column_cnt = len(toolbox.extract_descriptions())

        for idx, item in enumerate(toolbox.extract_descriptions()):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(item, renderer, text=idx, background=column_cnt)
            column.set_name(item)
            column.set_visible(self.filter_columns[item])
            column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            column.set_resizable(True)

            def cell_function(column, cell, model, iter, user_data):
                if model[iter][0] == logging.getLevelName(logging.DEBUG):
                    cell.set_property('foreground', uni_grau)
                elif model[iter][0] == logging.getLevelName(logging.INFO):
                    cell.set_property('foreground', uni_schwarz)
                elif model[iter][0] == logging.getLevelName(logging.WARNING):
                    cell.set_property('foreground', uni_goldgelb)
                elif model[iter][0] == logging.getLevelName(logging.ERROR):
                    cell.set_property('foreground', uni_orangerot)
                elif model[iter][0] == logging.getLevelName(logging.CRITICAL):
                    cell.set_property('foreground', uni_weinrot)
                else:
                    cell.set_property('foreground', uni_mintgruen)

            column.set_cell_data_func(cell_renderer=renderer, func=cell_function, func_data=None)
            self.tree.append_column(column)

    def on_treeview_changed(self, *args):
        adju = self.scroller.get_vadjustment()
        lower_boundary = adju.get_lower()
        upper_boundary = adju.get_upper()
        page_size = adju.get_page_size()
        current_position = adju.get_value()
        adju.set_value(upper_boundary - page_size)

    def load_data(self):
        if self.file_name is not None:
            self.data = self.load_data_from_log_file(self.file_name)
            self.data_filtered = self.load_data_into_liststore(self.data)

    def reload_data(self):
        self.load_data()
        self.fill_treeview()
        return

    def clear_log_file(self):
        """Deletes the content of the log file."""
        with open(self.file_name, 'r+') as fileobject:
            fileobject.truncate()
        self.reload_data()

    def on_clear_log_file(self, *args):
        self.clear_log_file()

    def on_file_changed(self, monitor, file, other_file, event_type, user_data=None, *args):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            self.reload_data()

    def on_toggle_filter_level_debug(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_level_debug = new_state
        self.data_filtered.refilter()

    def on_toggle_filter_level_info(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_level_info = new_state
        self.data_filtered.refilter()

    def on_toggle_filter_level_warning(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_level_warning = new_state
        self.data_filtered.refilter()

    def on_toggle_filter_level_error(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_level_error = new_state
        self.data_filtered.refilter()

    def on_toggle_filter_level_critical(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_level_critical = new_state
        self.data_filtered.refilter()

    def on_toggle_filter_level_none(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_level_none = new_state
        self.data_filtered.refilter()

    def on_toggle_filter_column(self, check_button, user_data):
        new_state = check_button.get_active()
        self.filter_columns[user_data] = new_state
        self.set_column_visibility(user_data)

    def on_btn_filter_rows(self, button):
        self.popover_filter_rows.set_relative_to(button)
        self.popover_filter_rows.show_all()

    def on_btn_filter_columns(self, button):
        self.popover_filter_columns.set_relative_to(button)
        self.popover_filter_columns.show_all()

    def on_btn_save_filters(self, *args):
        """
        Save the values of the current filters in the configuration file.
        """
        confignator.save_option('log-viewer-filter', 'level-debug', str(self.filter_level_debug))
        confignator.save_option('log-viewer-filter', 'level-info', str(self.filter_level_info))
        confignator.save_option('log-viewer-filter', 'level-warning', str(self.filter_level_warning))
        confignator.save_option('log-viewer-filter', 'level-error', str(self.filter_level_error))
        confignator.save_option('log-viewer-filter', 'level-critical', str(self.filter_level_critical))
        confignator.save_option('log-viewer-filter', 'level-none', str(self.filter_level_none))
        for key, value in self.filter_columns.items():
            confignator.save_option('log-viewer-filter', key, str(value))
        self.app_win.add_info_bar(message_type=Gtk.MessageType.INFO,
                                  message='Filter values were successfully saved.')


class NotebookPageLabel(Gtk.Box):
    def __init__(self, notebook, label_text):
        super().__init__(self)
        self.notebook = notebook
        self.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.label = Gtk.Label()
        self.label.set_text(label_text)
        self.btn_close = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.BUTTON)
        self.btn_close.set_tooltip_text('Close')
        self.btn_close.connect('clicked', self.on_close)
        self.pack_start(self.label, True, True, 0)
        self.pack_start(self.btn_close, True, True, 0)
        self.show_all()

    def on_close(self, *args):
        self.notebook.page_number(self)


def run(file_path=None):
    bus_name = confignator.get_option('dbus_names', 'log-viewer')
    dbus.validate_bus_name(bus_name)

    applica = LogViewer(application_id=bus_name, file_path=file_path)
    applica.run()


if __name__ == '__main__':
    run()
