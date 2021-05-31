import os
import gi
import logging
import dbus
import gettext
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, Gdk, GtkSource
from gi.repository import Gio
# -------------------------------------------
import confignator
import toolbox
import db_schema
import db_interaction
import dnd_data_parser

# using gettext for internationalization (i18n)
localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'locale')
translate = gettext.translation('handroll', localedir, fallback=True)
_ = translate.gettext

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


log_file_path = confignator.get_option(section='codereuse-logging', option='log-file-path')

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


class TstSearch(Gtk.Application):

    def __init__(self, application_id, file_path,  flags=Gio.ApplicationFlags.FLAGS_NONE, logger=logger, *args, **kwargs):
        super().__init__(application_id=application_id, flags=flags, **kwargs)
        self.window = None
        self.file_path = file_path
        self.logger = logger

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
            self.window = AppWindow(application=self,
                                    title='Log File Viewer',
                                    file_path=self.file_path,
                                    logger=self.logger)

        self.window.present()

    def on_about(self, action, param):
        about_dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        about_dialog.present()

    def on_quit(self, action, param):
        # save the window width & height and the position of the panes
        self.window.on_delete_event()
        self.quit()


class AppWindow(Gtk.ApplicationWindow):

    def __init__(self, file_path, logger=logger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger

        action = Gio.SimpleAction.new('close', None)
        action.connect('activate', self.on_close)
        self.add_action(action)
        action = Gio.SimpleAction.new('reload', None)
        action.connect('activate', self.on_reload)
        self.add_action(action)

        self.connect('delete-event', self.on_delete_event)

        # GUI
        self.box = Gtk.Box()
        self.box.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar & place for info bar (see function add_info_bar)
        self.btn_reload = Gtk.ToolButton()
        self.btn_reload.set_icon_name('view-refresh-symbolic')
        self.btn_reload.set_tooltip_text(_('Reload all files'))
        self.btn_reload.connect('clicked', self.on_reload)
        self.toolbar = Gtk.Toolbar()
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

        # set the size (width and height) of the main window using the values of the configuration file
        height_from_config = confignator.get_option('codereuse-preferences', 'main-window-height')
        width_from_config = confignator.get_option('codereuse-preferences', 'main-window-width')
        if height_from_config is not None and width_from_config is not None:
            self.resize(int(width_from_config), int(height_from_config))
        else:
            self.maximize()

        self.add_page()

        self.show_all()

    def add_page(self):
        page_widget = CBRSearch(self, logger=self.logger)
        label_text = os.path.basename('CodeBlockReuseFeature')
        label = self.notebook_page_label(label_text=label_text)
        new_page_index = self.notebook.append_page(child=page_widget, tab_label=label)
        self.show_all()
        self.notebook.set_current_page(new_page_index)
        return new_page_index

    def on_switch_page(self, notebook, page, page_num):
        return
        # switched_to = self.notebook.get_nth_page(page_num)

    def on_close(self, *args):
        """ Closing the current active page """
        current_page = self.notebook.get_current_page()
        if not current_page == -1:
            # remove the page from the notebook
            self.notebook.remove_page(current_page)
        # self.update_model_viewer()

    def on_delete_event(self, *args):
        # saving the height and width of the window
        confignator.save_option('codereuse-preferences', 'main-window-height', str(self.get_size().height))
        confignator.save_option('codereuse-preferences', 'main-window-width', str(self.get_size().width))
        # find the current notebook page and save the positions of the panes
        current_page_index = self.notebook.get_current_page()
        current_page_widget = self.notebook.get_nth_page(current_page_index)
        current_page_widget.save_panes_positions()

    def on_reload(self, *args):
        curr_page_idx = self.notebook.get_current_page()
        curr_page = self.notebook.get_nth_page(curr_page_idx)
        curr_page.reload_data()

    def add_filters(self, dialog):
        filter_text = Gtk.FileFilter()
        filter_text.set_name(_('Log files'))
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
        btn_close.set_tooltip_text(_('Close'))
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


class CBRSearch(Gtk.Box):

    def __init__(self, app_win, logger=logger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_win = app_win
        self.logger = logger

        # with db_schema.session_scope() as session:
        #     self.session = session

        self._filter_searchstring = ''
        self._filter_type_snippet = None
        # self._filter_lvl_info = None
        # self._filter_lvl_warning = None
        # self._filter_lvl_error = None
        # self._filter_lvl_critical = None
        # self._filter_lvl_none = None

        # self._filter_columns = {}

        self.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar
        self.toolbar = Gtk.Toolbar()
        self.btn_filter_rows = Gtk.ToolButton()
        self.btn_filter_rows.set_label('Filter Rows')
        self.btn_filter_rows.connect('clicked', self.on_btn_filter_rows)
        self.toolbar.insert(self.btn_filter_rows, 0)

        # self.btn_filter_columns = Gtk.ToolButton()
        # self.btn_filter_columns.set_label('Filter Columns')
        # self.btn_filter_columns.connect('clicked', self.on_btn_filter_columns)
        # self.toolbar.insert(self.btn_filter_columns, 1)

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
        self.checkbox_filter_debug.connect('toggled', self.on_toggle_filter_type_snippet)
        # self.checkbox_filter_info = Gtk.CheckButton()
        # self.checkbox_filter_info.connect('toggled', self.on_toggle_filter_level_info)
        # self.checkbox_filter_warning = Gtk.CheckButton()
        # self.checkbox_filter_warning.connect('toggled', self.on_toggle_filter_level_warning)
        # self.checkbox_filter_error = Gtk.CheckButton()
        # self.checkbox_filter_error.connect('toggled', self.on_toggle_filter_level_error)
        # self.checkbox_filter_critical = Gtk.CheckButton()
        # self.checkbox_filter_critical.connect('toggled', self.on_toggle_filter_level_critical)
        # self.checkbox_filter_none = Gtk.CheckButton()
        # self.checkbox_filter_none.connect('toggled', self.on_toggle_filter_level_none)
        self.btn_save_filters = Gtk.Button()
        self.btn_save_filters.set_label('Save')
        self.btn_save_filters.connect('clicked', self.on_btn_save_filters)
        # read the values of the filters out of the configuration file
        self.filter_type_snippet = confignator.get_bool_option('codereuse-filter', 'type-snippet')
        # self.filter_level_info = confignator.get_bool_option('log-viewer-filter', 'level-info')
        # self.filter_level_warning = confignator.get_bool_option('log-viewer-filter', 'level-warning')
        # self.filter_level_error = confignator.get_bool_option('log-viewer-filter', 'level-error')
        # self.filter_level_critical = confignator.get_bool_option('log-viewer-filter', 'level-critical')
        # self.filter_level_none = confignator.get_bool_option('log-viewer-filter', 'level-none')

        # load data into the Liststore and filter
        self.data = None
        self.data_filtered = None
        self.load_data()

        # popover for filtering the rows
        self.popover_filter_rows = Gtk.Popover()
        self.popover_filter_rows.set_position(Gtk.PositionType.BOTTOM)
        # set the checkboxes of the filter popover
        self.checkbox_filter_debug.set_active(self.filter_type_snippet)
        # self.checkbox_filter_info.set_active(self.filter_level_info)
        # self.checkbox_filter_warning.set_active(self.filter_level_warning)
        # self.checkbox_filter_error.set_active(self.filter_level_error)
        # self.checkbox_filter_critical.set_active(self.filter_level_critical)
        # self.checkbox_filter_none.set_active(self.filter_level_none)
        # add the checkboxes to the popover for filtering the rows
        self.listbox_levels = Gtk.ListBox()
        self.listbox_levels.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box_row_debug = make_list_box_row(_('Snippets'), self.checkbox_filter_debug)
        # list_box_row_info = make_list_box_row('INFO', self.checkbox_filter_info)
        # list_box_row_warning = make_list_box_row('WARNING', self.checkbox_filter_warning)
        # list_box_row_error = make_list_box_row('ERROR', self.checkbox_filter_error)
        # list_box_row_critical = make_list_box_row('CRITICAL', self.checkbox_filter_critical)
        # list_box_row_none = make_list_box_row('No level', self.checkbox_filter_none)
        list_box_row_save = make_list_box_row(_('Save filters'), self.btn_save_filters)
        self.listbox_levels.add(list_box_row_debug)
        # self.listbox_levels.add(list_box_row_info)
        # self.listbox_levels.add(list_box_row_warning)
        # self.listbox_levels.add(list_box_row_error)
        # self.listbox_levels.add(list_box_row_critical)
        # self.listbox_levels.add(list_box_row_none)
        self.listbox_levels.add(list_box_row_save)
        self.popover_filter_rows.add(self.listbox_levels)

        # # popover for filtering the columns
        # self.popover_filter_columns = Gtk.Popover()
        # self.popover_filter_columns.set_position(Gtk.PositionType.BOTTOM)
        # # add the checkboxes to the popover for filtering the columns
        # self.listbox_columns = Gtk.ListBox()
        # self.listbox_columns.set_selection_mode(Gtk.SelectionMode.NONE)
        # # read the values of the filters out of the configuration file
        # filter_values = []
        # for item in toolbox.extract_descriptions():
        #     value = confignator.get_bool_option('log-viewer-filter', item)
        #     if value is None:
        #         # ToDo: add a Infobar to notify the user, that no entry was found in the configuration
        #         value = True
        #     filter_values.append((item, value))
        # self.filter_columns = filter_values
        # # set the checkboxes of the filter popover
        # column_headers = toolbox.extract_descriptions()
        # for idx, head in enumerate(column_headers):
        #     checkbox_filter_column = Gtk.CheckButton()
        #     checkbox_filter_column.set_active(self.filter_columns[head])
        #     checkbox_filter_column.connect('toggled', self.on_toggle_filter_column, head)
        #     list_box_row_column = make_list_box_row(head, checkbox_filter_column)
        #     self.listbox_columns.add(list_box_row_column)
        # self.btn_save_filters_columns = Gtk.Button()
        # self.btn_save_filters_columns.set_label('Save')
        # self.btn_save_filters_columns.connect('clicked', self.on_btn_save_filters)
        # list_box_row_save = make_list_box_row('Save filters', self.btn_save_filters_columns)
        # self.listbox_columns.add(list_box_row_save)
        # self.popover_filter_columns.add(self.listbox_columns)

        # search field
        self.input_field = Gtk.Entry()
        self.pack_start(self.input_field, False, False, 0)
        self.input_buffer = Gtk.EntryBuffer()
        self.input_field.set_buffer(self.input_buffer)
        self.input_buffer.connect('inserted-text', self.on_search_text_inserted)
        self.input_buffer.connect('deleted-text', self.on_search_text_deleted)

        self.pane = Gtk.Paned()
        self.pane.set_orientation(Gtk.Orientation.VERTICAL)

        # tree view for the showing the log messages
        scroller = Gtk.ScrolledWindow()
        self.tree = Gtk.TreeView()
        self.tree.set_rules_hint(True)
        self.tree.set_grid_lines(Gtk.TreeViewGridLines.VERTICAL)
        self.tree.set_enable_tree_lines(True)
        self.tree.set_activate_on_single_click(True)
        self.tree.connect('row-activated', self.on_row_activated)
        self.tree.connect('button-release-event', self.on_button_release)
        self.tree.connect('key-release-event', self.on_key_release)
        self.fill_treeview()

        # drag and drop: the StepWidget as a drag source
        self.tree.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self.tree.drag_source_set_target_list(None)

        # drag and drop: the StepWidget as a drag destination
        self.tree.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.tree.drag_dest_set_target_list(None)

        self.tree.drag_dest_add_text_targets()
        self.tree.drag_source_add_text_targets()

        self.tree.connect('drag-data-received', self.on_drag_data_received)
        self.tree.connect('drag-motion', self.on_drag_motion)
        self.tree.connect('drag-leave', self.on_drag_leave)
        self.tree.connect('drag-begin', self.on_drag_begin)
        self.tree.connect('drag-data-get', self.on_drag_data_get)
        self.tree.connect('drag-drop', self.on_drag_drop)

        scroller.add(self.tree)
        self.pane.pack1(scroller)

        # the view of the code -----------------------------------------------------------------------------------------
        self.lm = GtkSource.LanguageManager()
        self.style_manager = GtkSource.StyleSchemeManager.get_default()

        # source view for the command code ---------------------
        self.cc_box = Gtk.Box()
        self.cc_box.set_orientation(Gtk.Orientation.VERTICAL)

        self.cc_label = Gtk.Label()
        self.cc_label.set_text(_('Command code:'))

        self.cc_scrolled_window = Gtk.ScrolledWindow()
        self.cc_code_view = GtkSource.View()
        self.cc_code_view_buffer = self.cc_code_view.get_buffer()
        self.cc_code_view_buffer.set_language(self.lm.get_language('json'))
        self.cc_code_view_buffer.set_style_scheme(self.style_manager.get_scheme('darcula'))
        self.cc_scrolled_window.add(self.cc_code_view)

        self.cc_box.pack_start(self.cc_label, False, False, 0)
        self.cc_box.pack_start(self.cc_scrolled_window, True, True, 0)

        # source view for the verification code ---------------------
        self.vc_box = Gtk.Box()
        self.vc_box.set_orientation(Gtk.Orientation.VERTICAL)

        self.vc_label = Gtk.Label()
        self.vc_label.set_text(_('Verification code:'))

        self.vc_scrolled_window = Gtk.ScrolledWindow()
        self.vc_code_view = GtkSource.View()
        self.vc_code_view_buffer = self.vc_code_view.get_buffer()
        self.vc_code_view_buffer.set_language(self.lm.get_language('json'))
        self.vc_code_view_buffer.set_style_scheme(self.style_manager.get_scheme('darcula'))
        self.vc_scrolled_window.add(self.vc_code_view)

        self.vc_box.pack_start(self.vc_label, False, False, 0)
        self.vc_box.pack_start(self.vc_scrolled_window, True, True, 0)

        self.code_view_pane = Gtk.Paned()
        self.code_view_pane.set_orientation(Gtk.Orientation.VERTICAL)
        self.code_view_pane.pack1(self.cc_box)
        self.code_view_pane.pack2(self.vc_box)
        self.pane.pack2(self.code_view_pane)

        self.pack_start(self.pane, True, True, 0)
        self.right_click_menu = TreeRightClickMenu(cruf=self)

        # set the position of the Paned widget using the configuration file
        paned_position = confignator.get_option('codereuse-preferences', 'paned-position-search')
        self.set_paned_position(int(paned_position))
        # set the position of the paned of the widget self.codeblockreuse
        paned_position_cc = confignator.get_option('codereuse-preferences', 'paned-position-command-code')
        self.set_code_view_pane_position(int(paned_position_cc))

        self.show_all()

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data, info, time):
        # parse the received data
        data_string = selection_data.get_text()
        data = dnd_data_parser.read_datastring(data_string, logger=self.logger)
        drag_source_type = data['data_type']
        step_number = data['step_number']
        description = data['description']
        command_code = data['command_code']
        verification_code = data['verification_code']
        if drag_source_type == dnd_data_parser.data_type_step:
            db_interaction.write_into_db_step(description=description,
                                              command_code=command_code,
                                              verification_code=verification_code)
        if drag_source_type == dnd_data_parser.data_type_snippet:
            db_interaction.write_into_db_snippet(description=description,
                                                 code_block=command_code)
        self.reload_data()
        self.show_all()

    def on_drag_motion(self, *args):
        pass

    def on_drag_leave(self, *args):
        pass

    def on_drag_begin(self, *args):
        pass

    def on_drag_drop(self, widget, drag_context, x, y, timestamp, *args):
        pass

    def on_drag_data_get(self, treeview, drag_context, selection_data, info, time, *args):
        # find the treeview row were the drag was started
        treeselection = treeview.get_selection()
        model, my_iter = treeselection.get_selected()
        path = model.get_path(my_iter)
        # retrieve the data from the tree-view row and build a string to set into the selection data object
        desc = model[path][2]
        command_code = model[path][3]
        verification_code = model[path][4]
        data_string = dnd_data_parser.create_datastring(dnd_data_parser.data_type_snippet, description=desc, command_code=command_code, verification_code=verification_code, logger=self.logger)
        # set the data into the selection data object
        selection_data.set_text(data_string, -1)

    def on_button_release(self, widget, event, *args):
        if event.button == 3:  # right mouse button clicked
            # show the right-click context menu
            self.right_click_menu.popup_at_pointer()

    def on_key_release(self, widget, event, *args):
        if Gdk.keyval_name(event.keyval) == 'Delete':
            self.delete_selected_treeview_row()

    def set_paned_position(self, position):
        # set the position of Paned widget. If no position is provided, -1 (as not set) is set.
        if position is None:
            position = -1
        self.pane.set_position(position)

    def get_paned_position(self):
        return self.pane.get_position()

    def set_code_view_pane_position(self, position):
        # set the position of Paned widget. If no position is provided, -1 (as not set) is set.
        if position is None:
            position = -1
        self.code_view_pane.set_position(position)

    def get_code_view_pane_position(self):
        return self.code_view_pane.get_position()

    def save_panes_positions(self):
        """
        save the position of the pane widgets
        """
        confignator.save_option('codereuse-preferences', 'paned-position-search',
                                str(self.get_paned_position()))
        confignator.save_option('codereuse-preferences', 'paned-position-command-code',
                                str(self.get_code_view_pane_position()))

    # @property
    # def filter_columns(self):
    #     return self._filter_columns
    #
    # @filter_columns.setter
    # def filter_columns(self, value: list):
    #     assert isinstance(value, list)
    #     for item in value:
    #         assert isinstance(item, tuple)
    #         assert isinstance(item[0], str)
    #         assert isinstance(item[1], bool)
    #         self._filter_columns[item[0]] = item[1]

    @property
    def filter_type_snippet(self):
        return self._filter_type_snippet

    @filter_type_snippet.setter
    def filter_type_snippet(self, value: bool):
        assert isinstance(value, bool)
        self._filter_type_snippet = value

    @property
    def filter_searchstring(self):
        return self._filter_searchstring

    @filter_searchstring.setter
    def filter_searchstring(self, value: str):
        assert isinstance(value, str)
        self._filter_searchstring = value

    # @property
    # def filter_level_info(self):
    #     return self._filter_lvl_info
    #
    # @filter_level_info.setter
    # def filter_level_info(self, value: bool):
    #     assert isinstance(value, bool)
    #     self._filter_lvl_info = value
    #
    # @property
    # def filter_level_warning(self):
    #     return self._filter_lvl_warning
    #
    # @filter_level_warning.setter
    # def filter_level_warning(self, value: bool):
    #     assert isinstance(value, bool)
    #     self._filter_lvl_warning = value
    #
    # @property
    # def filter_level_error(self):
    #     return self._filter_lvl_error
    #
    # @filter_level_error.setter
    # def filter_level_error(self, value: bool):
    #     assert isinstance(value, bool)
    #     self._filter_lvl_error = value
    #
    # @property
    # def filter_level_critical(self):
    #     return self._filter_lvl_critical
    #
    # @filter_level_critical.setter
    # def filter_level_critical(self, value: bool):
    #     assert isinstance(value, bool)
    #     self._filter_lvl_critical = value
    #
    # @property
    # def filter_level_none(self):
    #     return self._filter_lvl_none
    #
    # @filter_level_none.setter
    # def filter_level_none(self, value: bool):
    #     assert isinstance(value, bool)
    #     self._filter_lvl_none = value

    def on_search_text_inserted(self, buffer, position, chars, n_chars, *args):
        searchstring = buffer.get_text()
        self.filter_searchstring = searchstring
        self.reload_data()

    def on_search_text_deleted(self, buffer, position, n_chars, *args):
        searchstring = buffer.get_text()
        self.filter_searchstring = searchstring
        self.reload_data()

    # def set_column_visibility(self, column_name):
    #     for col_num in range(0, self.tree.get_n_columns()):
    #         col = self.tree.get_column(col_num)
    #         col_name = col.get_name()
    #         if col_name == column_name:
    #             col.set_visible(self.filter_columns[column_name])

    def on_row_activated(self, tree_view, path, column, *args):
        """
        If a row of the tree-view is activated, the detail view for the command and verification code are filled.
        """
        tree_view_model = tree_view.get_model()
        tree_model_row = tree_view_model[path]
        command_code = tree_model_row[3]
        verification_code = tree_model_row[4]
        self.cc_code_view_buffer.set_text(command_code)
        self.vc_code_view_buffer.set_text(verification_code)

    def load_data_into_liststore(self, data: list):
        # how many columns are in a row
        column_cnt = [int, str, str, str, str]
        # column_cnt.append(str)  # for background color

        self.data_filtered = Gtk.TreeStore(*column_cnt)
        last_added = None
        for line in data:
            assert isinstance(line, db_schema.CodeBlock)
            row = line.data_as_list()
            # add element in the list for the background color
            # background = '#767d89'
            # background = None
            # row.append(background)
            if len(row) != len(column_cnt):
                raise ValueError
            # if it is a traceback make it a child, otherwise just append the line
            # if line[0] == 'TRACEBACK':
            #     line[0] = ''
            #     liststore.append(parent=last_added, row=line)
            # else:
            #     last_added = liststore.append(parent=None, row=line)
            last_added = self.data_filtered.append(parent=None, row=row)

        # modelfilter = self.data_filtered.filter_new()
        #
        # def visible_func(model, iter, user_data):
        #     is_visible = True
        #
        #     first_column_val = model[iter][1]
        #
        #     if self.filter_type_snippet is False:
        #         if first_column_val == 'snippet':
        #             is_visible = False
        #
        #     # if self.filter_level_info is False:
        #     #     if first_column_val == logging.getLevelName(logging.INFO):
        #     #         is_visible = False
        #     #
        #     # if self.filter_level_warning is False:
        #     #     if first_column_val == logging.getLevelName(logging.WARNING):
        #     #         is_visible = False
        #     #
        #     # if self.filter_level_error is False:
        #     #     if first_column_val == logging.getLevelName(logging.ERROR):
        #     #         is_visible = False
        #     #
        #     # if self.filter_level_critical is False:
        #     #     if first_column_val == logging.getLevelName(logging.CRITICAL):
        #     #         is_visible = False
        #     #
        #     # if self.filter_level_none is False:
        #     #     if first_column_val == '':
        #     #         is_visible = False
        #
        #     return is_visible
        #
        # modelfilter.set_visible_func(func=visible_func, data=None)
        #
        # self.data_filtered = modelfilter
        return self.data_filtered

    def fill_treeview(self):
        for col in self.tree.get_columns():
            self.tree.remove_column(col)

        self.tree.set_model(self.data_filtered)

        # column 1
        renderer_number = Gtk.CellRendererText()
        #renderer_number.set_property('scale', 2)
        #renderer_number.set_property('single-paragraph-mode', True)
        column_desc = Gtk.TreeViewColumn('Type', renderer_number, text=1)
        #column_desc.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_desc.set_resizable(True)
        self.tree.append_column(column_desc)

        # column 2
        renderer_number = Gtk.CellRendererText()
        #renderer_number.set_property('scale', 2)
        #renderer_number.set_property('single-paragraph-mode', True)
        column_desc = Gtk.TreeViewColumn('Description', renderer_number, text=2)
        #column_desc.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_desc.set_resizable(True)
        self.tree.append_column(column_desc)

        # column 3
        renderer_exec_date = Gtk.CellRendererText()
        column_codeblock = Gtk.TreeViewColumn('Codeblock', renderer_exec_date, text=3)  #, background=3)
        column_codeblock.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_codeblock.set_resizable(True)
        #self.tree.append_column(column_codeblock)

    def load_data(self):
        """
        Loads the data from the database. The filter properties are used to build the SQL query.
        """
        self.logger.debug('Loading data from the database')
        if self.filter_searchstring != '':
            self.data = db_interaction.query_using_textsearch(expressions=self.filter_searchstring)
        else:
            self.data = db_interaction.query_get_all_entries()
        self.load_data_into_liststore(self.data)

    def reload_data(self):
        self.load_data()
        self.fill_treeview()

    def delete_selected_treeview_row(self):
        selection = self.tree.get_selection()
        model, paths = selection.get_selected_rows()
        for path in paths:
            iter = model.get_iter(path)
            row_id = model[path][0]
            db_interaction.delete_db_row(row_id)
        # remove the row from the treeview list store
        for path in paths:
            iter = model.get_iter(path)
            # Remove the ListStore row referenced by iter
            model.remove(iter)

    def on_file_changed(self, monitor, file, other_file, event_type, user_data=None, *args):
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            self.reload_data()

    def on_toggle_filter_type_snippet(self, check_button):
        """
        The filter checkbox was toggled. Setting the instance property to the new value.
        """
        new_state = check_button.get_active()
        self.filter_type_snippet = new_state
        self.reload_data()
        # Todo

    # def on_toggle_filter_level_info(self, check_button):
    #     """
    #     The filter checkbox was toggled. Setting the instance property to the new value.
    #     """
    #     new_state = check_button.get_active()
    #     self.filter_level_info = new_state
    #     # self.data_filtered.refilter()
    #
    # def on_toggle_filter_level_warning(self, check_button):
    #     """
    #     The filter checkbox was toggled. Setting the instance property to the new value.
    #     """
    #     new_state = check_button.get_active()
    #     self.filter_level_warning = new_state
    #     # self.data_filtered.refilter()
    #
    # def on_toggle_filter_level_error(self, check_button):
    #     """
    #     The filter checkbox was toggled. Setting the instance property to the new value.
    #     """
    #     new_state = check_button.get_active()
    #     self.filter_level_error = new_state
    #     # self.data_filtered.refilter()
    #
    # def on_toggle_filter_level_critical(self, check_button):
    #     """
    #     The filter checkbox was toggled. Setting the instance property to the new value.
    #     """
    #     new_state = check_button.get_active()
    #     self.filter_level_critical = new_state
    #     # self.data_filtered.refilter()
    #
    # def on_toggle_filter_level_none(self, check_button):
    #     """
    #     The filter checkbox was toggled. Setting the instance property to the new value.
    #     """
    #     new_state = check_button.get_active()
    #     self.filter_level_none = new_state
    #     # self.data_filtered.refilter()
    #
    # def on_toggle_filter_column(self, check_button, user_data):
    #     new_state = check_button.get_active()
    #     self.filter_columns[user_data] = new_state
    #     self.set_column_visibility(user_data)
    #
    def on_btn_filter_rows(self, button):
        self.popover_filter_rows.set_relative_to(button)
        self.popover_filter_rows.show_all()
    #
    # def on_btn_filter_columns(self, button):
    #     self.popover_filter_columns.set_relative_to(button)
    #     self.popover_filter_columns.show_all()
    #
    def on_btn_save_filters(self, *args):
        """
        Save the values of the current filters in the configuration file.
        """
        confignator.save_option('codereuse-filter', 'type-snippet', str(self.filter_type_snippet))
        # confignator.save_option('log-viewer-filter', 'level-info', str(self.filter_level_info))
        # confignator.save_option('log-viewer-filter', 'level-warning', str(self.filter_level_warning))
        # confignator.save_option('log-viewer-filter', 'level-error', str(self.filter_level_error))
        # confignator.save_option('log-viewer-filter', 'level-critical', str(self.filter_level_critical))
        # confignator.save_option('log-viewer-filter', 'level-none', str(self.filter_level_none))
        # for key, value in self.filter_columns.items():
        #     confignator.save_option('log-viewer-filter', key, str(value))
        # self.app_win.add_info_bar(message_type=Gtk.MessageType.INFO,
        #                           message='Filter values were successfully saved.')


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


class TreeRightClickMenu(Gtk.Menu):
    def __init__(self, cruf):
        super().__init__()

        entry_1 = Gtk.MenuItem('Delete')
        self.attach(entry_1, 0, 1, 0, 1)
        entry_1.show()
        entry_1.connect('activate', self.on_delete, cruf)

    def on_delete(self, menu_item, cruf, *args):
        # delete the entry from the database
        cruf.delete_selected_treeview_row()


def run(file_path=None):
        bus_name = confignator.get_option('dbus_names', 'log-viewer')
        dbus.validate_bus_name(bus_name)

        if file_path is None:
            confignator_log_file = confignator.get_option('confignator-paths', 'log-file')
            if os.path.isfile(confignator_log_file):
                file_path = confignator_log_file

        applica = TstSearch(application_id=bus_name, file_path=file_path)
        applica.run()


if __name__ == '__main__':
    run()
