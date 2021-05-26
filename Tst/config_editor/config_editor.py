#!/usr/bin/env python3
"""
Window for showing and editing a configuration file. If more configuration files are loaded, a merged version is shown.

This is a Gtk.Window which has for every section in the configuration a Frame with label. Within this frame for every
option of the section a row containing out of a label, entry field and optionally a button to open a FileChooserDialog
is added (see Class OptionLine).

Features:

* Read the configuration from file
* Set a parameter in the configuration
* Save a configuration as file

The OptionLine class is used to create the rows for every option. The event handling if a option was changed is done here.

Module content:

* Module level functions:

    * :func:`create_console_handler <confignator.config_editor.create_console_handler>`
    * :func:`build_log_file_path <confignator.config_editor.build_log_file_path>`
    * :func:`create_file_handler <confignator.config_editor.create_file_handler>`

* Classes:

    * :class:`Gtk.Application: Application <confignator.config_editor.Application>`
    * :class:`Gtk.Window: ConfigurationEditor <confignator.config_editor.ConfigurationEditor>`
    * :class:`PageWidget <confignator.config_editor.PageWidget>`
    * :class:`OptionLine <confignator.config_editor.OptionLine>`

When the Gtk.Application is started the Gtk.Window is created. This window has a Gtk.Notebook and every page of it, is
PageWidget. For every option of the configuration a OptionLine is used.

"""
import sys
import os
import logging
import logging.handlers
import configparser
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gio, GLib, Gdk
import confignator
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl
cfl.add_tst_import_paths()

app_name = 'Configuration Editor'
dbus_name = 'smile.tst.configeditor'
menu_xml = os.path.join(os.path.dirname(__file__), 'app_menu.xml')
css_file = os.path.join(os.path.dirname(__file__), 'style_config_editor.css')

fmt = ''
fmt += '%(levelname)s\t'
fmt += '%(asctime)s\t'
fmt += '%(message)s\t'
fmt += '%(name)s\t'
fmt += '%(funcName)s\t'
fmt += '%(lineno)s\t'
fmt += '%(filename)s\t'
fmt += '%(module)s\t'
fmt += '%(pathname)s\t'
fmt += '%(process)s\t'
fmt += '%(processName)s\t'
fmt += '%(thread)s\t'
fmt += '%(threadName)s\t'

logging_format = fmt

module_logger = logging.getLogger(__name__)
module_logger.setLevel(level=logging.DEBUG)


def create_console_handler(frmt=logging_format):
    """
    Creates a StreamHandler which logs to the console.

    :param str frmt: Format string for the log messages
    :return: Returns the created handler
    :rtype: logging.StreamHandler
    """
    hdlr = logging.StreamHandler()
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    hdlr.setLevel(logging.WARNING)
    return hdlr


def build_log_file_path():
    """"
    Reads from the BasicConfigurationFile the path for the log file. The folder will be created if it does not exist.

    :return: absolute path to the logging file
    :rtype: str
    """
    file_path = confignator.get_option('config-editor-logging', 'log-file-path')
    try:
        os.makedirs(os.path.dirname(file_path), mode=0o777, exist_ok=True)
    except TypeError as e:
        module_logger.exception(e)
        module_logger.critical("Could not create directory for the logging file.")
    return file_path


def create_file_handler(frmt=logging_format):
    """
    Creates a RotatingFileHandler

    :param str frmt: Format string for the log messages
    :return: Returns the created handler
    :rtype: logging.handlers.RotatingFileHandler
    """
    file_name = build_log_file_path()
    hdlr = logging.handlers.RotatingFileHandler(filename=file_name, mode='a', maxBytes=524288, backupCount=3)
    frmt = logging.Formatter(fmt=frmt)
    hdlr.setFormatter(frmt)
    return hdlr


class Application(Gtk.Application):
    """
    GTK Application of the config editor.
    """
    def __init__(self, application_id=dbus_name, file_path=None, flags=Gio.ApplicationFlags.FLAGS_NONE):
        super().__init__(application_id=application_id, flags=flags)
        self.file_path = file_path
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)

        action = Gio.SimpleAction.new('quit', None)
        action.connect('activate', self.on_quit)
        self.add_action(action)

        action = Gio.SimpleAction.new('open_doc', None)
        action.connect('activate', self.on_open_doc)
        self.add_action(action)

        # create the menu
        builder = Gtk.Builder.new_from_file(menu_xml)
        self.set_menubar(builder.get_object('app-menu'))

    def do_activate(self):
        # only allow a single window and raise any existing ones
        if not self.window:
            # Windows are associated with the application
            # when the last one is closed the application shuts down
            self.window = ConfigurationEditor(application=self,
                                              file_path=self.file_path)
        self.window.present()

    def on_open_doc(self, *args):
        confignator.documentation()

    def on_quit(self, action, param):
        self.quit()


class ConfigurationEditor(Gtk.ApplicationWindow):
    """ This window is for editing the configuration file. """
    def __init__(self, file_path, logger=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if logger is None:
            module_logger.addHandler(create_console_handler())
            module_logger.addHandler(create_file_handler())
            self.logger = module_logger
        else:
            self.logger = logger
        self.logger.info('Initializing a instance of ConfigurationEditor class')
        self.tabs = []
        self.merge_cfg = None
        self.merge_page = None
        self.page_widget = None
        # loads all configuration files listed in file_path & at least the configuration file of the confignator
        self.load_configuration(file_path=file_path)

        self._show_interpol_val = None
        self._show_merge_page = None

        self.show_interpol_val = False
        self.show_merge_page = True

        # actions
        self.act_siv = Gio.SimpleAction.new_stateful('show_interpol_val',
                                                     None,
                                                     GLib.Variant.new_boolean(self.show_interpol_val))
        self.act_siv.connect('change-state', self.toggle_show_interpol_val)
        self.add_action(self.act_siv)

        self.act_smp = Gio.SimpleAction.new_stateful('show_merge_page',
                                                     None,
                                                     GLib.Variant.new_boolean(self.show_merge_page))
        self.act_smp.connect('change-state', self.toggle_show_merge_page)
        self.add_action(self.act_smp)

        action = Gio.SimpleAction.new('open', None)
        action.connect('activate', self.on_open)
        self.add_action(action)

        action = Gio.SimpleAction.new('save', None)
        action.connect('activate', self.on_save_config)
        self.add_action(action)

        action = Gio.SimpleAction.new('save_as', None)
        action.connect('activate', self.on_save_as)
        self.add_action(action)

        action = Gio.SimpleAction.new('reload', None)
        action.connect('activate', self.on_reload)
        self.add_action(action)

        # GUI
        self.outer_box = Gtk.Box()
        self.outer_box.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar & place for info bar (see function add_info_bar)
        self.btn_open_file = Gtk.ToolButton()
        self.btn_open_file.set_icon_name('document-open')
        self.btn_open_file.set_tooltip_text('Open file')
        self.btn_open_file.connect('clicked', self.on_open)
        self.btn_save = Gtk.ToolButton()
        self.btn_save.set_icon_name('document-save')
        self.btn_save.set_tooltip_text('Save')
        self.btn_save.connect('clicked', self.on_save_config)
        self.btn_reload = Gtk.ToolButton()
        self.btn_reload.set_icon_name('view-refresh-symbolic')
        self.btn_reload.set_tooltip_text('Reload all files')
        self.btn_reload.connect('clicked', self.on_reload)
        self.toolbar = Gtk.Toolbar()
        self.toolbar.insert(self.btn_open_file, 0)
        self.toolbar.insert(self.btn_save, 1)
        self.toolbar.insert(self.btn_reload, 2)
        self.outer_box.pack_start(self.toolbar, False, True, 0)

        self.info_bar = None

        # create the Notebook and the pages for all loaded configuration files
        self.notebook = Gtk.Notebook()
        self.outer_box.pack_start(self.notebook, True, True, 0)
        self.create_notebook_pages()
        self.notebook.connect('switch-page', self.on_switch_page)
        # status bar
        self.stat_bar = Gtk.Statusbar()
        self.outer_box.pack_start(self.stat_bar, False, False, 0)

        self.add(self.outer_box)

        self.connect('destroy', self.on_destroy)
        self.set_position(Gtk.PositionType.RIGHT)
        self.resize(900, 900)

        # for styling the application with CSS
        context = self.get_style_context()
        Gtk.StyleContext.add_class(context, 'cfg-css')
        self.on_apply_css()
        self.show_all()

    @property
    def show_interpol_val(self):
        return self._show_interpol_val

    @show_interpol_val.setter
    def show_interpol_val(self, value):
        assert isinstance(value, bool)
        self._show_interpol_val = value

    @property
    def show_merge_page(self):
        return self._show_merge_page

    @show_merge_page.setter
    def show_merge_page(self, value):
        assert isinstance(value, bool)
        self._show_merge_page = value

    def load_configuration(self, file_path=None, *args):
        """
        Creates a instance of config.Config and sets this as configuration. The application title is set.

        :param str file_path: path to the configuration file which should be loaded
        """
        self.logger.debug('load configuration: {}'.format(file_path))
        self.merge_cfg = confignator.get_config(file_path=file_path, logger=self.logger, load_denoted_files=True)
        self.set_app_title()

    def set_app_title(self):
        """
        Sets the title of the application. String depends if a single file was loaded or a bunch of files
        """
        self.logger.debug('setting the title of the application')
        self.set_title(app_name)

    def create_notebook_pages(self):
        self.set_merge_page()
        # create notebook pages for every configuration file
        for path in self.merge_cfg.files:
            wid, idx = self.new_page(file_path=path)
            # self.tabs.append((path, idx))
            self.logger.debug('created notebook page with index {} for: {}'.format(idx, path))

    def set_merge_page(self):
        if self.show_merge_page is False and self.merge_page is not None:
            page_index = self.notebook.page_num(self.merge_page)
            self.notebook.remove_page(page_index)
            self.merge_page = None
        if self.show_merge_page is True and self.merge_page is None:
            self.merge_page, merge_page_idx = self.new_page(cfg=self.merge_cfg, file_path=None)
            self.logger.debug('created merge page with index {} for: {}'.format(merge_page_idx, self.merge_cfg.files))

    def new_page(self, cfg=None, file_path=None):
        self.page_widget = PageWidget(window=self, file_path=file_path, cfg=cfg)
        # create page label
        if file_path is not None:
            label_text = os.path.basename(file_path)
            self.create_new_merge = False
        else:
            label_text = 'Merge'
            self.create_new_merge = True
        label_box = Gtk.Box()
        label_box.set_orientation(Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label()
        label.set_text(label_text)
        label_btn_close = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.BUTTON)
        label_btn_close.set_tooltip_text('Close')
        label_box.pack_start(label, True, True, 0)
        label_box.pack_start(label_btn_close, True, True, 0)
        label_box.show_all()
        # append notebook page
        if self.create_new_merge:
            page_index = self.notebook.insert_page(child=self.page_widget, tab_label=label_box, position=0)
        else:
            page_index = self.notebook.append_page(child=self.page_widget, tab_label=label_box)
        # connect the tab close button
        label_btn_close.connect('clicked', self.on_close_notebook_page, self.page_widget)
        self.show_all()
        self.notebook.set_current_page(page_index)
        return self.page_widget, page_index

    def on_close_notebook_page(self, button, page_widget):
        # remove the page from the notebook
        page_index = self.notebook.page_num(page_widget)
        self.notebook.remove_page(page_index)
        # if the merge page is closed, don't create it again
        if page_widget == self.merge_page:
            self.toggle_show_merge_page()
        # remove the the entry in self.merge_cfg.files
        file_path = page_widget.file_path
        for idx, entry in enumerate(self.merge_cfg.files):
            if entry == file_path:
                self.merge_cfg.files.pop(idx)
        self.merge_cfg.load_denoted_files = False
        # show the changes
        self.update_page()

    def rebuild_pages(self):
        for idx in range(0, self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(idx)
            page.recreate_sections()

    def update_page(self, page_idx=None, except_section=None, except_option=None):
        if page_idx is None:
            page_idx = self.notebook.get_current_page()
        page_widget = self.notebook.get_nth_page(page_idx)
        page_widget.update_option_data(except_section=except_section, except_option=except_option)
        if self.show_merge_page and not self.create_new_merge:
            self.set_merge_page()
        if self.create_new_merge:
            self.create_new_merge = False

    def on_reload(self, *args):
        for idx in range(0, self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(idx)
            page.reload_config_files()

    def on_switch_page(self, notebook, page, page_num):
        switched_to = self.notebook.get_nth_page(page_num)
        self.update_page()
        if switched_to.file_path is not None:
            message = str(switched_to.file_path)
        else:
            message = ''
        self.stat_bar.push(1, message)

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
        self.outer_box.pack_start(self.info_bar, False, True, 0)
        # move the info bar below the toolbar:
        self.outer_box.reorder_child(self.info_bar, 1)
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

    def toggle_show_interpol_val(self, *args):
        self.show_interpol_val = not self.show_interpol_val
        self.act_siv.set_state(GLib.Variant.new_boolean(self.show_interpol_val))
        self.update_page()

    def toggle_show_merge_page(self, *args):
        self.show_merge_page = not self.show_merge_page
        self.act_smp.set_state(GLib.Variant.new_boolean(self.show_merge_page))
        self.set_merge_page()

    def on_destroy(self, *args):
        self.logger.info('Self-Destruct initiated.\n')
        self.destroy()

    def on_open(self, *args):
        dialog = Gtk.FileChooserDialog('Please choose a folder',
                                       self,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        self.add_filters(dialog)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            # add a new notebook page
            self.new_page(file_path=file_selected)
            # add the new file to the merge config
            self.merge_cfg.files.append(file_selected)
            self.update_page()
        elif response == Gtk.ResponseType.CANCEL:
            pass
        dialog.destroy()

    def save_config(self, configuration, file_path=None):
        try:
            saved_to = configuration.save_to_file(file_path=file_path)
            self.add_info_bar(message_type=Gtk.MessageType.INFO,
                              message='Successfully saved in {}'.format(saved_to))
            self.update_page()
        except OSError as e:
            self.logger.exception(e)
            self.logger.error('Failed to save the configuration. OSError.')
            self.add_info_bar(message_type=Gtk.MessageType.ERROR,
                              message=e.strerror)
        except ValueError as e:
            self.on_save_as()
            # self.logger.exception(e)
            # self.logger.error('Failed to save the configuration. ValueError. {}'.format(e.args[0]))
            # self.add_info_bar(message_type=Gtk.MessageType.ERROR,
            #                   message=e.args[0])

    def on_save_config(self, *args):
        current_page = self.notebook.get_current_page()
        page_widget = self.notebook.get_nth_page(current_page)
        cfg = page_widget.cfg
        self.save_config(configuration=cfg)

    def on_save_as(self, *args):
        dialog = Gtk.FileChooserDialog('Save configuration as',
                                       self,
                                       Gtk.FileChooserAction.SAVE,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        self.add_filters(dialog)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_selected = dialog.get_filename()
            current_page = self.notebook.get_current_page()
            page_widget = self.notebook.get_nth_page(current_page)
            cfg = page_widget.cfg
            # self.merge_cfg.files.append(file_selected)
            self.save_config(configuration=cfg, file_path=file_selected)
        elif response == Gtk.ResponseType.CANCEL:
            pass
        dialog.destroy()

    def add_filters(self, dialog):
        filter_text = Gtk.FileFilter()
        filter_text.set_name('cfg')
        filter_text.add_pattern('*.cfg')
        dialog.add_filter(filter_text)

        filter_any = Gtk.FileFilter()
        filter_any.set_name('Any files')
        filter_any.add_pattern('*')
        dialog.add_filter(filter_any)

    def on_apply_css(self, *args):
        """
        Applies the css file.
        """
        self.logger.debug('Applying CSS')
        style_provider = Gtk.CssProvider()
        css = open(css_file, 'rb')  # rb needed for python 3 support
        css_data = css.read()
        css.close()
        style_provider.load_from_data(css_data)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                                 style_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.StyleContext.reset_widgets(Gdk.Screen.get_default())


class PageWidget(Gtk.ScrolledWindow):
    def __init__(self, cfg, file_path, window, logger=module_logger, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cfg = cfg
        self.file_path = file_path
        self.window = window
        self.logger = logger
        self.rows = []
        if cfg is not None:
            self.file_path = None
        if cfg is None and file_path is not None:
            self.cfg = confignator.get_config(file_path=self.file_path, logger=self.logger)
        if cfg is None and file_path is None:
            tb = sys.exc_info()[2]
            message = 'None of the both arguments was provided (cfg or file_path). One of them is needed.'
            raise ValueError(message).with_traceback(tb)
        self.box_for_frames = Gtk.Box()
        self.box_for_frames.set_orientation(Gtk.Orientation.VERTICAL)
        self.add(self.box_for_frames)
        # for every option create a row with label, entry field and an (optional) button to open a FileChooserDialog
        self.create_all_sections()

    def create_all_sections(self):
        """ For every option in the configuration create a line consisting out of a label, entry field and a button """
        self.rows = []
        for section in self.cfg.sections():
            section_frame = self.create_section(section=section)
            self.box_for_frames.pack_start(section_frame, True, True, 0)

    def create_section(self, section):
        """ For every section a frame is created. Then for every option in the section a instance of the class OptionLine
        is created. Then the label, entry and optionally a button are added to the grid.

        :param section: section of the configuration
        :return: Frame containing OptionLine instances (which are arranged in a grid)
        :rtype: Gtk.Frame
        """
        frame = Gtk.Frame()
        frame.set_label(section)
        grid = Gtk.Grid()
        row_no = 0
        for option in self.cfg.options(section):
            row = OptionLine(section, option, self.cfg, self.window, self.logger)
            self.rows.append(row)
            grid.attach(row.option_label, left=0, top=row_no, width=1, height=1)
            grid.attach(row.option_entry, left=1, top=row_no, width=1, height=1)
            if hasattr(row, 'btn_choose_dir'):
                grid.attach(row.btn_choose_dir, left=2, top=row_no, width=1, height=1)
            row_no += 1
        frame.add(grid)
        # for styling the application with CSS
        context = grid.get_style_context()
        Gtk.StyleContext.add_class(context, 'cfg-optionline')
        return frame

    def reload_config_files(self):
        self.cfg.reload_config_files()
        self.recreate_sections()

    def recreate_sections(self):
        for child in self.box_for_frames.get_children():
            child.destroy()
        self.create_all_sections()
        self.show_all()

    def update_option_data(self, except_section, except_option):
        for row in self.rows:
            if row.section != except_section and row.option != except_option:
                row.set_entry_text()


class OptionLine:
    """
    This class represents a option in the configuration file. A label, entry field and optionally a button (to start a
    FileChooserDialog) is created for the option.
    When a entry is changed the configuration is updated, but not yet saved to file (this is triggered by the Save
    button). Thus changes can be discarded if the window is closed without saving.
    """
    def __init__(self, section, option, configuration, window, logger):
        self.logger = logger
        self.win = window
        self.config = configuration
        self.section = section
        self.option = option
        # label
        self.option_label = Gtk.Label()
        self.option_label.set_xalign(0)
        # option entry field
        self.option_entry = Gtk.Entry()
        self.option_entry.set_width_chars(80)
        self.set_data()

        self.option_entry.connect('changed', self.on_entry_edited)
        if section == 'paths':
            self.btn_choose_dir = Gtk.Button.new_from_icon_name('document-open-symbolic', Gtk.IconSize.BUTTON)
            self.btn_choose_dir.set_tooltip_text('Choose a path')
            self.btn_choose_dir.connect('clicked', self.on_choose_dir)

    def get_entry_text(self):
        """ Get the current text of the entry field """
        self.option_entry.get_text()

    def set_label_text(self):
        """ Set the text of the label """
        self.option_label.set_text(self.option)

    def set_entry_text(self):
        """ Set the text of the entry field """
        show_data_raw = not self.win.show_interpol_val
        try:
            if show_data_raw is False:
                merge_config = confignator.get_config()
                interpolated_value = merge_config.get(self.section, self.option, raw=False)
                self.option_entry.set_text(interpolated_value)
            else:
                raw_value = self.config.get(self.section, self.option, raw=True)
                self.option_entry.set_text(raw_value)
        except configparser.InterpolationMissingOptionError as e:
            self.logger.debug(e)

    def set_data(self):
        """ Sets the text of the label and the entry field """
        self.set_label_text()
        self.set_entry_text()

    def on_choose_dir(self, button):
        """ Event when the button to open a FileChooserDialog was clicked """
        dialog = Gtk.FileChooserDialog('Please choose a file',
                                       None,
                                       Gtk.FileChooserAction.SELECT_FOLDER,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            self.config.set_parameter(section=self.section, option=self.option, value=path)
            self.set_data()
        elif response == Gtk.ResponseType.CANCEL:
            pass
        dialog.destroy()

    def on_entry_edited(self, entry_field):
        """ Event when the text of an entry field was changed """
        new_option = entry_field.get_text()
        self.config.set_parameter(section=self.section, option=self.option, value=new_option)
        # show the change in other fields too, if they are linked, except the field the user changed
        self.win.update_page(except_section=self.section, except_option=self.option)


def run(file_path=None):
    """
    Starts the ConfigEditor application. If file_path is provided, this file is opened.
    Otherwise the default configuration is opened (merge configuration)

    :param file_path: path to a configuration file
    """
    app = Application(application_id=dbus_name, file_path=file_path)
    app.run(sys.argv)


if __name__ == '__main__':
    run()
