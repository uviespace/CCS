#!/usr/bin/env python3
import os
import datetime
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib
from testlib import analyse_command_log
from testlib import analyse_verification_log
from testlib import testing_logger
import dbus
import time
import data_model
import json
import confignator
import toolbox


# create a logger
log_file_path = confignator.get_option(section='progress-viewer-logging', option='log-file-path')

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

        self.expander_states = []

        self.progress_tree_store = Gtk.TreeStore(str, str, str, str, str, str, str, str, str, str)

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
        self.box.pack_start(self.path_frame, True, True, 0)

        # buttons for the tree view (expand all, collapse all)
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
        self.box.pack_start(self.box_buttons, False, True, 0)

        self.btn_apply_css = Gtk.Button().new_from_icon_name('media-playlist-repeat-symbolic', Gtk.IconSize.BUTTON)
        self.btn_apply_css.set_tooltip_text('Apply CSS')
        self.btn_apply_css.connect('clicked', self.on_apply_css)
        # self.box_buttons.pack_start(self.btn_apply_css, False, False, 0)

        # --------------- tree view ---------------
        self.sorted_model = Gtk.TreeModelSort(model=self.progress_tree_store)
        self.sorted_model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        self.view = Gtk.TreeView(model=self.sorted_model)
        self.view.set_grid_lines(True)
        # self.view.set_enable_tree_lines(True)

        # column 1
        renderer_number = Gtk.CellRendererText()
        renderer_number.set_property('scale', 2)
        renderer_number.set_property('single-paragraph-mode', True)
        column_number = Gtk.TreeViewColumn('Step', renderer_number, text=8)
        self.view.append_column(column_number)

        # column 2
        renderer_exec_date = Gtk.CellRendererText()
        column_exec_date = Gtk.TreeViewColumn('Execution date', renderer_exec_date, text=1, background=7)
        self.view.append_column(column_exec_date)

        # column 3
        renderer_type = Gtk.CellRendererText()
        column_type = Gtk.TreeViewColumn('Type', renderer_type, text=2, background=7)
        self.view.append_column(column_type)

        # column 4
        renderer_cmd_version = Gtk.CellRendererText()
        column_cmd_version = Gtk.TreeViewColumn('Version', renderer_cmd_version, text=3, background=7)
        self.view.append_column(column_cmd_version)

        # column 5
        renderer_cmd_status = Gtk.CellRendererText()
        column_cmd_status = Gtk.TreeViewColumn('Status', renderer_cmd_status, text=4, background=7)
        self.view.append_column(column_cmd_status)

        # column 6
        renderer_tcs = Gtk.CellRendererText()
        column_tcs = Gtk.TreeViewColumn('TC\'s sent', renderer_tcs, text=5, background=7)
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
        # column_result.set_cell_data_func(cell_renderer=renderer_result, func=set_bkgrd_clr, func_data=None)
        self.view.append_column(column_result)

        self.view.expand_all()

        self.scroll_win = Gtk.ScrolledWindow()
        self.scroll_win.set_min_content_height(1200)
        self.scroll_win.set_min_content_width(900)
        self.scroll_win.add(self.view)
        self.box.pack_start(self.scroll_win, True, True, 0)

        self.connect('destroy', self.on_destroy)

        # expand all entries
        self.view.expand_all()

        # for styling the application with CSS
        context = self.get_style_context()
        Gtk.StyleContext.add_class(context, 'tst-css')
        self.on_apply_css()
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
        dialog = Gtk.FileChooserDialog('Please choose a Test Specification',
                                       self,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        self.add_filters(dialog)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            # ToDo: get the path for all 3 (json, cmd, vrc) and load them
        elif response == Gtk.ResponseType.CANCEL:
            pass
        dialog.destroy()

    def open_test_files(self, simple_action, paths, *args):
        logger.debug('Opening files... ')
        self.path_json = paths['json_file_path']
        self.text_path_json_btn.set_file(Gio.File.new_for_path(self.path_json))

        self.path_cmd = paths['cmd_log_file_path']
        self.text_path_cmd_btn.set_file(Gio.File.new_for_path(self.path_cmd))
        self.monitor_cmd = Gio.File.new_for_path(self.path_cmd).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor_cmd.set_rate_limit(100)
        self.monitor_cmd.connect('changed', self.file_cmd_changed)

        self.path_vrc = paths['vrc_log_file_path']
        self.text_path_vrc_btn.set_file(Gio.File.new_for_path(self.path_vrc))
        self.monitor_vrc = Gio.File.new_for_path(self.path_vrc).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor_vrc.set_rate_limit(100)
        self.monitor_vrc.connect('changed', self.file_vrc_changed)

        self.on_reload_all()
        self.on_expand_all_rows()

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

    def on_reload_all(self, *args):
        self.load_json(self.path_json)
        self.load_cmd(self.path_cmd)
        self.load_vrc(self.path_vrc)

    def on_clear_cmd_log(self, *args):
        with open(self.path_cmd, 'w') as cmd_log:
            cmd_log.write('')
            cmd_log.close()

    def on_clear_vrc_log(self, *args):
        with open(self.path_vrc, 'w') as vrc_log:
            vrc_log.write('')
            vrc_log.close()

    def on_destroy(self, *args):
        self.logger.info('Self-Destruct of the ProgressView Window initiated.\n')
        self.destroy()

    # ------------------- model functions ----------------------
    @staticmethod
    def build_row_list(row=None, step_number=None, exec_date=None, entry_type=None, version=None, status=None, tcs=None,
                       result=None, step_desc=None):
        """
        Builds or updates a row of the TreeStore. For a new row, the argument 'row' is expected to be None.
        :param Gtk.TreeModelRow row: a row of the tree model
        :param str step_number:
        :param datetime.datetime exec_date:
        :param str entry_type:
        :param str version:
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
            if step_number is not None:
                row[0] = step_number
            if exec_date is not None:
                row[1] = exec_date
            if entry_type is not None:
                row[2] = entry_type
            if version is not None:
                row[3] = version
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
            row = [
                step_number,
                exec_date,
                entry_type,
                version,
                status,
                tcs,
                result_value,
                entry_background,
                step_desc,
                result_cell_color

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
                self.test_model = data_model.TestSequence()
                self.test_model.decode_from_json(json_data=data_from_file)
                self.load_model_into_tree_store(self.progress_tree_store, self.test_model)
            else:
                logger.warning('load_file: could not read from the JSON test spec')

    def load_cmd(self, filepath):
        if not os.path.isfile(filepath):
            message = 'load_file: no file found for the path {}'.format(filepath)
            logger.warning(message)
            self.add_info_bar(message_type=Gtk.MessageType.WARNING, message=message)
        else:
            # analyse the command log
            self.cmd_steps = analyse_command_log.get_steps_and_commands(filepath)
            self.load_cmd_into_tree_store(self.progress_tree_store, self.cmd_steps)

    def load_vrc(self, filepath):
        if not os.path.isfile(filepath):
            message = 'load_file: no file found for the path {}'.format(filepath)
            logger.warning(message)
            self.add_info_bar(message_type=Gtk.MessageType.WARNING, message=message)
        else:
            # analyse the verification log
            self.vrc_steps = analyse_verification_log.get_verification_steps(filepath)
            self.load_vrc_into_tree_store(self.progress_tree_store, self.vrc_steps)

    def load_model_into_tree_store(self, tree_store, test_model):

        # collect the information if the drawer rows are expanded, in order to restore this states
        self.gather_expanded_states(tree_store)
        # check which step numbers are already in the tree_store
        tree_store_steps = []
        for row in tree_store:
            step_number_tree_store = int(row[0:1][0])
            tree_store_steps.append(step_number_tree_store)
        # add drawer for each step which is not in the tree_store already
        for key in test_model.steps_dict:
            step_number = int(test_model.steps_dict[key].step_number)
            if step_number not in tree_store_steps:
                step_desc = 'Step ' + str(step_number)
                new_drawer_row = self.build_row_list(step_number=str(step_number),
                                                     step_desc=step_desc)
                tree_store.append(None, new_drawer_row)
                tree_store_steps.append(step_number)
        # # remove all existing specifications
        # for row in tree_store:
        #   for item in row.iterchildren():
        #       if item[2] == 'specification':
        #           tree_store.remove(item.iter)
        # # add a row for (**each version of**) the step specification
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

        # check which step numbers are already in the tree_store
        tree_store_steps = []
        for row in tree_store:
            step_number_tree_store = int(row[0:1][0])
            tree_store_steps.append(step_number_tree_store)
        # add drawer for each step which is not in the tree_store already
        for item in cmd_steps:
            step_number = int(item['step'])
            if step_number not in tree_store_steps:
                step_desc = 'Step ' + str(step_number)
                new_drawer_row = self.build_row_list(step_number=str(step_number),
                                                     step_desc=step_desc)
                tree_store.append(None, new_drawer_row)
                tree_store_steps.append(step_number)
        # clear all command rows, before adding
        for row in tree_store:
            for item in row.iterchildren():
                if item[2] == 'command':
                    tree_store.remove(item.iter)
        # add rows for command
        for row in tree_store:
            step_number_tree_store = int(row[0:1][0])
            for item in cmd_steps:
                step_number_cmd = int(item['step'])
                if step_number_tree_store == step_number_cmd:
                    # already_exists = False
                    # for i in row.iterchildren():
                    #     if datetime.datetime.strftime(item['exec_date'], testing_logger.date_time_format) == i[1]:
                    #         already_exists = True
                    # # add a new row
                    # if not already_exists:
                    new_row_list = self.build_row_list(entry_type='command',
                                                       version=item['version'],
                                                       exec_date=item['exec_date'])
                    new_row_iter = tree_store.append(row.iter, new_row_list)
                    new_row = tree_store[new_row_iter]
                    # add the information if the step was executed or had an exception
                    if 'exception' in item:
                        self.build_row_list(row=new_row,
                                            status='EXCEPTION',
                                            result=False)
                    else:
                        if 'end_timestamp' in item:
                            self.build_row_list(row=new_row,
                                                status='executed',
                                                result=True)
                    # add the TC's
                    tcs_str = ''
                    for telecommand in item['tcs']:
                        if tcs_str != '':
                            tcs_str += ', '
                        tcs_str += telecommand.tc_kind()
                    self.build_row_list(row=new_row,
                                        tcs=tcs_str)
        self.restore_expanded_states(tree_store)

    def load_vrc_into_tree_store(self, tree_store, vrc_steps):

        # collect the information if the drawer rows are expanded, in order to restore this states
        self.gather_expanded_states(tree_store)
        # check which step numbers are already in the tree_store
        tree_store_steps = []
        for row in tree_store:
            step_number_tree_store = int(row[0:1][0])
            tree_store_steps.append(step_number_tree_store)
        # add drawer for each step which is not in the tree_store already
        for item in vrc_steps:
            step_number = int(item['step'])
            if step_number not in tree_store_steps:
                step_desc = 'Step ' + str(step_number)
                new_drawer_row = self.build_row_list(step_number=str(step_number),
                                                     step_desc=step_desc)
                tree_store.append(None, new_drawer_row)
                tree_store_steps.append(step_number)
        # clear all verification rows, before adding
        for row in tree_store:
            for item in row.iterchildren():
                if item[2] == 'verification':
                    tree_store.remove(item.iter)
        # add row for verification
        for row in tree_store:
            step_number_tree_store = int(row[0:1][0])
            for item in vrc_steps:
                step_number_vrc = int(item['step'])
                if step_number_tree_store == step_number_vrc:
                    # already_exists = False
                    # for i in row.iterchildren():
                    #     if datetime.datetime.strftime(item['exec_date'], testing_logger.date_time_format) == i[1]:
                    #         already_exists = True
                    # # add a new row
                    # if not already_exists:
                    new_row_list = self.build_row_list(entry_type='verification',
                                                       version=item['version'],
                                                       exec_date=item['exec_date'])
                    new_row_iter = tree_store.append(row.iter, new_row_list)
                    new_row = tree_store[new_row_iter]
                    # add the information if the step was executed or had an exception
                    if 'exception' in item:
                        self.build_row_list(row=new_row,
                                            status='EXCEPTION')
                    else:
                        if 'end_timestamp' in item:
                            self.build_row_list(row=new_row,
                                                status='executed')
                    if 'result' in item:
                        if item['result'] is True:
                            self.build_row_list(row=new_row,
                                                result=True)
                        else:
                            self.build_row_list(row=new_row,
                                                result=False)
        self.restore_expanded_states(tree_store)


def run():
    bus_name = confignator.get_option('dbus_names', 'progress-view')
    dbus.validate_bus_name(bus_name)
    appli = Application(application_id=bus_name,
                        flags=Gio.ApplicationFlags.FLAGS_NONE)
    appli.run()


if __name__ == '__main__':
    run()
