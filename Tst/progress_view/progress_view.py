#!/usr/bin/env python3
import os
import datetime
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib
import sys
import confignator

cfg = confignator.get_config()
sys.path.append(cfg.get('paths', 'ccs'))

import ccs_function_lib as cfl
cfl.add_tst_import_paths()

from testlib import analyse_command_log
from testlib import analyse_verification_log
from testlib import testing_logger
from testlib import analyse_test_run
import dbus
import time
import data_model
import json
import toolbox
import generator

# create a logger
log_file_path = cfg.get(section='progress-viewer-logging', option='log-file-path')

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)
file_hdlr = toolbox.create_file_handler(file=log_file_path)
logger.addHandler(hdlr=file_hdlr)

menu_xml = os.path.join(os.path.dirname(__file__), 'app_menu.xml')
css_file = os.path.join(os.path.dirname(__file__), 'style_progress_view.css')

row_step_drawer_color_even = None  # '#333333'
row_step_drawer_color_odd = None  # '#333333'
row_cmd_color = '#ced1fd'  # '#a8aefc'
row_vrc_color = '#cee9fd'  # '#a8d8fc'
row_spec_color = '#fdface'  # '#fcf6a8'

cell_result_passed = '#d1fdce'
cell_result_failed = '#fdced1'


class Application(Gtk.Application):
    def __init__(self, application_id, flags, logger=logger, *args, **kwargs):
        self.logger = logger
        self.logger.info('Initiated a instance of the ProgressViewer application class at {}'.format(time.asctime()))

        super().__init__(application_id=application_id, flags=flags)
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)

        action = Gio.SimpleAction.new('quit', None)
        action.connect('activate', self.on_quit)
        self.add_action(action)

        # create the menu
        builder = Gtk.Builder.new_from_file(menu_xml)
        self.set_app_menu(builder.get_object('app-menu'))
        self.set_menubar(builder.get_object('menu-bar'))

    def do_activate(self):
        # only allow a single window and raise any existing ones
        if not self.window:
            # Windows are associated with the application
            # when the last one is closed the application shuts down
            self.window = TestProgressView(application=self, title='Progress Viewer', logger=self.logger)
        self.window.present()

    def on_quit(self, action, param):
        self.logger.info('Self-Destruct of the ProgressView initiated.\n')
        self.quit()


class TestProgressView(Gtk.ApplicationWindow):
    """ Shows the progress of the test scripts """

    def __init__(self, logger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger

        action = Gio.SimpleAction.new('open', None)
        action.connect('activate', self.on_open)
        self.add_action(action)

        action = Gio.SimpleAction.new('open-test-files', GLib.VariantType('a{ss}'))
        action.connect('activate', self.open_test_files)
        self.add_action(action)

        action = Gio.SimpleAction.new('apply-css', None)
        action.connect('activate', self.on_apply_css)
        self.add_action(action)

        self.path_json = ''
        self.path_cmd = ''
        self.path_vrc = ''

        self.test_model = None
        self.cmd_steps = None
        self.vrc_steps = None

        self.run_count = {}

        self.expander_states = []

        self.progress_tree_store = Gtk.TreeStore(str, str, str, str, str, str, str, str, str, str, str)

        # monitoring the cmd and vrc log files for changes
        file_cmd = Gio.File.new_for_path(self.path_cmd)
        self.monitor_cmd = file_cmd.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor_cmd.set_rate_limit(100)
        self.monitor_cmd.connect('changed', self.file_cmd_changed)
        file_vrc = Gio.File.new_for_path(self.path_vrc)
        self.monitor_vrc = file_vrc.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor_vrc.set_rate_limit(100)
        self.monitor_vrc.connect('changed', self.file_vrc_changed)

        self.info_bar = None

        # GUI
        self.box = Gtk.Box()
        self.box.set_orientation(Gtk.Orientation.VERTICAL)
        self.add(self.box)
        #self.set_position(self.get_default_size()[1] * 0.2)

        self.path_frame = Gtk.Frame()
        self.path_box = Gtk.Box()
        self.path_box.set_orientation(Gtk.Orientation.VERTICAL)

        # select file - JSON test model
        self.box_file_path_1 = Gtk.Box()
        self.box_file_path_1.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.label_path_json = Gtk.Label()
        self.label_path_json.set_text('Path to JSON test spec:')
        self.box_file_path_1.pack_start(self.label_path_json, False, False, 0)
        self.text_path_json_btn = Gtk.FileChooserButton()
        self.text_path_json_btn.set_title('Choose a test specification JSON file')
        self.text_path_json_btn.connect('file-set', self.set_path_json_file)
        self.box_file_path_1.pack_start(self.text_path_json_btn, False, False, 0)
        self.path_box.pack_start(self.box_file_path_1, True, True, 0)

        # select file - command log
        self.box_file_path_2 = Gtk.Box()
        self.box_file_path_2.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.label_path_cmd = Gtk.Label()
        self.label_path_cmd.set_text('Path to Command log:')
        self.box_file_path_2.pack_start(self.label_path_cmd, False, False, 0)
        self.text_path_cmd_btn = Gtk.FileChooserButton()
        self.text_path_cmd_btn.connect('file-set', self.set_path_cmd_file)
        self.box_file_path_2.pack_start(self.text_path_cmd_btn, False, False, 0)
        self.del_btn_cmd = Gtk.Button()
        self.del_btn_cmd.set_label('Clear command log')
        self.del_btn_cmd.connect('clicked', self.on_clear_cmd_log)
        self.box_file_path_2.pack_start(self.del_btn_cmd, False, True, 0)
        self.path_box.pack_start(self.box_file_path_2, True, True, 0)

        # select file - verification log
        self.box_file_path_3 = Gtk.Box()
        self.box_file_path_3.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.label_path_vrc = Gtk.Label()
        self.label_path_vrc.set_text('Path to Verification log:')
        self.box_file_path_3.pack_start(self.label_path_vrc, False, False, 0)
        self.text_path_vrc_btn = Gtk.FileChooserButton()
        self.text_path_vrc_btn.connect('file-set', self.set_path_vrc_file)
        self.box_file_path_3.pack_start(self.text_path_vrc_btn, False, False, 0)
        self.del_btn_vrc = Gtk.Button()
        self.del_btn_vrc.set_label('Clear verification log')
        self.del_btn_vrc.connect('clicked', self.on_clear_vrc_log)
        self.box_file_path_3.pack_start(self.del_btn_vrc, False, True, 0)
        self.path_box.pack_start(self.box_file_path_3, True, True, 0)

        self.path_frame.add(self.path_box)
        self.box.pack_start(self.path_frame, False, True, 0)

        self.title_box = Gtk.HBox()
        self.test_label = Gtk.Label()
        self.test_label.set_markup('<big>Test Title: </big>')
        self.test_title = Gtk.Label()
        self.set_test_title()

        self.title_box.pack_start(self.test_label, False, True, 0)
        self.title_box.pack_start(self.test_title, False, True, 0)
        self.box.pack_start(self.title_box, False, True, 20)

        # --------------- tree view ---------------
        self.sorted_model = Gtk.TreeModelSort(model=self.progress_tree_store)
        self.sorted_model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        self.view = Gtk.TreeView(model=self.sorted_model)
        self.view.set_grid_lines(True)
        self.view.set_has_tooltip(True)
        self.view.set_tooltip_column(10)

        self.scroll_win = Gtk.ScrolledWindow()
        self.scroll_win.add(self.view)

        # buttons for the tree view (expand all, collapse all)
        self.make_button_box()
        self.box.pack_start(self.box_buttons, False, True, 0)

        self.btn_apply_css = Gtk.Button().new_from_icon_name('media-playlist-repeat-symbolic', Gtk.IconSize.BUTTON)
        self.btn_apply_css.set_tooltip_text('Apply CSS')
        self.btn_apply_css.connect('clicked', self.on_apply_css)
        # self.box_buttons.pack_start(self.btn_apply_css, False, False, 0)

        self.make_treeview()

        self.view.expand_all()

        self.box.pack_start(self.scroll_win, True, True, 0)

        self.connect('destroy', self.on_destroy)

        # expand all entries
        self.view.expand_all()

        self.refresh_rate = 1
        self.refresh_worker()

        # for styling the application with CSS
        context = self.get_style_context()
        Gtk.StyleContext.add_class(context, 'tst-css')
        self.on_apply_css()
        self.resize(
            int(cfg.get(section='progress-viewer-window-size', option='basic-width-step-mode')),
            int(cfg.get(section='progress-viewer-window-size', option='basic-height')))
        self.sort_button.set_active(True)
        self.show_all()
        logger.debug('__init__ succeeded')

    @staticmethod
    def on_apply_css(*args):
        logger.debug('Applying CSS')
        style_provider = Gtk.CssProvider()
        css = open(css_file, 'rb')  # rb needed for python 3 support
        css_data = css.read()
        css.close()
        style_provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                                 style_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.StyleContext.reset_widgets(Gdk.Screen.get_default())

    def on_open(self, simple_action, parameter):
        """
        Menu -> Open: choose a Test specification file. The command log and verification log files will be loaded
        automatically. Using the path in the configuration file.
        :param Gio.SimpleAction simple_action: The object which received the signal
        :param parameter: the parameter to the activation, or None if it has no parameter
        """
        dialog = Gtk.FileChooserDialog(title='Please choose a Test Specification',
                                       parent=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.set_current_folder(cfg.get(section='progress-viewer-history', option='last-folder'))
        self.add_filters(dialog)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            confignator.save_option('progress-viewer-history', 'last-folder', os.path.dirname(file_selected))
            self.open_test_files(None, self.get_log_file_paths_from_json_file_name(file_selected))
        elif response == Gtk.ResponseType.CANCEL:
            pass
        dialog.destroy()

    def make_button_box(self):
        self.box_buttons = Gtk.Box()
        self.box_buttons.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.btn_exp_all = Gtk.Button()
        self.btn_exp_all.set_label('Expand all')
        self.btn_exp_all.connect('clicked', self.on_expand_all_rows)
        self.box_buttons.pack_start(self.btn_exp_all, False, False, 0)
        self.btn_clp_all = Gtk.Button()
        self.btn_clp_all.set_label('Collapse all')
        self.btn_clp_all.connect('clicked', self.on_collapse_all_rows)
        self.box_buttons.pack_start(self.btn_clp_all, False, False, 0)
        self.btn_rld_all = Gtk.Button()
        self.btn_rld_all.set_label('Reload all')
        self.btn_rld_all.connect('clicked', self.on_reload_all)
        self.box_buttons.pack_start(self.btn_rld_all, False, False, 0)
        self.btn_output = Gtk.Button()
        self.btn_output.set_label('Generate Output File')
        self.btn_output.connect('clicked', self.on_save_as)
        self.box_buttons.pack_start(self.btn_output, False, False, 0)

        self.sort_label = Gtk.Label()
        self.sort_label.set_text('Sort by Execution')
        self.box_buttons.pack_end(self.sort_label, False, True, 0)

        self.sort_button = Gtk.Switch()
        self.sort_button.connect("notify::active", self.on_remake_treeview)
        self.box_buttons.pack_end(self.sort_button, False, True, 0)

        self.sort_label2 = Gtk.Label()
        self.sort_label2.set_text('Sort by Steps')
        self.box_buttons.pack_end(self.sort_label2, False, True, 0)

    def make_treeview(self):
        # self.view.set_enable_tree_lines(True)
        if self.sort_button.get_active():  # Only if sorted by executions
            # column 0
            renderer_number = Gtk.CellRendererText()
            renderer_number.set_property('scale', 2)
            renderer_number.set_property('single-paragraph-mode', True)
            execution_number = Gtk.TreeViewColumn('Run ', renderer_number, text=11)
            execution_number.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
            execution_number.set_resizable(True)
            execution_number.set_min_width(50)
            self.view.append_column(execution_number)

        # column 1
        renderer_number = Gtk.CellRendererText()
        if not self.sort_button.get_active():  # Only big if sorted by steps, otherwise normal size
            renderer_number.set_property('scale', 2)
            renderer_number.set_property('single-paragraph-mode', True)
        column_number = Gtk.TreeViewColumn('Step', renderer_number, text=8)
        column_number.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_number.set_resizable(True)
        column_number.set_min_width(50)
        self.view.append_column(column_number)

        # column 2
        renderer_exec_date = Gtk.CellRendererText()
        column_exec_date = Gtk.TreeViewColumn('Execution date', renderer_exec_date, text=1, background=7)
        column_exec_date.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_exec_date.set_resizable(True)
        column_exec_date.set_min_width(50)
        self.view.append_column(column_exec_date)

        # column 3
        renderer_type = Gtk.CellRendererText()
        column_type = Gtk.TreeViewColumn('Type', renderer_type, text=2, background=7)
        column_type.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_type.set_resizable(True)
        column_type.set_min_width(50)
        self.view.append_column(column_type)

        # column 4
        renderer_cmd_version = Gtk.CellRendererText(xalign=0.5)
        column_cmd_version = Gtk.TreeViewColumn('Spec. Version', renderer_cmd_version, text=3, background=7)
        column_cmd_version.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_cmd_version.set_resizable(True)
        column_cmd_version.set_min_width(50)
        self.view.append_column(column_cmd_version)

        # column 5
        renderer_cmd_status = Gtk.CellRendererText()
        column_cmd_status = Gtk.TreeViewColumn('Status', renderer_cmd_status, text=4, background=7)
        column_cmd_status.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_cmd_status.set_resizable(True)
        column_cmd_status.set_min_width(50)
        self.view.append_column(column_cmd_status)

        # column 6
        renderer_tcs = Gtk.CellRendererText()
        column_tcs = Gtk.TreeViewColumn('TC\'s sent', renderer_tcs, text=5, background=7)
        column_tcs.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_tcs.set_resizable(True)
        column_tcs.set_min_width(50)
        self.view.append_column(column_tcs)

        # column 7
        # def set_bkgrd_clr(column, cell, model, iter, user_data):
        #     if model[iter][6] == 'object-select-symbolic':
        #         cell.set_property('cell-background', '#333333')
        #     if model[iter][6] == 'window-close-symbolic':
        #         cell.set_property('cell-background', '#666666')
        # renderer_result = Gtk.CellRendererPixbuf()
        # renderer_result.set_property('cell-background', 7)
        # column_result = Gtk.TreeViewColumn('Result', renderer_result, icon_name=6)
        # # column_result.set_cell_data_func(cell_renderer=renderer_result, func=set_bkgrd_clr, func_data=None)
        # self.view.append_column(column_result)
        renderer_result = Gtk.CellRendererText()
        renderer_result.set_property('xalign', 0.5)
        column_result = Gtk.TreeViewColumn('Result', renderer_result, text=6, background=9)
        column_result.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_result.set_resizable(True)
        column_result.set_min_width(50)
        # column_result.set_cell_data_func(cell_renderer=renderer_result, func=set_bkgrd_clr, func_data=None)
        self.view.append_column(column_result)
        return

    def get_log_file_paths_from_json_file_name(self, filename):
        from testlib import testing_logger
        paths = {}
        try:
            current_file_name = os.path.basename(filename)
            path_test_specs = cfg.get(section='tst-paths', option='tst_products')
            path_test_runs = cfg.get(section='tst-logging', option='test_run')

            json_file_path = os.path.join(path_test_specs, current_file_name)
            paths['json_file_path'] = json_file_path

            name = generator.strip_file_extension(current_file_name)
            cmd_log_file_path = os.path.join(path_test_runs, name + testing_logger.cmd_log_auxiliary)
            paths['cmd_log_file_path'] = cmd_log_file_path

            vrc_log_file_path = os.path.join(path_test_runs, name + testing_logger.vrc_log_auxiliary)
            paths['vrc_log_file_path'] = vrc_log_file_path
        except Exception as e:
            self.logger.info('Json or Log Files could not be found')
            return ''
        return paths

    def open_test_files(self, simple_action, paths, *args):
        logger.debug('Opening files... ')
        try:
            self.path_json = paths['json_file_path']
            self.text_path_json_btn.set_file(Gio.File.new_for_path(self.path_json))
        except:
            logger.debug('JSon File could not be opened')

        try:
            self.path_cmd = paths['cmd_log_file_path']
            self.text_path_cmd_btn.set_file(Gio.File.new_for_path(self.path_cmd))
            self.monitor_cmd = Gio.File.new_for_path(self.path_cmd).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor_cmd.set_rate_limit(100)
            self.monitor_cmd.connect('changed', self.file_cmd_changed)
        except:
            logger.debug('Commond log File could not be opened')

        try:
            self.path_vrc = paths['vrc_log_file_path']
            self.text_path_vrc_btn.set_file(Gio.File.new_for_path(self.path_vrc))
            self.monitor_vrc = Gio.File.new_for_path(self.path_vrc).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self.monitor_vrc.set_rate_limit(100)
            self.monitor_vrc.connect('changed', self.file_vrc_changed)
        except:
            logger.debug('Verification log File could not be opened')

        self.on_reload_all()
        self.on_expand_all_rows()
        self.refresh_worker()

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
        self.box.reorder_child(self.info_bar, 1)
        # add the text:
        self.info_bar.get_content_area().pack_start(
            Gtk.Label(message),
            False, False, 0)
        self.info_bar.connect('response', self.remove_info_bar)
        self.show_all()

    def remove_info_bar(self, infobar, response_id):
        if response_id == -7:
            infobar.destroy()

    def add_filters(self, dialog):
        """
        Add the option to filter files in the file choosing dialog
        :param Gtk.FileChooserDialog dialog: FileChooserDialog
        """
        filter_text = Gtk.FileFilter()
        filter_text.set_name('JSON format')
        filter_text.add_mime_type('application/json')
        filter_text.add_pattern('.json')
        dialog.add_filter(filter_text)

        filter_any = Gtk.FileFilter()
        filter_any.set_name('Any files')
        filter_any.add_pattern('*')
        dialog.add_filter(filter_any)

    def set_path_json_file(self, widget):
        """
        Set the path of the Test Specification JSON file as class attribute.
        Loads the Test Specification into the TreeView
        :param Gtk.FileChooserButton widget: The FileChooserButton which was clicked
        """
        self.path_json = widget.get_filename()
        self.load_json(self.path_json)

    def set_path_cmd_file(self, widget):
        """
        Set the path of the command log file as class attribute.
        Loads the command log into the TreeView
        :param Gtk.FileChooserButton widget: The FileChooserButton which was clicked
        """
        self.path_cmd = widget.get_filename()
        self.load_cmd(self.path_cmd)

    def set_path_vrc_file(self, widget):
        """
        Set the path of the verification log file as class attribute.
        Loads the verifiction log file into the TreeView
        :param Gtk.FileChooserButton widget: The FileChooserButton which was clicked
        """
        self.path_vrc = widget.get_filename()
        self.load_vrc(self.path_vrc)

    def file_cmd_changed(self, monitor, file, o, event):
        if event == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            self.load_cmd(self.path_cmd)
            self.on_expand_all_rows()

    def file_vrc_changed(self, monitor, file, o, event):
        if event == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            self.load_vrc(self.path_vrc)
            self.on_expand_all_rows()

    def gather_expanded_states(self, tree_store):
        # gather the expanded states of all drawer rows
        for row in tree_store:
            tree_path = tree_store.get_path(row.iter)
            expanded = self.view.row_expanded(tree_path)
            if not tree_store.iter_has_child(row.iter):
                expanded = None
            self.expander_states.append((row[0], expanded, tree_path))

    def restore_expanded_states(self, tree_store):
        # restore the expander states
        for row in tree_store:
            row_step_num = row[0]
            for entry in self.expander_states:
                step_num = entry[0]
                if row_step_num == step_num:
                    if entry[1] is True:
                        self.view.expand_row(entry[2], False)
                    else:
                        self.view.collapse_row(entry[2])

    def on_expand_all_rows(self, *args):
        self.view.expand_all()

    def on_collapse_all_rows(self, *args):
        self.view.collapse_all()

    def refresh_worker(self):
        GLib.timeout_add_seconds(self.refresh_rate, self.on_reload_all)

    def on_remake_treeview(self, *args):
        if self.sort_button.get_active():
            self.progress_tree_store = Gtk.TreeStore(str, str, str, str, str, str, str, str, str, str, str, str, str)
            self.scroll_win.set_min_content_width(int(cfg.get(section='progress-viewer-window-size', option='minimum-width-run-mode')))
            if self.get_size()[0] == int(cfg.get(section='progress-viewer-window-size', option='basic-width-step-mode')):
                self.resize(int(cfg.get(section='progress-viewer-window-size', option='basic-width-run-mode')), self.get_size()[1])
        else:
            self.progress_tree_store = Gtk.TreeStore(str, str, str, str, str, str, str, str, str, str, str)
            self.scroll_win.set_min_content_width(int(cfg.get(section='progress-viewer-window-size', option='minimum-width-step-mode')))
            if self.get_size()[0] == int(cfg.get(section='progress-viewer-window-size', option='basic-width-run-mode')):
                self.resize(int(cfg.get(section='progress-viewer-window-size', option='basic-width-step-mode')), self.get_size()[1])
        self.sorted_model = Gtk.TreeModelSort(model=self.progress_tree_store)
        self.sorted_model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        self.view.set_model(self.sorted_model)
        all_columns = self.view.get_columns()
        for column in all_columns:
            self.view.remove_column(column)
        self.make_treeview()
        self.on_reload_all()


    def on_reload_all(self, *args):
        if self.path_json:
            self.load_json(self.path_json)
        if self.path_cmd:
            self.load_cmd(self.path_cmd)
        if self.path_vrc:
            self.load_vrc(self.path_vrc)


    def on_clear_cmd_log(self, *args):
        with open(self.path_cmd, 'w') as cmd_log:
            cmd_log.write('')
            cmd_log.close()

    def on_clear_vrc_log(self, *args):
        with open(self.path_vrc, 'w') as vrc_log:
            vrc_log.write('')
            vrc_log.close()


    def on_save_as(self, *args):
        self.save_as_file_dialog()
        return

    def save_as_file_dialog(self):
        # If one log file is loaded use it as Log file path, otherwise ask for it in separate dialog
        test_name = None
        if self.path_cmd:
            file_name = self.path_cmd.split('/')[-1]
            log_file_path = self.path_cmd[:-len(file_name)]
            test_name = file_name.split('_')[0]
        elif self.path_vrc:
            file_name = self.path_vrc.split('/')[-1]
            log_file_path = self.path_vrc[:-len(file_name)]
            test_name = file_name.split('_')[0]
        else:
            log_file_path=None

        if not test_name and self.path_json:
            test_name = self.path_json.split('/')[-1].split('.')[0]

        dialog = Save_to_File_Dialog(parent=self)  # Look were the output file should be saved and which files (log, json) should be used
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            if not test_name:
                test_name = dialog.test_name.get_text()
                if not test_name:
                    dialog.destroy()
                    self.logger.info('Can not create Output file without test name')
                    return

            folder = dialog.get_current_folder()
            run_count = dialog.run_id_selection.get_active()
            test_report = dialog.test_report_int.get_text()
            sent_run_id = None
            if run_count:
                for run_id in self.run_count.keys():
                    if self.run_count[run_id] == str(run_count):
                        sent_run_id = run_id
            if not log_file_path:
                if not dialog.log_file_path_check.get_active():
                    log_file_path = 'FIND'
            if not self.path_json:
                if dialog.log_file_path_check.get_active():
                    json_file_path = None
                else:
                    json_file_path = 'FIND'
            else:
                json_file_path = self.path_json

        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()
            return

        dialog.destroy()
        if log_file_path == 'FIND':  # Get the log file path if they are not already given
            dialog = File_Path_Dialog(parent=self, file='Command or Verification Log File', is_json=False)
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                log_file_path = dialog.get_current_folder()
            elif response == Gtk.ResponseType.CANCEL:
                dialog.destroy()
                return
        dialog.destroy()

        if json_file_path == 'FIND':  # Get the json file if it is not already given
            dialog = File_Path_Dialog(parent=self, file='the Json File', is_json=True)
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                json_file_path = dialog.get_filename()
            elif response == Gtk.ResponseType.CANCEL:
                dialog.destroy()
                return

        dialog.destroy()

        analyse_test_run.save_result_to_file(test_name=test_name, log_file_path=log_file_path, output_file_path=folder,
                                             json_file_path=json_file_path, run_id=sent_run_id, test_report=test_report,
                                             logger=self.logger)

        return

    def on_destroy(self, *args):
        self.logger.info('Self-Destruct of the ProgressView Window initiated.\n')
        self.destroy()

    # ------------------- model functions ----------------------
    @staticmethod
    def build_row_list(row=None, step_number=None, exec_date=None, entry_type=None, spec_version=None, status=None, tcs=None,
                       result=None, step_desc=None, tooltip_text=None, exec_int=None, exec_desc=None, sort_button_active=False):
        """
        Builds or updates a row of the TreeStore. For a new row, the argument 'row' is expected to be None.
        :param Gtk.TreeModelRow row: a row of the tree model
        :param str step_number:
        :param datetime.datetime exec_date:
        :param str entry_type:
        :param str spec_version:
        :param str status:
        :param str tcs:
        :param boolean result:
        :param str step_desc:
        :return: list of the arguments or a TreeModelRow
        :rtype: list or TreeModelRow

        """

        def set_result_cell_color(res):
            if res is True:
                return cell_result_passed
            else:
                return cell_result_failed

        def set_result_row(res):
            if res is True:
                return 'passed'
            else:
                return 'failed'

        sort_adjustment = 1 if sort_button_active else 0

        entry_background = None
        if exec_date is not None:
            exec_date = datetime.datetime.strftime(exec_date, testing_logger.date_time_format)
        if result is not None:
            result_value = set_result_row(res=result)
            result_cell_color = set_result_cell_color(res=result)
        else:
            result_value = None
            result_cell_color = None

        if row is not None:
            # update existing row
            if sort_button_active:
                if exec_int:
                    row[12] = exec_int
                if exec_desc:
                    row[11] = exec_desc
            if step_number is not None:
                row[0] = step_number
            if exec_date is not None:
                row[1] = exec_date
            if entry_type is not None:
                row[2] = entry_type
            if spec_version is not None:
                row[3] = spec_version
            if status is not None:
                row[4] = status
            if tcs is not None:
                row[5] = tcs
            if result is not None:
                row[6] = result_value
                row[9] = result_cell_color
            if step_desc is not None:
                row[8] = step_desc
        else:
            # build a new row
            if sort_button_active:
                row = [
                    step_number,
                    exec_date,
                    entry_type,
                    spec_version,
                    status,
                    tcs,
                    result_value,
                    entry_background,
                    step_desc,
                    result_cell_color,
                    tooltip_text,
                    exec_desc,
                    exec_int
                ]
            else:
                row = [
                    step_number,
                    exec_date,
                    entry_type,
                    spec_version,
                    status,
                    tcs,
                    result_value,
                    entry_background,
                    step_desc,
                    result_cell_color,
                    tooltip_text
                ]
        # set the background color of the rows
        if row[2] == 'command':
            entry_background = row_cmd_color
        elif row[2] == 'verification':
            entry_background = row_vrc_color
        elif row[2] == 'specification':
            entry_background = row_spec_color
        else:
            entry_background = row_step_drawer_color_odd
        row[7] = entry_background
        return row

    # No longer used
    def add_detailed_row(self, inner_row_iter, tree_store):
        """
        Was used to add an additional row (only if sorted by steps) to show more detailed information about a step, it
        was seen that only the description is needed and it is easier shown as a tooltip text, stays here if more
        information is wanted some day
        """
        detailed_info=[]
        for count, item in enumerate(tree_store[inner_row_iter]):
            if count in [0,7,9]:  # Stepnumber, colour, colour
                detailed_info.append(item)
            elif count == 1:
                detailed_info.append('Description:')
            elif count == 2:
                if self.test_model:
                    detailed_info.append('{}'.format(self.test_model.description))
                else:
                    detailed_info.append('Json File has to be given')
            elif count == 4:
                if tree_store[inner_row_iter][2] == 'command':
                    detailed_info.append('Command Code:')
                elif tree_store[inner_row_iter][2] == 'verification':
                    detailed_info.append('Verification Code:')
                else:
                    detailed_info.append('Error Code:')
            elif count == 5:
                detailed_info.append('Code')
            elif count in [3, 6, 8, 10]:
                detailed_info.append('')

        new_row_iter = tree_store.append(inner_row_iter, detailed_info)

    def set_test_title(self):
        json_title = self.test_model.name if self.test_model else None
        test_desc = self.test_model.description if self.test_model else None
        cmd_title = self.text_path_cmd_btn.get_filename() if self.text_path_cmd_btn.get_filename() else None
        test_desc = analyse_command_log.get_test_description(self.path_cmd) if not test_desc else test_desc
        vrc_title = self.text_path_vrc_btn.get_filename().split('_')[0] if self.text_path_vrc_btn.get_filename() else None
        if json_title:
            self.test_title.set_markup('<b><big>{}</big></b>\t{}'.format(json_title.split('/')[-1], test_desc))
        elif cmd_title:
            self.test_title.set_markup('<b><big>{}</big></b>\t{}'.format(cmd_title.split('/')[-1].split('_')[0], test_desc))
        elif vrc_title:
            self.test_title.set_markup('<b><big>{}</big></b>\t{}'.format(vrc_title.split('/')[-1].split('_')[0], test_desc))
        else:
            self.test_title.set_text('')

    def load_json(self, filepath):

        if not os.path.isfile(filepath):
            message = 'load_file: no file found for the path {}'.format(filepath)
            logger.warning(message)
            self.add_info_bar(message_type=Gtk.MessageType.WARNING, message=message)
        else:
            data_from_file = None
            with open(filepath, 'r') as file:
                data = file.read()
                data_from_file = json.loads(data)
            file.close()
            if data_from_file is not None:
                self.test_model = data_model.TestSpecification()
                self.test_model.decode_from_json(json_data=data_from_file)
                if not self.sort_button.get_active():  # Only add json steps, if sorted by steps
                    self.load_model_into_tree_store(self.progress_tree_store, self.test_model)
            else:
                logger.warning('load_file: could not read from the JSON test spec')
            self.set_test_title()

    def load_cmd(self, filepath):
        if not os.path.isfile(filepath):
            message = 'load_file: no file found for the path {}'.format(filepath)
            logger.warning(message)
            self.add_info_bar(message_type=Gtk.MessageType.WARNING, message=message)
        else:
            # analyse the command log
            self.cmd_steps = analyse_command_log.get_steps_and_commands(filepath)
            self.load_cmd_into_tree_store(self.progress_tree_store, self.cmd_steps)
            self.set_test_title()

    def load_vrc(self, filepath):
        if not os.path.isfile(filepath):
            message = 'load_file: no file found for the path {}'.format(filepath)
            logger.warning(message)
            self.add_info_bar(message_type=Gtk.MessageType.WARNING, message=message)
        else:
            # analyse the verification log
            self.vrc_steps = analyse_verification_log.get_verification_steps(filepath)
            self.load_vrc_into_tree_store(self.progress_tree_store, self.vrc_steps)
            self.set_test_title()

    def load_model_into_tree_store(self, tree_store, test_model):

        # collect the information if the drawer rows are expanded, in order to restore this states
        self.gather_expanded_states(tree_store)
        # check which step numbers are already in the tree_store
        tree_store_steps = []
        for row in tree_store:
            step_number_tree_store = row[0:1][0]
            tree_store_steps.append(step_number_tree_store)
        # add drawer for each step which is not in the tree_store already
        # ToDo: only the first sequence is loaded, at the moment only one is supported, but if that changes, this
        #  has to be changed as well, (Dominik)
        for step in test_model.sequences[0].steps:
            step_number = step.step_number_test_format
            if step_number not in tree_store_steps:
                # Secondary Counter is not shown if it is 0
                step_number_primary, step_number_secondary = step_number.split('_')
                step_number_shown = step_number_primary if int(step_number_secondary) == 0 else '{}.{}'.format(step_number_primary, step_number_secondary)
                step_desc = 'Step ' + str(step_number_shown)

                new_drawer_row = self.build_row_list(step_number=str(step_number),
                                                     step_desc=step_desc,
                                                     sort_button_active=self.sort_button.get_active(),
                                                     tooltip_text=step.description)

                tree_store.append(None, new_drawer_row)
                tree_store_steps.append(step_number)

        # # remove all existing specifications
        # for row in tree_store:
        #   for item in row.iterchildren():
        #       if item[2] == 'specification':
        #           tree_store.remove(item.iter)
        # # add a row for (**each spec version of**) the step specification
        # for row in tree_store:
        #     step_number_tree_store = int(row[0:1][0])
        #     for key in test_model.steps_dict:
        #         step_number = int(test_model.steps_dict[key].step_number)
        #         if step_number_tree_store == step_number:
        #             model_version = str(test_model.version)
        #             status = ''
        #             if test_model.steps_dict[key].command_code == '':
        #                 status += 'no cmd code; '
        #             if test_model.steps_dict[key].verification_code == '':
        #                 status += 'no vrc code; '
        #             if status == '':
        #                 new_row_list = self.build_row_list(version=model_version,
        #                                                    entry_type='specification',
        #                                                    status=status,
        #                                                    result=True)
        #             else:
        #                 new_row_list = self.build_row_list(version=model_version,
        #                                                    entry_type='specification',
        #                                                    status=status,
        #                                                    result=False)
        #             tree_store.append(row.iter, new_row_list)
        self.restore_expanded_states(tree_store)

    def load_cmd_into_tree_store(self, tree_store, cmd_steps):
        """
        For every step in the command log, add the information to the tree store
        :param tree_store:
        :param cmd_steps:
        :return:
        """
        # collect the information if the drawer rows are expanded, in order to restore this states
        self.gather_expanded_states(tree_store)
        if self.sort_button.get_active():
            # check which executions are already in the tree store
            tree_store_exec = {}
            for row in tree_store:
                if row[12]:
                    tree_store_exec[row[12]] = []
            # check which steps are in each execution
            for row in tree_store:
                if row[12]:
                    for item in row.iterchildren():
                        if item[0]:
                            tree_store_exec[row[12]].append(item[0])

            all_exec_numbers = {}
            # get all executions
            for item in cmd_steps:
                all_exec_numbers[str(item['run_id'])] = []
            # get all steps for every execution
            for item in cmd_steps:
                all_exec_numbers[str(item['run_id'])].append(item)

            # make execution drawers
            for exec_num in all_exec_numbers.keys():
                if not exec_num in tree_store_exec.keys():
                    if exec_num not in self.run_count.keys():
                        self.run_count[exec_num] = str(len(self.run_count) + 1)
                    exec_desc = 'Run ' + self.run_count[exec_num]
                    tooltip = '{}-{}-{} {}:{}:{}'.format(exec_num[0:4], exec_num[4:6], exec_num[6:8], exec_num[8:10],
                                                         exec_num[10:12], exec_num[12:14])
                    new_drawer_row = self.build_row_list(exec_int=str(exec_num),
                                                         exec_desc=exec_desc,
                                                         sort_button_active=self.sort_button.get_active(),
                                                         tooltip_text=tooltip)
                    tree_store.append(None, new_drawer_row)
                    tree_store_exec[exec_num] = []

            # make step drawers for every execution drawer
            for row in tree_store:
                if row[12]:
                    exec_num = row[12]
                    for step in all_exec_numbers[exec_num]:
                        if not step['step'] in tree_store_exec[exec_num]:
                            # Secondary Counter is not shown if it is 0
                            step_number_primary, step_number_secondary = step['step'].split('_')
                            step_number_shown = step_number_primary if int(
                                step_number_secondary) == 0 else '{}.{}'.format(step_number_primary,
                                                                                step_number_secondary)
                            step_desc = 'Step ' + str(step_number_shown)
                            new_step_row = self.build_row_list(step_number=str(step['step']),
                                                               step_desc=step_desc,
                                                               sort_button_active=self.sort_button.get_active(),
                                                               tooltip_text=step['descr'])
                            new_row_iter = tree_store.append(row.iter, new_step_row)
                            tree_store_exec[exec_num].append(step['step'])

            # clear all command rows, before adding
            for row in tree_store:
                if row[12]:
                    for step_row in row.iterchildren():
                        for item in step_row.iterchildren():
                            if item[2] == 'command':
                                tree_store.remove(item.iter)

            # add rows for command
            for row in tree_store:
                if row[12]:
                    exec_num = row[12]
                    for step_row in row.iterchildren():
                        if step_row[0]:
                            step_num = step_row[0]
                            for item in cmd_steps:
                                if item['run_id'] == exec_num and item['step'] == step_num:
                                    new_row_list = self.build_row_list(entry_type='command',
                                                                       spec_version=item['spec_version'],
                                                                       exec_date=item['exec_date'],
                                                                       sort_button_active=self.sort_button.get_active(),
                                                                       tooltip_text=item['descr'])
                                    new_row_iter = tree_store.append(step_row.iter, new_row_list)
                                    new_row = tree_store[new_row_iter]
                                    # add the information if the step was executed or had an exception
                                    if 'exception' in item:
                                        self.build_row_list(row=new_row,
                                                            status='EXCEPTION',
                                                            result=False,
                                                            sort_button_active=self.sort_button.get_active())
                                    else:
                                        if 'end_timestamp' in item:
                                            self.build_row_list(row=new_row,
                                                                status='executed',
                                                                result=True,
                                                                sort_button_active=self.sort_button.get_active())
                                    # add the TC's
                                    tcs_str = ''
                                    for telecommand in item['tcs']:
                                        if tcs_str != '':
                                            tcs_str += ', '
                                        tcs_str += telecommand.tc_kind()
                                    self.build_row_list(row=new_row,
                                                        tcs=tcs_str,
                                                        sort_button_active=self.sort_button.get_active())

                                    #self.add_detailed_row(new_row_iter, tree_store)

        else:
            # check which step numbers are already in the tree_store
            tree_store_steps = []
            for row in tree_store:
                step_number_tree_store = row[0:1][0]
                tree_store_steps.append(step_number_tree_store)
            # add drawer for each step which is not in the tree_store already
            for item in cmd_steps:
                step_number = item['step']
                if step_number not in tree_store_steps:
                    # Secondary Counter is not shown if it is 0
                    step_number_primary, step_number_secondary = step_number.split('_')
                    step_number_shown = step_number_primary if int(
                        step_number_secondary) == 0 else '{}.{}'.format(step_number_primary,
                                                                        step_number_secondary)
                    step_desc = 'Step ' + str(step_number_shown)
                    new_drawer_row = self.build_row_list(step_number=str(step_number),
                                                         step_desc=step_desc,
                                                         sort_button_active=self.sort_button.get_active(),
                                                         tooltip_text=item['descr'])
                    tree_store.append(None, new_drawer_row)
                    tree_store_steps.append(step_number)
            # clear all command rows, before adding
            for row in tree_store:
                for item in row.iterchildren():
                    if item[2] == 'command':
                        tree_store.remove(item.iter)
            # add rows for command
            for row in tree_store:
                #self.view.set_tooltip_column()
                step_number_tree_store = row[0:1][0]
                for item in cmd_steps:
                    step_number_cmd = item['step']
                    if step_number_tree_store == step_number_cmd:
                        # already_exists = False
                        # for i in row.iterchildren():
                        #     if datetime.datetime.strftime(item['exec_date'], testing_logger.date_time_format) == i[1]:
                        #         already_exists = True
                        # # add a new row
                        # if not already_exists:
                        new_row_list = self.build_row_list(entry_type='command',
                                                           spec_version=item['spec_version'],
                                                           exec_date=item['exec_date'],
                                                           sort_button_active=self.sort_button.get_active(),
                                                           tooltip_text=item['descr'])
                        new_row_iter = tree_store.append(row.iter, new_row_list)
                        new_row = tree_store[new_row_iter]

                        # add the information if the step was executed or had an exception
                        if 'exception' in item:
                            self.build_row_list(row=new_row,
                                                status='EXCEPTION',
                                                result=False,
                                                sort_button_active=self.sort_button.get_active())
                        else:
                            if 'end_timestamp' in item:
                                self.build_row_list(row=new_row,
                                                    status='executed',
                                                    result=True,
                                                    sort_button_active=self.sort_button.get_active())
                        # add the TC's
                        tcs_str = ''
                        for telecommand in item['tcs']:
                            if tcs_str != '':
                                tcs_str += ', '
                            tcs_str += telecommand.tc_kind()
                        self.build_row_list(row=new_row,
                                            tcs=tcs_str,
                                            sort_button_active=self.sort_button.get_active())

                        #self.add_detailed_row(new_row_iter, tree_store)

        self.restore_expanded_states(tree_store)

    def load_vrc_into_tree_store(self, tree_store, vrc_steps):

        # collect the information if the drawer rows are expanded, in order to restore this states
        self.gather_expanded_states(tree_store)

        if self.sort_button.get_active():
            # check which executions are already in the tree store
            tree_store_exec = {}
            for row in tree_store:
                if row[12]:
                    tree_store_exec[row[12]] = []
            # check which steps are in each execution
            for row in tree_store:
                if row[12]:
                    for item in row.iterchildren():
                        if item[0]:
                            tree_store_exec[row[12]].append(item[0])

            all_exec_numbers = {}
            # get all executions
            for item in vrc_steps:
                all_exec_numbers[str(item['run_id'])] = []
            # get all steps for every execution
            for item in vrc_steps:
                all_exec_numbers[str(item['run_id'])].append(item)

            # make execution drawers
            for exec_num in all_exec_numbers.keys():
                if not exec_num in tree_store_exec.keys():
                    if exec_num not in self.run_count.keys():
                        self.run_count[exec_num] = str(len(self.run_count) + 1)
                    exec_desc = 'Run ' + self.run_count[exec_num]
                    tooltip = '{}-{}-{} {}:{}:{}'.format(exec_num[0:4], exec_num[4:6], exec_num[6:8], exec_num[8:10],
                                                         exec_num[10:12], exec_num[12:14])
                    new_drawer_row = self.build_row_list(exec_int=str(exec_num),
                                                         exec_desc=exec_desc,
                                                         sort_button_active=self.sort_button.get_active(),
                                                         tooltip_text=tooltip)
                    tree_store.append(None, new_drawer_row)
                    tree_store_exec[exec_num] = []

            # make step drawers for every execution drawer
            for row in tree_store:
                if row[12]:
                    exec_num = row[12]
                    for step in all_exec_numbers[exec_num]:
                        if not step['step'] in tree_store_exec[exec_num]:
                            # Secondary Counter is not shown if it is 0
                            step_number_primary, step_number_secondary = step['step'].split('_')
                            step_number_shown = step_number_primary if int(
                                step_number_secondary) == 0 else '{}.{}'.format(step_number_primary,
                                                                                step_number_secondary)
                            step_desc = 'Step ' + str(step_number_shown)
                            new_step_row = self.build_row_list(step_number=str(step['step']),
                                                               step_desc=step_desc,
                                                               sort_button_active=self.sort_button.get_active(),
                                                               tooltip_text=step['descr'])
                            new_row_iter = tree_store.append(row.iter, new_step_row)
                            tree_store_exec[exec_num].append(step['step'])

            # clear all verification rows, before adding
            for row in tree_store:
                if row[12]:
                    for step_row in row.iterchildren():
                        for item in step_row.iterchildren():
                            if item[2] == 'verification':
                                tree_store.remove(item.iter)

            # add rows for verification
            for row in tree_store:
                if row[12]:
                    exec_num = row[12]
                    for step_row in row.iterchildren():
                        if step_row[0]:
                            step_num = step_row[0]
                            for item in vrc_steps:
                                if item['run_id'] == exec_num and item['step'] == step_num:
                                    new_row_list = self.build_row_list(entry_type='verification',
                                                                       spec_version=item['spec_version'],
                                                                       exec_date=item['exec_date'],
                                                                       sort_button_active=self.sort_button.get_active(),
                                                                       tooltip_text=item['descr'])
                                    new_row_iter = tree_store.append(step_row.iter, new_row_list)
                                    new_row = tree_store[new_row_iter]
                                    # add the information if the step was executed or had an exception
                                    if 'exception' in item:
                                        self.build_row_list(row=new_row,
                                                            status='EXCEPTION',
                                                            sort_button_active=self.sort_button.get_active())
                                    else:
                                        if 'end_timestamp' in item:
                                            self.build_row_list(row=new_row,
                                                                status='executed',
                                                                sort_button_active=self.sort_button.get_active())
                                    if 'result' in item:
                                        if item['result'] is True:
                                            self.build_row_list(row=new_row,
                                                                result=True,
                                                                sort_button_active=self.sort_button.get_active())
                                        else:
                                            self.build_row_list(row=new_row,
                                                                result=False,
                                                                sort_button_active=self.sort_button.get_active())

        else:
            # check which step numbers are already in the tree_store
            tree_store_steps = []
            for row in tree_store:
                step_number_tree_store = row[0:1][0]
                tree_store_steps.append(step_number_tree_store)
            # add drawer for each step which is not in the tree_store already
            for item in vrc_steps:
                step_number = item['step']
                if step_number not in tree_store_steps:
                    # Secondary Counter is not shown if it is 0
                    step_number_primary, step_number_secondary = step_number.split('_')
                    step_number_shown = step_number_primary if int(
                        step_number_secondary) == 0 else '{}.{}'.format(step_number_primary,
                                                                        step_number_secondary)
                    step_desc = 'Step ' + str(step_number_shown)
                    new_drawer_row = self.build_row_list(step_number=str(step_number),
                                                         step_desc=step_desc,
                                                         sort_button_active=self.sort_button.get_active(),
                                                         tooltip_text=item['descr'])
                    tree_store.append(None, new_drawer_row)
                    tree_store_steps.append(step_number)
            # clear all verification rows, before adding
            for row in tree_store:
                for item in row.iterchildren():
                    if item[2] == 'verification':
                        tree_store.remove(item.iter)
            # add row for verification
            for row in tree_store:
                step_number_tree_store = row[0:1][0]
                for item in vrc_steps:
                    step_number_vrc = item['step']
                    if step_number_tree_store == step_number_vrc:
                        # already_exists = False
                        # for i in row.iterchildren():
                        #     if datetime.datetime.strftime(item['exec_date'], testing_logger.date_time_format) == i[1]:
                        #         already_exists = True
                        # # add a new row
                        # if not already_exists:
                        new_row_list = self.build_row_list(entry_type='verification',
                                                           spec_version=item['spec_version'],
                                                           exec_date=item['exec_date'],
                                                           sort_button_active=self.sort_button.get_active(),
                                                           tooltip_text=item['descr'])
                        new_row_iter = tree_store.append(row.iter, new_row_list)
                        new_row = tree_store[new_row_iter]
                        # add the information if the step was executed or had an exception
                        if 'exception' in item:
                            self.build_row_list(row=new_row,
                                                status='EXCEPTION',
                                                sort_button_active=self.sort_button.get_active())
                        else:
                            if 'end_timestamp' in item:
                                self.build_row_list(row=new_row,
                                                    status='executed',
                                                    sort_button_active=self.sort_button.get_active())
                        if 'result' in item:
                            if item['result'] is True:
                                self.build_row_list(row=new_row,
                                                    result=True,
                                                    sort_button_active=self.sort_button.get_active())
                            else:
                                self.build_row_list(row=new_row,
                                                    result=False,
                                                    sort_button_active=self.sort_button.get_active())
                        #self.add_detailed_row(new_row_iter, tree_store)
            self.restore_expanded_states(tree_store)


class Save_to_File_Dialog(Gtk.FileChooserDialog):
    def __init__(self, parent=None):
        super(Save_to_File_Dialog, self).__init__(title='Please choose a Folder to save the Test Run',
                                       parent=parent,
                                       action=Gtk.FileChooserAction.OPEN_FOLDER)

        self.win = parent
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        self.set_current_folder(cfg.get(section='tst-logging', option='output-file-path'))
        #self.set_current_name('{}-IASW-{}TS-{}TR-{}'.format())

        area = self.get_content_area()

        self.savedetailes = Gtk.HBox()  # Store everything in this box
        self.savedetailes.set_border_width(15)

        # Only shown if a name was not given (Found from Log Files or Json File in main window
        name_label = Gtk.Label(label='Test Name: ')
        self.test_name = Gtk.Entry()
        self.test_name.set_tooltip_text('The name of the Test')

        # Only shown if Log File path was not given (Found from loaded log File in main window)
        log_file_path_label = Gtk.Label(label='Use Basic Log File Path: ')
        log_file_path_label.set_tooltip_text('Basic File Path: {}'.format(cfg.get('tst-logging', 'test_run')))
        self.log_file_path_check = Gtk.CheckButton()
        self.log_file_path_check.set_active(True)

        # Only shown if Json File path was not given (Found from loaded json file in main window)
        json_file_path_label = Gtk.Label(label='Use Basic Json File Path: ')
        json_file_path_label.set_tooltip_text(
            'Basic File Path: {}, Also True if No Json File should be used (Specification Date in Output File will be empty)'.format(
                cfg.get('tst-paths', 'tst_products')))
        self.json_file_path_check = Gtk.CheckButton()
        self.json_file_path_check.set_active(True)

        run_id_label = Gtk.Label(label='Select Run ID: ')

        # Select the Run ID which should be printed to the File
        self.run_id_selection = Gtk.ComboBoxText.new()  # Make the Combobox
        if not self.win.sort_button.get_active():  # If sorted by steps, run id is not defined
            self.run_id_selection.append_text('Whole Log File')  # Only possible selection is to save whole file
            self.run_id_selection.set_button_sensitivity(False)
            self.run_id_selection.set_active(0)
            self.run_id_selection.set_tooltip_text('If Sorted by Executions, it is possible to limit the Output File to just one Run')
        else:  # If sorted by executions add all available run ids
            self.run_id_selection.append('0', 'Whole Log File')  # Give also the possibility to save whole file
            for run_id in self.win.run_count:
                self.run_id_selection.append(run_id, 'Run ' + self.win.run_count[run_id])  # Add all Run ids

            model, iter = self.win.view.get_selection().get_selected()  # Get selected treeview row
            if iter:  # If a selection is made try to set it as active row, otherwise Whole file is active row
                selected_step_id = model.get_value(iter, 12)  # Get the value
                if not selected_step_id:  # Only execution rows ('Run X') have entry at coloumn 12, others dont
                    try:
                        self.run_id_selection.set_active(1)
                    except:
                        self.run_id_selection.set_active(0)
                else:
                    self.run_id_selection.set_active(int(self.win.run_count[selected_step_id]))
            else:
                try:
                    self.run_id_selection.set_active(1)
                except:
                    self.run_id_selection.set_active(0)
            self.run_id_selection.set_tooltip_text('Define which Run should be saved or the whole Log File')

        test_report_label = Gtk.Label(label='Test Report: ')

        self.test_report_int = Gtk.Entry()
        self.test_report_int.set_tooltip_text('Select the Test Report Number (1-999) NOTE: Prior Versions could be overwritten, If emtpy it will be automatically generated')

        self.savedetailes.pack_end(self.run_id_selection, False, True, 10)
        self.savedetailes.pack_end(run_id_label, False, True, 10)
        self.savedetailes.pack_end(self.test_report_int, False, True, 10)
        self.savedetailes.pack_end(test_report_label, False, True, 10)

        if not self.win.path_vrc and not self.win.path_cmd:
            self.savedetailes.pack_end(self.log_file_path_check, False, True, 10)
            self.savedetailes.pack_end(log_file_path_label, False, True, 10)

        if not self.win.path_json:
            self.savedetailes.pack_end(self.json_file_path_check, False, True, 10)
            self.savedetailes.pack_end(json_file_path_label, False, True, 10)

        if not self.win.path_json and not self.win.path_vrc and not self.win.path_cmd:
            self.savedetailes.pack_end(self.test_name, False, True, 10)
            self.savedetailes.pack_end(name_label, False, True, 10)

        area.pack_start(self.savedetailes, False, True, 0)

        self.show_all()
        return


class File_Path_Dialog(Gtk.FileChooserDialog):
    def __init__(self, parent=None, file=None, is_json=None):
        super(File_Path_Dialog, self).__init__(title='Please choose {}'.format(file),
                                                  parent=parent,
                                                  action=Gtk.FileChooserAction.OPEN)

        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        self.win = parent
        if not is_json:
            self.set_current_folder(cfg.get(section='tst-logging', option='test_run'))
        else:
            self.set_current_folder(cfg.get(section='tst-paths', option='tst_products'))

        if not is_json:
            area = self.get_content_area()
            #main_box = Gtk.HBox()
            label = Gtk.Label(label='It does not matter if Command or Verification Log File is choosen, both are in the same Folder')
            #main_box.pack_end(label, False, True, 10)
            area.pack_start(label, False, True, 0)
        self.show_all()


def run():
    bus_name = cfg.get('dbus_names', 'progress-view')
    dbus.validate_bus_name(bus_name)
    appli = Application(application_id=bus_name,
                        flags=Gio.ApplicationFlags.FLAGS_NONE)
    appli.run()


if __name__ == '__main__':
    run()
