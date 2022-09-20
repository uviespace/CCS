#!/usr/bin/env python3
import json
import os
import logging
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, Gdk, Gio, GtkSource, GLib, GdkPixbuf
import confignator
cfg = confignator.get_config()

import sys
sys.path.append(cfg.get('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()
import view
import data_model
import file_management
# import tst_logger
import generator
import codeblockreuse
import connect_apps
import dbus
import toolbox
import tc_management as tcm
import tm_management as tmm
import data_pool_tab as dpt
import verification_tab as vt

import json_to_barescript
import json_to_csv

import spec_to_json


# creating lists for type and subtype to get rid of duplicate entries, for TC List


path_icon = os.path.join(os.path.dirname(__file__), 'style/tst.svg')
menu_xml = os.path.join(os.path.dirname(__file__), 'app_menu.xml')
css_file = os.path.join(os.path.dirname(__file__), 'style/style.css')
style_path = os.path.join(os.path.dirname(__file__), 'style')

logger = logging.getLogger('tst_app_main')
log_lvl = cfg.get(section='tst-logging', option='level')
logger.setLevel(level=log_lvl)
console_hdlr = toolbox.create_console_handler(hdlr_lvl=log_lvl)
console_hdlr.setLevel(level=logging.WARNING)
logger.addHandler(hdlr=console_hdlr)
log_file = cfg.get(section='tst-logging', option='log-file-path')
file_hdlr = toolbox.create_file_handler(file=log_file)
logger.addHandler(hdlr=file_hdlr)


VERSION = '0.10'


class TstApp(Gtk.Application):

    def __init__(self, application_id, flags, logger=logger):
        super().__init__(application_id=application_id, flags=flags)
        self.window = None
        self.application_id = application_id

        # set up logging
        # tst_logger.setup_logging(level=logging.DEBUG)
        self.logger = logger

        self.logger.info('Initiated a instance of the TstApp class')

    def do_startup(self):
        Gtk.Application.do_startup(self)

        action = Gio.SimpleAction.new('about_us', None)
        action.connect('activate', self._on_about)
        self.add_action(action)

        action = Gio.SimpleAction.new('quit', None)
        action.connect('activate', self._on_quit)
        self.add_action(action)

        self.create_modules_menu()

        # create the menu
        builder = Gtk.Builder.new_from_file(menu_xml)
        self.set_menubar(builder.get_object('app-menu'))

    def do_activate(self):
        # only allow a single window and raise any existing ones
        if not self.window:
            # Windows are associated with the application
            # when the last one is closed the application shuts down
            self.window = TstAppWindow(application=self, title='Test Specification Tool', logger=self.logger)

            # import DBus_Basic
            # import dbus
            # from dbus.mainloop.glib import DBusGMainLoop
            # dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            # DBus_Basic.MessageListener(self.window, self.application_id)

        self.window.present()

    def create_modules_menu(self):
        action = Gio.SimpleAction.new('start_ccs_editor', None)
        action.connect("activate", self._on_start_ccs_editor)
        self.add_action(action)

        action = Gio.SimpleAction.new('start_poolviewer', None)
        action.connect("activate", self._on_start_poolviewer)
        self.add_action(action)

        action = Gio.SimpleAction.new('start_poolmanager', None)
        action.connect("activate", self._on_start_poolmanager)
        self.add_action(action)

        action = Gio.SimpleAction.new('start_plotter', None)
        action.connect("activate", self._on_start_plotter)
        self.add_action(action)

        action = Gio.SimpleAction.new('start_monitor', None)
        action.connect("activate", self._on_start_monitor)
        self.add_action(action)

        action = Gio.SimpleAction.new('start_config_editor', None)
        action.connect("activate", self._on_start_config_editor)
        self.add_action(action)

        action = Gio.SimpleAction.new('start_log_viewer', None)
        action.connect("activate", self._on_start_log_viewer)
        self.add_action(action)

    def _on_about(self, action, param):
        about_dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        about_dialog.present()
        return

    def _on_quit(self, action, param):
        response = self.window.on_delete_event()
        if response:
            return
        self.quit()
        return

    def _on_start_ccs_editor(self, *args):
        try:
            cfl.start_editor()
        except Exception as e:
            self.logger.exception(e)
            message = 'Failed to start the CSS-Editor'
            self.add_info_bar(message_type=Gtk.MessageType.ERROR, message=message)
        return

    def _on_start_poolviewer(self, *args):
        cfl.start_pv()
        return

    def _on_start_poolmanager(self, *args):
        cfl.start_pmgr()
        return

    def _on_start_plotter(self, *args):
        cfl.start_plotter()
        return

    def _on_start_monitor(self, *args):
        cfl.start_monitor()
        return

    def _on_start_config_editor(self, *args):
        cfl.start_config_editor()
        return

    def _on_start_log_viewer(self, *args):
        cfl.start_log_viewer()
        return


class TestInstance:
    def __init__(self, app, logger=logger, *args, **kwargs):
        self.logger = logger
        self.model = data_model.TestSpecification(logger=logger)
        self._filename = None
        self.view = view.Board(self.model, app, filename=self.filename, logger=self.logger)

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value


class TstAppWindow(Gtk.ApplicationWindow):

    def __init__(self, logger=logger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger
        self.logger.info('Initializing an instance of the class TstAppWindow')
        self.product_paths = []

        # actions
        action = Gio.SimpleAction.new('make_new_test', None)
        action.connect('activate', self.on_new_test)
        self.add_action(action)

        action = Gio.SimpleAction.new('open', None)
        action.connect('activate', self.on_open)
        self.add_action(action)

        action = Gio.SimpleAction.new('save', None)
        action.connect('activate', self.on_save)
        self.add_action(action)

        action = Gio.SimpleAction.new('save_as', None)
        action.connect('activate', self.on_save_as)
        self.add_action(action)

        action = Gio.SimpleAction.new('csv_to_json', None)
        action.connect('activate', self.on_csv_to_json)
        self.add_action(action)

        action = Gio.SimpleAction.new('close', None)
        action.connect('activate', self.on_close)
        self.add_action(action)

        show_json_view = cfg.getboolean('tst-preferences', 'show-json-view')
        action = Gio.SimpleAction.new_stateful('model_viewer_toggle_hide', None,
                                               GLib.Variant.new_boolean(show_json_view))
        action.connect('change-state', self.model_viewer_toggle_hide)
        self.add_action(action)

        action = Gio.SimpleAction.new('apply_css', None)
        action.connect('activate', self.on_apply_css)
        self.add_action(action)

        action = Gio.SimpleAction.new('about_us', None)
        action.connect('activate', self.on_about)
        self.add_action(action)

        self.create_make_menu()

        self.set_icon_from_file(path_icon)
        self.set_keybinds()

        # GUI
        self.box = Gtk.Box()
        self.box.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar & place for info bar (see function add_info_bar)
        self.btn_new_file = Gtk.ToolButton()
        self.btn_new_file.set_icon_name('document-new')
        self.btn_new_file.set_tooltip_text('New test specification')
        self.btn_new_file.connect('clicked', self.on_new_test)
        self.btn_open_file = Gtk.ToolButton()
        self.btn_open_file.set_icon_name('document-open')
        self.btn_open_file.set_tooltip_text('Open file')
        self.btn_open_file.connect('clicked', self.on_open)
        # self.btn_apply_css = Gtk.ToolButton()
        # self.btn_apply_css.set_icon_name('media-playlist-repeat-symbolic')
        # self.btn_apply_css.set_tooltip_text('Apply CSS')
        # self.btn_apply_css.connect('clicked', self.apply_css)
        self.btn_save = Gtk.ToolButton()
        self.btn_save.set_icon_name('document-save')
        self.btn_save.set_tooltip_text('Save')
        self.btn_save.connect('clicked', self.on_save)
        # self.btn_show_model_viewer = Gtk.ToolButton()
        # self.btn_show_model_viewer.set_icon_name('accessories-dictionary-symbolic')
        # self.btn_show_model_viewer.set_tooltip_text('Show/hide model viewer')
        # self.btn_show_model_viewer.connect('clicked', self.model_viewer_toggle_hide)
        self.btn_generate_products = Gtk.ToolButton()
        self.btn_generate_products.set_label('Generate scripts')
        self.btn_generate_products.set_icon_name('text-x-python')
        self.btn_generate_products.set_tooltip_text('Generate command.py, verification.py and manually.py')
        self.btn_generate_products.connect('clicked', self.on_generate_products)

        self.btn_start_ccs_editor = Gtk.ToolButton()
        self.btn_start_ccs_editor.set_label('Start CCS')
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            cfg.get('paths', 'ccs') + '/pixmap/ccs_logo_2.svg', 28, 28)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        self.btn_start_ccs_editor.set_icon_widget(icon)
        self.btn_start_ccs_editor.set_tooltip_text('Start CCS-Editor')
        self.btn_start_ccs_editor.connect('clicked', self.on_start_ccs_editor)

        self.btn_open_progress_view = Gtk.ToolButton()
        self.btn_open_progress_view.set_label('Start ProgressView')
        self.btn_open_progress_view.set_icon_name('utilities-system-monitor')
        self.btn_open_progress_view.set_tooltip_text('Start ProgressView')
        self.btn_open_progress_view.connect('clicked', self.on_start_progress_viewer)

        self.toolbar = Gtk.Toolbar()
        self.toolbar.insert(self.btn_new_file, 0)
        self.toolbar.insert(self.btn_open_file, 1)
        self.toolbar.insert(self.btn_save, 2)
        # self.toolbar.insert(self.btn_show_model_viewer, 2)
        self.toolbar.insert(self.btn_generate_products, 3)
        self.toolbar.insert(self.btn_start_ccs_editor, 4)
        self.toolbar.insert(self.btn_open_progress_view, 5)
        
        # IDB chooser
        self.idb_chooser = Gtk.ToolButton()

        label = Gtk.Label()
        label.set_markup('<b>IDB:</b> {}'.format(cfl.scoped_session_idb.bind.url.database))
        self.idb_chooser.set_label_widget(label)
        self.idb_chooser.set_tooltip_text('Select IDB')
        self.idb_chooser.connect('clicked', self.on_set_idb_version)
        self.toolbar.insert(self.idb_chooser, 6)

        # separator
        sepa = Gtk.SeparatorToolItem()
        sepa.set_expand(True)
        self.toolbar.insert(sepa, 7)

        # logo
        self.unilogo = Gtk.ToolButton()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            cfg.get('paths', 'ccs') + '/pixmap/Icon_Space_blau_en.png', 32, 32)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        self.unilogo.set_icon_widget(icon)
        self.unilogo.connect('clicked', self.on_about)
        self.toolbar.insert(self.unilogo, 8)
        self.box.pack_start(self.toolbar, False, True, 0)
        
        self.info_bar = None

        # packing the widgets
        self.work_desk = Gtk.Paned()
        self.work_desk.set_wide_handle(True)

        # add the notebook for the test specifications
        self.notebook = Gtk.Notebook()
        self.notebook.connect('switch-page', self.update_model_viewer)
        self.work_desk.pack1(self.notebook)

        self.feature_area = Gtk.Notebook()
        self.work_desk.pack2(self.feature_area)

        self.codeblockreuse = codeblockreuse.CBRSearch(app_win=self, logger=self.logger)
        self.label_widget_codeblockreuse = Gtk.Label()
        self.label_widget_codeblockreuse.set_text('Code Snippets')
        self.feature_area.append_page(child=self.codeblockreuse, tab_label=self.label_widget_codeblockreuse)

        import log_viewer
        self.log_view = log_viewer.LogView(filename=log_file, app_win=self)
        self.label_widget_log_view = Gtk.Label()
        self.label_widget_log_view.set_text('Log View')
        self.feature_area.append_page(child=self.log_view, tab_label=self.label_widget_log_view)

        self.json_view = ViewModelAsJson()
        self.update_model_viewer()
        self.label_widget_json_view = Gtk.Label()
        self.label_widget_json_view.set_text('JSON View')
        self.feature_area.append_page(child=self.json_view, tab_label=self.label_widget_json_view)

        # command list tab

        self.tcm = tcm.TcTable()
        self.label_widget_tcm = Gtk.Label()
        self.label_widget_tcm.set_text('TC Table')
        self.feature_area.insert_page(child=self.tcm, tab_label=self.label_widget_tcm, position=1)

        # telemetry list tab
        self.telemetry = tmm.TmTable()
        self.label_widget_telemetry = Gtk.Label()
        self.label_widget_telemetry.set_text('TM Table')
        self.feature_area.insert_page(child=self.telemetry, tab_label=self.label_widget_telemetry, position=2)

        # data pool list tab
        self.data_pool_tab = dpt.DataPoolTable()
        self.label_widget_data_pool = Gtk.Label()
        self.label_widget_data_pool.set_text('Data Pool')
        self.feature_area.insert_page(child=self.data_pool_tab, tab_label=self.label_widget_data_pool, position=3)

        # verification tab
        self.verification_tab = vt.VerificationTable()
        self.label_widget_verification = Gtk.Label()
        self.label_widget_verification.set_text("Verification")
        self.feature_area.insert_page(child=self.verification_tab, tab_label=self.label_widget_verification, position=4)

        self.box.pack_start(self.work_desk, True, True, 0)

        # # panes for the step grid an so on
        # self.paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        #
        # # paned: left pane: CodeBlockReuse
        #
        # self.codeblockreuse = search.Search(None, self)
        # self.paned.pack1(child=self.codeblockreuse, resize=True, shrink=True)
        #
        # # paned: right pane: TestSpecificationEditor
        # self.notebook = Gtk.Notebook()
        # self.paned.pack2(child=self.notebook, resize=True, shrink=False)
        #
        # # add the view to display the data model as JSON
        # self.json_view = ViewModelAsJson()
        # self.update_model_viewer()
        # # self.paned.pack2(child=self.json_view, resize=True, shrink=True)
        #
        # self.box.pack_start(self.paned, True, True, 0)

        self.add(self.box)

        self.connect('delete-event', self.on_delete_event)

        # self.dev_open_example_json_file()

        # set the size (width and height) of the main window using the values of the configuration file
        height_from_config = cfg.get('tst-preferences', 'main-window-height')
        width_from_config = cfg.get('tst-preferences', 'main-window-width')
        if height_from_config is not None and width_from_config is not None:
            self.resize(int(width_from_config), int(height_from_config))
        else:
            self.maximize()
        # set the position of the Paned widget using the configuration file
        paned_position = cfg.get('tst-preferences', 'paned-position')
        if paned_position is None:
            paned_position = self.get_size().width * 3 / 5
        self.work_desk.set_position(int(paned_position))
        # # set the position of the paned of the widget self.codeblockreuse
        # paned_position_cbr = cfg.get('tst-preferences', 'paned-position-codeblockreuse')
        # self.codeblockreuse.set_paned_position(int(paned_position_cbr))

        self.show_all()

        # for styling the application with CSS
        context = self.get_style_context()
        Gtk.StyleContext.add_class(context, 'tst-css')
        self.on_apply_css()

    def create_make_menu(self):
        action = Gio.SimpleAction.new('generate_scripts', None)
        action.connect('activate', self.on_generate_products)
        self.add_action(action)

        action = Gio.SimpleAction.new('generate_barescript', None)
        action.connect('activate', self.on_generate_barescript)
        self.add_action(action)

        action = Gio.SimpleAction.new('generate_csv', None)
        action.connect('activate', self.on_generate_csv)
        self.add_action(action)

    def set_keybinds(self):
        accel = Gtk.AccelGroup()
        accel.connect(Gdk.keyval_from_name('c'), Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0, self.copy_pid_name)
        self.add_accel_group(accel)

    def copy_pid_name(self, *args):
        self.data_pool_tab.copy_cell_content(1)

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

    def new_test(self):
        new_test = TestInstance(self, logger=self.logger)
        return new_test

    def new_page(self, test_instance):
        if test_instance.filename is not None:
            label_text = os.path.basename(test_instance.filename)
            test_instance.view.filename = test_instance.filename
        else:
            label_text = 'New test'
        label = self.notebook_page_label(label_text=label_text)
        page_index = self.notebook.append_page(child=test_instance.view, tab_label=label)
        # reload the data of the widgets, in order to display it
        test_instance.view.update_widget_data()
        self.show_all()
        return page_index

    def notebook_page_label(self, label_text):
        box = Gtk.Box()
        box.set_orientation(Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label()
        label.set_text(label_text)
        btn_close = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.BUTTON)
        btn_close.set_tooltip_text('Close')
        btn_close.connect('clicked', self.on_close_clicked)
        box.pack_start(label, True, True, 0)
        box.pack_start(btn_close, True, True, 0)
        box.show_all()
        return box

    def current_test_instance(self):
        test_instance = None
        current_page = self.notebook.get_current_page()
        if not current_page == -1:
            test_instance = self.notebook.get_nth_page(current_page)
        return test_instance

    def current_model(self):
        # get the  data model of the current notebook page
        current_model = None
        current_test = self.current_test_instance()
        if current_test is not None:
            current_model = current_test.model
            if not isinstance(current_model, data_model.TestSpecification):
                raise Exception
        return current_model

    def update_model_viewer(self, *args):
        """
        Gets the data of the model and makes a JSON string out of it. Intended to display the model data as plain JSON
        """
        if len(args) == 3:
            nb, _, n = args
            tab = nb.get_nth_page(n)
            self.json_view.update(tab.model)
            return

        current_model = self.current_model()
        self.json_view.update(current_model)

    def model_viewer_toggle_hide(self, action, value):
        visible = self.json_view.is_visible()
        action.set_state(GLib.Variant.new_boolean(not visible))
        if visible:
            self.json_view.hide()
        else:
            self.json_view.show()

    def on_new_test(self, *args):
        # create a new test instance and add a sequence + first step
        test = self.new_test()
        new_seq = test.model.add_sequence()
        new_step = test.model.get_sequence(new_seq).add_step_below()
        # adding a page to the notebook
        self.new_page(test)
        # show the details of the new step
        new_step_widget = test.view.get_step_widget(seq_num=new_seq, step_number=new_step.step_number)
        new_step_widget.on_toggle_detail(None)
        # update the model viewer
        self.update_model_viewer()

    def on_close(self, *args):
        """ Closing the current active page """
        current_page = self.notebook.get_current_page()
        if not current_page == -1:
            # check if it should be saved
            # ToDo
            # remove the page from the notebook
            self.notebook.remove_page(current_page)
        self.update_model_viewer()

    def on_close_clicked(self, widget):
        """
        Closing the page on which was clicked
        """
        for i in range(0, self.notebook.get_n_pages()):  # Loop over all availabe page numbers
            page = self.notebook.get_nth_page(i)  # Get page widget
            if self.notebook.get_tab_label(
                    page) == widget.get_parent():  # Check if the label widget is the same as for the given widget
                self.notebook.remove_page(i)  # If so close the page
                return

        # self.notebook.remove_page(widget.get_parent())

    def on_open(self, *args):
        dialog = Gtk.FileChooserDialog('Please choose a file',
                                       self,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        # using the last folder from history
        last_folder = cfg.get('tst-history', 'last-folder')
        if os.path.isdir(last_folder):
            dialog.set_current_folder(last_folder)
        self.add_filters(dialog)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            cfg.save_option_to_file('tst-history', 'last-folder', os.path.dirname(file_selected))
            try:
                json_type = True
                data_from_file = file_management.open_file(file_name=file_selected)
                filename = file_selected
            except json.decoder.JSONDecodeError:
                # data_from_file = file_management.from_json(spec_to_json.run(specfile=file_selected, gen_cmd=True, save_json=False))
                data_from_file = spec_to_json.run(specfile=file_selected, gen_cmd=True, save_json=False)
                filename = file_selected.replace('.' + file_selected.split('.')[-1], '.json')
                json_type = False
                if os.path.exists(filename):
                    self.existing_json_warn_dialog(filename)

            if data_from_file is not None:
                self.on_open_create_tab(data_from_file, filename, json_type)

        dialog.destroy()
        return

    def on_open_create_tab(self, data_from_file, filename, json_type):
        # make a new test instance and notebook page
        self.logger.info('make a new test instance and notebook page for: {}'.format(filename))
        new_test = self.new_test()
        new_test.model.decode_from_json(json_data=data_from_file)
        new_test.filename = filename
        if not json:
            new_test.ask_overwrite = True
        else:
            new_test.ask_overwrite = True
        new_page_index = self.new_page(test_instance=new_test)
        self.update_model_viewer()
        new_test.view.update_widget_data()
        self.notebook.set_current_page(new_page_index)
        return

    def on_save(self, *args):
        # get the  data model of the current notebook page
        current_test = self.current_test_instance()
        current_model = self.current_model()
        # current_model2=current_model.serialize(current_model)
        if current_model is not None and current_test.filename is None:
            self.save_as_file_dialog()
        elif current_test and current_test.ask_overwrite and current_test.filename:
            if os.path.exists(current_test.filename):
                self.overwrite_dialog(current_test)
            else:
                self.save_as_file_dialog()
        elif current_model is not None:
            file_management.save_file(file_path=current_test.filename, test_spec=current_model, logger=self.logger)

    def on_save_as(self, *args):
        self.save_as_file_dialog()

    def save_as_file_dialog(self):
        current_test = self.current_test_instance()
        current_name = self.current_model().name
        current_model = self.current_model()
        dialog = Gtk.FileChooserDialog('Please choose a file',
                                       self,
                                       Gtk.FileChooserAction.SAVE,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        dialog.set_current_folder(cfg.get(section='tst-history', option='last-folder'))
        dialog.set_current_name('{}-TS-{}.json'.format(current_name, current_model.spec_version))
        self.add_filters(dialog)
        dialog.set_do_overwrite_confirmation(True)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            cfg.save_option_to_file('tst-history', 'last-folder', os.path.dirname(file_selected))
            file_management.save_file(file_path=file_selected, test_spec=current_model, file_extension='json',
                                      logger=self.logger)
            current_test.filename = file_selected
            file_name = file_selected.split('/')[-1]
            # current_model.name = file_selected.split('/')[-1].split('.')[0].split('-TS-')[0]  # Get only the name
            current_test.update_widget_data()
            self.notebook.set_tab_label(current_test, self.notebook_page_label(file_name))  # Update tab label
            self.show_all()
            dialog.destroy()
            return True
        else:
            dialog.destroy()
            return False

    def add_filters(self, dialog, filter_json=True):
        if filter_json:
            filter_text = Gtk.FileFilter()
            filter_text.set_name('JSON format')
            filter_text.add_mime_type('application/json')
            filter_text.add_pattern('.json')
            dialog.add_filter(filter_text)
        else:
            filter_text = Gtk.FileFilter()
            filter_text.set_name('Spec Files')
            filter_text.add_mime_type('text/csv')
            filter_text.add_pattern('.csv*')
            dialog.add_filter(filter_text)

        filter_any = Gtk.FileFilter()
        filter_any.set_name('Any files')
        filter_any.add_pattern('*')
        dialog.add_filter(filter_any)

    def on_csv_to_json(self, *args):
        dialog = Gtk.FileChooserDialog('Please choose a CSV File',
                                       self,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        # using the last folder from history
        last_folder = cfg.get('tst-history', 'last-folder')
        if os.path.isdir(last_folder):
            dialog.set_current_folder(last_folder)
        # self.add_filters(dialog, filter_json=False)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            cfg.save_option_to_file('tst-history', 'last-folder', dialog.get_current_folder())
            file_selected = dialog.get_filename()
            filename = file_selected.replace('.' + file_selected.split('.')[-1], '.json')
            data_from_file = spec_to_json.run(specfile=file_selected, gen_cmd=True, save_json=False)
            self.on_open_create_tab(data_from_file, filename, json_type=False)
            # self.on_open_create_tab(data_from_file, filename, json_type=False)
            dialog.destroy()

            self.save_as_file_dialog()
        else:
            dialog.destroy()

        return

    def overwrite_dialog(self, current_test):
        filepath = current_test.filename
        filename = filepath.split('/')[-1]
        folder = filepath[:-len(filename)-1]
        dialog = Gtk.MessageDialog()
        dialog.add_buttons(Gtk.STOCK_YES, Gtk.ResponseType.YES, Gtk.STOCK_NO, Gtk.ResponseType.NO)
        dialog.set_title('Overwrite existing file')
        dialog.format_secondary_text('{} at {} already exists. Overwrite?'.format(filename, folder))
        response = dialog.run()

        if response == Gtk.ResponseType.YES:
            current_test.ask_overwrite = False
            dialog.destroy()
            self.on_save()
        else:
            dialog.destroy()

        return

    def existing_file_dialog(self, filepath):
        dialog = Gtk.MessageDialog()
        dialog.add_buttons(Gtk.STOCK_YES, Gtk.ResponseType.YES, Gtk.STOCK_NO, Gtk.ResponseType.NO)
        dialog.set_title('Overwrite existing file')
        # dialog.set_markup('Overwrite existing file?')
        dialog.format_secondary_text('{} already exists. Overwrite?'.format(filepath))
        response = dialog.run()
        if response == Gtk.ResponseType.YES:
            dialog.destroy()
            return True
        else:
            dialog.destroy()
            return False

    def existing_json_warn_dialog(self, filepath):
        filename = filepath.split('/')[-1]
        folder = filepath[:-len(filename)-1]
        dialog = Gtk.MessageDialog()
        dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_markup('CSV converted JSON file already exists'.format(filename))
        dialog.format_secondary_text('{} at {} already exists, temporarily saved in TST \nBe careful during saving'.format(filename, folder))
        dialog.run()
        dialog.destroy()
        return True

    def unsaved_changes_overwrite_dialog(self, current_test):
        filepath = current_test.filename
        filename = filepath.split('/')[-1]
        folder = filepath[:-len(filename)-1]
        dialog = Gtk.MessageDialog()
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_YES, Gtk.ResponseType.YES, Gtk.STOCK_NO, Gtk.ResponseType.NO)
        dialog.set_title('Unsaved Buffer')
        dialog.set_markup('Unsaved changes in {}, Overwrite?'.format(filename))
        dialog.format_secondary_text('{} at {} already exists'.format(filename, folder))
        response = dialog.run()
        if response == Gtk.ResponseType.YES:
            current_test.ask_overwrite = False
            dialog.destroy()
            self.on_save()
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()
            return False
        else:
            dialog.destroy()

        return True

    def unsaved_changes_newfile_dialog(self, current_test):
        filepath = current_test.filename
        if filepath:
            filename = filepath.split('/')[-1]
        else:
            filename = 'New Test'
        dialog = Gtk.MessageDialog()
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_YES, Gtk.ResponseType.YES, Gtk.STOCK_NO, Gtk.ResponseType.NO)
        dialog.set_title('Unsaved buffer')
        dialog.set_markup('Unsaved file {}, save?'.format(filename))
        # dialog.format_secondary_text('{} at {} is unsaved'.format(filename, folder))
        response = dialog.run()

        if response == Gtk.ResponseType.YES:
            current_test.ask_overwrite = False
            dialog.destroy()
            response = self.save_as_file_dialog()
            if response:
                return True
            else:
                return False
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()
            return False
        else:
            dialog.destroy()

        return True

    def on_delete_event(self, *args):
        self.logger.info('save preferences')
        # saving the height and width of the main window
        cfg.save_option_to_file('tst-preferences', 'main-window-height', str(self.get_size().height))
        cfg.save_option_to_file('tst-preferences', 'main-window-width', str(self.get_size().width))
        # save the position of the paned widget
        cfg.save_option_to_file('tst-preferences', 'paned-position', str(self.work_desk.get_position()))
        # save the preferences of the CodeReuseFeature
        self.codeblockreuse.save_panes_positions()
        self.logger.info('Check for Unsaved Buffer')
        response = self._check_unsaved_buffer()
        if not response:
            return True
        return False

    def _check_unsaved_buffer(self):
        for test_instance in self.notebook:
            filename = test_instance.filename
            tst_json = json.loads(test_instance.model.encode_to_json())
            if filename and os.path.exists(filename):
                file_json = file_management.open_file(filename)
                if not tst_json == file_json:
                    response = self.unsaved_changes_overwrite_dialog(test_instance)
                    if not response:
                        return False
            else:
                response = self.unsaved_changes_newfile_dialog(test_instance)
                if not response:
                    return False

        return True

    def on_generate_products(self, *args):
        """
        This function generates out of the current test script model the command script, the verification script and
        the documentation file. If it succeeded, a dialog box will be triggered.
        """
        # ToDo: remove the reloading, when developing is finished
        # import importlib
        # importlib.reload(generator)
        model = self.current_model()
        if not model:
            logger.info('Test Files can not be generated without Steps')
            logger.error('Please add at least one test step')
            return
        elif not model.name:
            logger.info('Test Files can not be generated if Test has no name!')
            logger.error('Please give the test a name')
            return
        self.product_paths = generator.make_all(model=model)
        # triggering the dialog after generation
        self.on_generate_products_message_dialog(paths=self.product_paths)

    def on_generate_barescript(self, *args):
        """
        Generates a compact python test file without all the additional stuff from on_generate_scripts
        """
        dialog = Gtk.FileChooserDialog(
            title="Save script as", parent=self, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,
            Gtk.ResponseType.OK, )

        if self.current_test_instance():
            # current_json_filename = self.current_test_instance().filename
            current_model = self.current_model()
        else:
            logger.error('Small Script can not be generated without JSON file')
            return

        outfile_basic = '{}-TS-{}.py'.format(current_model.name, current_model.spec_version)
        dialog.set_current_name(outfile_basic)
        dialog.set_current_folder(cfg.get('tst-history', 'last-folder'))

        response = dialog.run()
        while response == Gtk.ResponseType.OK:
            if os.path.exists(dialog.get_filename()):
                if not self.existing_file_dialog(dialog.get_filename()):
                    response = dialog.run()
                    continue
            json_to_barescript.run(current_model.encode_to_json(), dialog.get_filename())
            cfg.save_option_to_file('tst-history', 'last-folder', dialog.get_current_folder())
            break

        dialog.destroy()
        return

    def on_generate_csv(self, *args):
        """
        Generates a CSV Test Specification file
        """
        dialog = Gtk.FileChooserDialog(
            title="Save CSV as", parent=self, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE,
            Gtk.ResponseType.OK, )

        if self.current_test_instance():
            # current_json_filename = self.current_test_instance().filename
            current_model = self.current_model()
        else:
            logger.info('CSV File can not be generated without JSON file')
            return

        outfile_basic = '{}-TS-{}.csv_PIPE'.format(current_model.name, current_model.spec_version)
        dialog.set_current_name(outfile_basic)
        dialog.set_current_folder(cfg.get('tst-history', 'last-folder'))

        response = dialog.run()
        while response == Gtk.ResponseType.OK:
            if os.path.exists(dialog.get_filename()):
                if not self.existing_file_dialog(dialog.get_filename()):
                    response = dialog.run()
                    continue
            json_to_csv.run(current_model.encode_to_json(), dialog.get_filename())
            cfg.save_option_to_file('tst-history', 'last-folder', dialog.get_current_folder())
            break

        dialog.destroy()
        return

    def connect_to_ccs_editor(self):
        # get the DBus connection to the CCS-Editor
        editor = connect_apps.connect_to_editor()
        if editor is None:
            self.logger.warning('Failed to connect to the CCS-Editor via DBus')
            self.on_start_ccs_editor(False)

        editor = connect_apps.connect_to_app('editor')
        '''     
        k = 0
        while k < 3:
            # try again to connect to the CCS-Editor
            self.logger.info('Trying to connect to the CCS-Editor via DBus.')
            time.sleep(1)
            editor = connect_apps.connect_to_editor()
            if editor is not None:
                self.logger.info('Successfully connected to the CCS-Editor via DBus.')
                break
            k += 1'''
        return editor

    def connect_progress_viewer(self):
        # get the DBus connection to the CCS-Editor
        try:
            connect_apps.connect_to_progress_viewer(logger=self.logger)
        except dbus.exceptions.DBusException:
            self.logger.warning('could not connect to ProgressViewer, starting it')
            cfl.start_progress_view()
        k = 0
        while k < 10:
            # try again to connect to the CCS-Editor
            self.logger.info('trying to connect to the ProgressViewer via DBus.')
            time.sleep(0.2)
            try:
                prog = connect_apps.connect_to_progress_viewer(logger=self.logger)
                if prog is not None:
                    self.logger.info('Successfully connected to the ProgressViewer via DBus.')
                    return prog
            except dbus.exceptions.DBusException:
                self.logger.warning('could not connect to ProgressViewer')
            k += 1

    def ccs_editor_open_files(self, editor, file_list):
        if editor is not None:
            # open the files in the CCS-Editor
            for pth in file_list:
                pth = os.path.abspath(pth)
                try:
                    self.logger.info('Opening file {} in the CCS-Editor'.format(pth))
                    editor.Functions('open_file', pth)
                except dbus.exceptions.DBusException as e:
                    message = 'Could not find the file: {}'.format(pth)
                    self.logger.error(message)
                    self.logger.exception(e)
                    self.add_info_bar(message_type=Gtk.MessageType.ERROR, message=message)

    def on_generate_products_message_dialog(self, paths):
        """
        After the successful generation of the products, a dialog is shown and asks if the files should be opened in the
        CCS-editor.
        :param list paths: List of the paths of the product files
        """
        dialog = Gtk.MessageDialog(self,
                                   0,
                                   Gtk.MessageType.QUESTION,
                                   Gtk.ButtonsType.YES_NO,
                                   'Scripts were generated')
        message = 'Generated files:\n'
        for entry in paths:
            message += os.path.basename(entry) + '\n'
        paths.append(os.path.join(os.path.realpath(os.path.join(os.path.dirname(__file__), '..')), 'prep_test_env.py'))
        message += 'Do you want to open them in CCS?'
        dialog.format_secondary_text(message)
        response = dialog.run()
        if response == Gtk.ResponseType.YES:
            # get a Dbus connection to the CCS-Editor
            editor = self.connect_to_ccs_editor()
            # open files in the CCS-Editor
            if editor is not None:
                self.ccs_editor_open_files(editor, paths)
        elif response == Gtk.ResponseType.NO:
            pass
        dialog.destroy()

    def get_log_file_paths_from_json_file_name(self):
        from testlib import testing_logger
        paths = {}
        current_instance = self.current_test_instance()
        if not current_instance:
            self.logger.warning('Progress Viewer started without running Test')
            return ''
        try:
            current_file_name = os.path.basename(current_instance.filename)
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
            self.logger.warning('Json or Log Files could not be found')
            return ''
        return paths

    def on_make_desktop_entry(self):
        # ToDo: create a file for the desktop entry
        pass

    def on_start_progress_viewer(self, *args):

        self.logger.info('Starting ProgressViewer')

        progress_viewer = self.connect_progress_viewer()
        file_names = self.get_log_file_paths_from_json_file_name()
        try:
            progress_viewer.Activate('open-test-files', [file_names], [])
        except Exception as e:
            message = 'Could not start ProgressViewer application.'
            self.logger.error(message)
            self.logger.exception(e)
            # add a info bar message that the starting of the CCS-Editor failed.
            self.add_info_bar(message_type=Gtk.MessageType.ERROR, message=message)

    def on_start_ccs_editor(self, *args):
        try:
            self.logger.info('Starting CCS-Editor application.')
            cfl.start_editor()
        except Exception as e:
            message = 'Could not start CCS-Editor.'
            self.logger.error(message)
            self.logger.exception(e)
            # add a info bar message that the starting of the CCS-Editor failed.
            self.add_info_bar(message_type=Gtk.MessageType.ERROR, message=message)

    def on_apply_css(self, *args):
        style_provider = Gtk.CssProvider()
        css = open(css_file, 'rb')  # rb needed for python 3 support
        css_data = css.read()
        css.close()
        style_provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                                 style_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.StyleContext.reset_widgets(Gdk.Screen.get_default())

    def on_about(self, *args):
        about_dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        about_dialog.set_authors(['Stefan Winkler', 'Dominik Möslinger', 'Sebastian Miksch', 'Marko Mecina'])
        about_dialog.set_website('https://space.univie.ac.at/en')
        about_dialog.set_website_label('space.univie.ac.at')
        about_dialog.set_version(VERSION)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(style_path + '/tst.png')
        about_dialog.set_logo(pixbuf)
        about_dialog.set_program_name('Test Specification Tool')
        about_dialog.set_copyright('UVIE 08/2022')
        about_dialog.set_license_type(Gtk.License.MPL_2_0)
        about_dialog.present()
        return

    def on_set_idb_version(self, widget):
        self.reconnect_mib()
        # get current MIB name
        mibname = widget.get_label_widget().get_text().replace('IDB: ', '')
        dialog = IDBChooser(mibname)
        dialog.set_transient_for(self)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            model, it = dialog.selection.get_selected()
            idb = model[it][0]
            cfl.set_scoped_session_idb_version(idb_version=idb)
            label = self.idb_chooser.get_label_widget()
            label.set_markup('<b>IDB:</b> {}'.format(cfl.scoped_session_idb.bind.url.database))
            self.feature_area.freeze_child_notify()
            page = self.feature_area.get_current_page()
            self.reload_tc_table()
            self.reload_tm_table()
            self.reload_dp_table()
            self.feature_area.set_current_page(page)
            self.feature_area.thaw_child_notify()
            dialog.destroy()
        else:
            dialog.destroy()

    def reload_tc_table(self):
        self.feature_area.remove_page(self.feature_area.page_num(self.tcm))
        tcm.reload_tc_data()
        self.tcm = tcm.TcTable()
        self.feature_area.insert_page(self.tcm, self.label_widget_tcm, 1)

    def reload_tm_table(self):
        self.feature_area.remove_page(self.feature_area.page_num(self.telemetry))
        tmm.reload_tm_data()
        self.telemetry = tmm.TmTable()
        self.feature_area.insert_page(self.telemetry, self.label_widget_telemetry, 2)

    def reload_dp_table(self):
        self.feature_area.remove_page(self.feature_area.page_num(self.data_pool_tab))
        dpt.reload_dp_data()
        self.data_pool_tab = dpt.DataPoolTable()
        self.feature_area.insert_page(self.data_pool_tab, self.label_widget_data_pool, 3)

    @staticmethod
    def reconnect_mib():
        cfl.scoped_session_idb.close()


class IDBChooser(Gtk.Dialog):
    def __init__(self, cur_mibname):
        super(IDBChooser, self).__init__(title='Select MIB')
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.set_size_request(300, 200)

        idb_selection = Gtk.ListStore(str)
        mibs = cfl.scoped_session_idb.execute('show databases').fetchall()

        for m, in mibs:
            if m.count('mib'):
                idb_selection.append([m])

        tv = Gtk.TreeView(model=idb_selection)
        self.selection = tv.get_selection()
        self.selection.set_mode(Gtk.SelectionMode.SINGLE)

        for i, row in enumerate(idb_selection):
            if row[0] == cur_mibname:
                self.selection.select_path(idb_selection.get_path(idb_selection.get_iter(i)))

        col = Gtk.TreeViewColumn('SCHEMA NAME', Gtk.CellRendererText(), text=0)
        tv.append_column(col)

        scr = Gtk.ScrolledWindow()
        scr.add(tv)

        box = self.get_content_area()
        box.pack_start(scr, True, True, 0)

        self.show_all()


class ViewModelAsJson(Gtk.Box):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_orientation(Gtk.Orientation.VERTICAL)

        # options area
        self.box_h = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.style_manager = GtkSource.StyleSchemeManager.get_default()
        self.style_manager.append_search_path(style_path)
        self.chooser_button = GtkSource.StyleSchemeChooserButton()
        self.chooser_button.set_style_scheme(self.style_manager.get_scheme('darcula'))
        self.chooser_button.connect('notify', self._update_style)
        img = Gtk.Image.new_from_icon_name('applications-system-symbolic', Gtk.IconSize.BUTTON)
        self.chooser_button.set_image(img)
        self.chooser_button.set_label('')
        self.current_scheme = self.chooser_button.get_style_scheme()
        self.chooser_button.set_tooltip_text('style: ' + self.current_scheme.get_name())
        self.box_h.pack_end(self.chooser_button, False, False, 0)
        self.pack_start(self.box_h, False, True, 0)

        # the view of the json
        self.scrolled_window = Gtk.ScrolledWindow()
        self.model_viewer = GtkSource.View()
        self.model_viewer.set_editable(False)
        self.model_viewer_buffer = self.model_viewer.get_buffer()
        self.lm = GtkSource.LanguageManager()
        self.model_viewer_buffer.set_language(self.lm.get_language('json'))
        self.model_viewer_buffer.set_style_scheme(self.current_scheme)
        self.scrolled_window.add(self.model_viewer)
        self.pack_start(self.scrolled_window, True, True, 0)

    def _update_style(self, widget, spec):
        if spec.name == 'style-scheme':
            self.current_scheme = self.chooser_button.get_style_scheme()
            self.model_viewer_buffer.set_style_scheme(self.current_scheme)
            self.chooser_button.set_label('')
            self.chooser_button.set_tooltip_text('style: ' + self.current_scheme.get_name())

    def options_toggle_hide(self, button):
        visible = self.box_h.is_visible()
        if visible:
            self.box_h.hide()
        else:
            self.box_h.show()

    def update(self, model):
        """
        Gets the data of the model and makes a JSON string out of it. Intended to display the model data as plain JSON
        :param data_model.TestSpecification model: a instance of the TestSpecification class
        :param data_model.TestSequence model: a instance of the TestSpecification class
        """
        assert isinstance(model, data_model.TestSpecification) or model is None
        if model is not None:
            json_str = json.dumps(model, sort_keys=True, indent=8, default=model.serialize)
            self.model_viewer_buffer.set_text(json_str)
        else:
            self.model_viewer_buffer.set_text('{}')


def run():
    bus_name = cfg.get('dbus_names', 'tst')
    dbus.validate_bus_name(bus_name)

    applica = TstApp(bus_name, Gio.ApplicationFlags.FLAGS_NONE, logger=logger)
    applica.run()


if __name__ == '__main__':
    run()
