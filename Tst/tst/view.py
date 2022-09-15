import os
import logging
import gettext
import gi
import time

import db_interaction

gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')
from gi.repository import Gtk, Gdk, GtkSource, GdkPixbuf
# -------------------------------------------
import data_model
import dnd_data_parser
import toolbox
import cairo
import sys

import confignator
ccs_path = confignator.get_option('paths', 'ccs')
sys.path.append(ccs_path)

import ccs_function_lib as cfl

lm = GtkSource.LanguageManager()
lngg = lm.get_language('python')

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.WARNING)
console_hdlr = toolbox.create_console_handler()
logger.addHandler(hdlr=console_hdlr)

# using gettext for internationalization (i18n)
localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'locale')
translate = gettext.translation('handroll', localedir, fallback=True)
_ = translate.gettext

style_path = os.path.join(os.path.dirname(__file__), 'style')

widget_grip_upper = 1 / 4
widget_grip_lower = 3 / 4


class Board(Gtk.Box):
    """
    A sketch desk consists out of a toolbar and a grid where the StepWidgets are placed.

    Features

    * data model functions

        * change of the number of a step triggers renumbering and reordering of all steps

    * drag and drop

        * reorder the steps
        * drag the 'Add step' button and insert a new step
        * drop a step before or after a existing step. Highlight the associated border
        * select multiple steps and move them as a block

    * adding a parallel thread

        * place the start before, within or after an existing step
        * place the end before, within or after an existing step

    * loop over steps

        * select multiple steps add loop over them till a break condition is reached (ToDo)

    """
    def __init__(self, model, app, filename=None, logger=logger):
        """
        When an instance is initialized:
        * a data model instance is created
        * the toolbar is created
        * a instance of a grid is added
        * drag and drop is set up
        """
        #assert isinstance(model, data_model.TestSpecification)
        self.model = model
        self.app = app
        self._filename = filename
        self.logger = logger

        self._test_is_locked = None
        # Save Button in TST clicked for first time, Always do save_as to not overwrite something, used in tst.py
        self._ask_overwrite = True

        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.VERTICAL)

        # test meta data
        self.test_meta_data_box = Gtk.Box()
        self.test_meta_data_box.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.test_meta_data_labels = Gtk.Box()
        self.test_meta_data_labels.set_orientation(Gtk.Orientation.VERTICAL)
        self.test_meta_data_entries = Gtk.Box()
        self.test_meta_data_entries.set_orientation(Gtk.Orientation.VERTICAL)
        self.test_meta_data_pre_post_con = Gtk.Box()
        self.test_meta_data_pre_post_con.set_orientation(Gtk.Orientation.VERTICAL)
        self.test_meta_data_pre_post_con_edit = Gtk.Box()
        self.test_meta_data_pre_post_con_edit.set_orientation(Gtk.Orientation.VERTICAL)
        # name of the test
        self.test_meta_data_name_label = Gtk.Label()
        self.test_meta_data_name_label.set_text('Name of the test:')
        self.test_meta_data_labels.pack_start(self.test_meta_data_name_label, True, True, 0)
        self.test_meta_data_name = Gtk.Entry()
        self.test_meta_data_name.set_placeholder_text('< name of the test>')
        self.test_meta_data_entries.pack_start(self.test_meta_data_name, True, True, 0)
        # test description
        self.test_meta_data_desc_label = Gtk.Label()
        self.test_meta_data_desc_label.set_text('Description of the test:')
        self.test_meta_data_labels.pack_start(self.test_meta_data_desc_label, True, True, 0)
        self.test_meta_data_desc = Gtk.Entry()
        self.test_meta_data_desc.set_placeholder_text('< description of the test>')
        self.test_meta_data_entries.pack_start(self.test_meta_data_desc, True, True, 0)
        # spec_version
        self.test_meta_data_spec_version_label = Gtk.Label()
        self.test_meta_data_spec_version_label.set_text('Spec Version:')
        self.test_meta_data_labels.pack_start(self.test_meta_data_spec_version_label, True, True, 0)
        self.test_meta_data_spec_version = Gtk.Entry()
        self.test_meta_data_spec_version.set_placeholder_text('< spec version >')
        self.test_meta_data_entries.pack_start(self.test_meta_data_spec_version, True, True, 0)
        # IASW Software Version
        self.test_meta_data_iasw_version_label = Gtk.Label()
        self.test_meta_data_iasw_version_label.set_text('IASW Version:')
        self.test_meta_data_labels.pack_start(self.test_meta_data_iasw_version_label, True, True, 0)
        self.test_meta_data_iasw_version = Gtk.Entry()
        self.test_meta_data_iasw_version.set_placeholder_text('< IASW version >')
        self.test_meta_data_entries.pack_start(self.test_meta_data_iasw_version, True, True, 0)
        # checkbox for locking the step numbers
        self.test_is_locked_label = Gtk.Label()
        self.test_is_locked_label.set_text(_('Lock step enumeration:'))
        self.test_meta_data_labels.pack_start(self.test_is_locked_label, True, True, 0)
        self.text_meta_data_test_is_locked = Gtk.CheckButton()
        self.test_meta_data_entries.pack_start(self.text_meta_data_test_is_locked, True, True, 0)

        # Add pre post condition selections
        # Pre conditions
        self.precon_selection_label = Gtk.Label()
        self.precon_selection_label.set_text('Pre-Conditions:')
        self.precon_selection = Gtk.ComboBoxText()
        self.set_precon_model()
        self.precon_selection.connect("changed", self.on_precon_changed)
        # Post conditions
        self.postcon_selection_label = Gtk.Label()
        self.postcon_selection_label.set_text('Post-Conditions:')
        self.postcon_selection = Gtk.ComboBoxText()
        self.set_postcon_model()
        self.postcon_selection.connect("changed", self.on_postcon_changed)

        # add to pre post box
        self.test_meta_data_pre_post_con.pack_start(self.precon_selection_label, False, True, 0)
        self.test_meta_data_pre_post_con.pack_start(self.precon_selection, False, True, 0)
        self.test_meta_data_pre_post_con.pack_start(self.postcon_selection_label, False, True, 0)
        self.test_meta_data_pre_post_con.pack_start(self.postcon_selection, False, True, 0)
        self.test_meta_data_box.set_spacing(20)

        # Add Edit Buttons
        self.precon_edit_button = Gtk.Button.new_with_label('Edit')
        self.precon_edit_button.connect("clicked", self.precon_edit_clicked)
        self.postcon_edit_button = Gtk.Button.new_with_label('Edit')
        self.postcon_edit_button.connect("clicked", self.postcon_edit_clicked)

        self.test_meta_data_pre_post_con_edit.pack_start(self.precon_edit_button, False, True, 17)
        self.test_meta_data_pre_post_con_edit.pack_start(self.postcon_edit_button, False, True, 0)

        self.test_comment_box = Gtk.Box()
        self.test_comment_box.set_orientation(Gtk.Orientation.VERTICAL)
        self.lbl_box_comment = Gtk.Box()
        self.lbl_box_comment.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.label_comment = Gtk.Label.new()
        self.label_comment.set_text(_('Test Comment:'))
        self.lbl_box_comment.pack_start(self.label_comment, False, False, 0)
        # Make the area where the real command is entered
        self.comment_scrolled_window = Gtk.ScrolledWindow()
        # self.comment_scrolled_window.set_size_request(200, 100)
        self.test_meta_data_comment = Gtk.TextView.new()
        self.comment_scrolled_window.add(self.test_meta_data_comment)

        self.test_comment_box.pack_start(self.lbl_box_comment, False, False, 0)
        self.test_comment_box.pack_start(self.comment_scrolled_window, True, True, 0)

        # add the meta data
        self.test_meta_data_box.pack_start(self.test_meta_data_labels, False, True, 0)
        self.test_meta_data_box.pack_start(self.test_meta_data_entries, False, True, 0)
        self.test_meta_data_box.pack_start(self.test_meta_data_pre_post_con, False, True, 0)
        self.test_meta_data_box.pack_start(self.test_meta_data_pre_post_con_edit, False, True, 0)
        self.test_meta_data_box.pack_start(self.test_comment_box, True, True, 0)
        self.pack_start(self.test_meta_data_box, False, True, 0)

        # making the toolbar
        self.btn_add_step = Gtk.ToolButton()
        self.btn_add_step.set_label(_('Add step'))
        self.btn_add_step.set_tooltip_text(_('Add step'))
        self.btn_add_step.set_icon_name('list-add')
        self.btn_add_step.connect('clicked', self.on_btn_clicked_add_step)
        self.btn_collapse_all_steps = Gtk.ToolButton()
        self.btn_collapse_all_steps.set_label(_('Collapse all steps'))
        self.btn_collapse_all_steps.set_tooltip_text(_('Collapse all steps'))
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(ccs_path + '/pixmap/collapse.svg', 24, 24)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        self.btn_collapse_all_steps.set_icon_widget(icon)
        self.btn_collapse_all_steps.connect('clicked', self.collapse_all_steps)
        self.btn_expand_all_steps = Gtk.ToolButton()
        self.btn_expand_all_steps.set_label(_('Expand all steps'))
        self.btn_expand_all_steps.set_tooltip_text(_('Expand all steps'))
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(ccs_path + '/pixmap/expand.svg', 24, 24)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        self.btn_expand_all_steps.set_icon_widget(icon)
        self.btn_expand_all_steps.connect('clicked', self.expand_all_steps)
        # self.btn_add_parallel = Gtk.ToolButton()
        # self.btn_add_parallel.set_label(_('Add parallel sequence'))
        # self.btn_add_parallel.connect('clicked', self.on_btn_clicked_add_parallel)
        self.toolbar = Gtk.Toolbar()
        self.toolbar.insert(self.btn_add_step, 0)
        self.toolbar.insert(self.btn_collapse_all_steps, 1)
        self.toolbar.insert(self.btn_expand_all_steps, 2)
        # self.toolbar.insert(self.btn_add_parallel, 3)
        self.pack_start(self.toolbar, False, True, 0)

        # add the grid for steps
        self.scrolled_window = Gtk.ScrolledWindow()
        self.grid = Gtk.Grid()
        # self.grid.set_row_spacing(20)
        self.scrolled_window.add(self.grid)
        self.pack_start(self.scrolled_window, True, True, 0)

        # scheme for the GtkSource Views
        self.style_manager = GtkSource.StyleSchemeManager.get_default()
        self.style_manager.append_search_path(style_path)
        self.current_scheme = self.style_manager.get_scheme('darcula')

        # connect signals
        self.test_meta_data_name.connect('changed', self.on_test_name_change)
        self.test_meta_data_desc.connect('changed', self.on_test_desc_change)
        self.test_meta_data_spec_version.connect('changed', self.on_test_spec_version_change)
        self.test_meta_data_iasw_version.connect('changed', self.on_test_iasw_version_change)
        self.text_meta_data_test_is_locked.connect('toggled', self.on_test_locked_toggled)
        self.test_meta_data_comment.get_buffer().connect('changed', self.on_comment_change)

    @property
    def test_is_locked(self):
        return self._test_is_locked

    @test_is_locked.setter
    def test_is_locked(self, value):
        assert isinstance(value, bool)
        self._test_is_locked = value

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value

    @property
    def ask_overwrite(self):
        return self._ask_overwrite

    @ask_overwrite.setter
    def ask_overwrite(self, value):
        self._ask_overwrite = value

    def update_widget_data(self):
        """
        Updates the grid with the steps. All widgets of the grid are destroyed. The grid is build new from the model.
        """
        # update the meta data of the test spec
        self.set_test_spec_metadata()
        # update the steps grid
        self.destroy_all_step_widgets()
        self.build_all_steps()
        # refresh all widgets
        self.show_all()

    def set_test_spec_metadata(self):
        """ Update the displayed data of the test specification using the data from the model """
        # set the name of the test specification using the data from the model
        self.test_meta_data_name.set_text(self.model.name)
        # set the description of the test specification using the data from the model
        self.test_meta_data_desc.set_text(self.model.description)
        # set the Specification version of the test specification from the data model
        self.test_meta_data_spec_version.set_text(self.model.spec_version)
        # set the Software version of the test specification from the data model
        self.test_meta_data_iasw_version.set_text(self.model.iasw_version)
        # set the pre-condition name
        if self.model.precon_name:
            found = False
            for index, precon_name in enumerate(self.precon_selection.get_model()):
                if precon_name[0] == self.model.precon_name:
                    found = True
                    self.precon_selection.set_active(index)
            if not found:
                msg = 'Given Pre-Condition Name could not be found/loaded'
                self.logger.warning(msg)
                # self.app.add_info_bar(message_type=Gtk.MessageType.INFO, message=msg)
                self.on_precon_changed(self.precon_selection)

        # set the post-condition name
        if self.model.postcon_name:
            found = False
            for index, postcon_name in enumerate(self.postcon_selection.get_model()):
                if postcon_name[0] == self.model.postcon_name:
                    found = True
                    self.postcon_selection.set_active(index)
            if not found:
                msg = 'Given Post-Condition Name could not be found/loaded'
                self.logger.warning(msg)
                # self.app.add_info_bar(message_type=Gtk.MessageType.INFO, message=msg)
                self.on_postcon_changed(self.precon_selection)

        # Set the test comment
        self.test_meta_data_comment.get_buffer().set_text(self.model.comment)

        # Set the Locked STep numeration
        self.text_meta_data_test_is_locked.set_active(self.model.primary_counter_locked)

    def collapse_all_steps(self, button):
        """ Close all expander of the steps """
        steps = self.grid.get_children()
        for child in steps:
            child.step_detail_visible = False

    def expand_all_steps(self, button):
        """ Expand all step widgets """
        steps = self.grid.get_children()
        for child in steps:
            child.step_detail_visible = True

    def build_step(self, step_number):
        """ Create a new step widget and add it to the grid

        :param: step_number: number of a step
        """
        step_to_add = StepWidget(model=self.model, step_number=step_number, app=self.app, board=self, logger=self.logger)  # TODO: seq_num parameter??
        # find the next free grid cell
        number_of_existing_steps = len(self.view.grid.get_children())
        row = number_of_existing_steps - 1
        self.grid.attach(step_to_add, 0, row, 1, 1)

    def on_btn_clicked_add_step(self, button):
        """ add a step to the model, then add a StepWidget to the steps grid and update the model viewer

        :param: button: button widget which was clicked
        """
        # ToDo
        # self.model.get_sequence(self.sequence)add_step_below()
        self.model.get_sequence(0).add_step_below()
        # ToDo
        self.update_widget_data()
        self.app.update_model_viewer()

    def on_btn_clicked_add_parallel(self, button):
        """ Add the first step of a new sequence. Add the step to start the sequence.

        :param: button: Gtk.Button widget which was clicked
        """
        # create the new sequence in the data model
        new_seq_num = self.model.add_sequence()
        # create the step to start the sequence (only the 1st sequence can start further ones)
        new_step = data_model.create_start_sequence_step(new_seq_num)
        self.model.get_sequence(0).add_step_below(step_instance=new_step)
        # create first step of the new sequence
        self.model.get_sequence(new_seq_num).add_step_below()
        # update the view
        self.update_widget_data()
        self.app.update_model_viewer()

    def set_precon_model(self, active_name=None):
        section_dict = db_interaction.get_pre_post_con('pre')
        active_nbr = 0
        for count, condition in enumerate(section_dict):
            self.precon_selection.append_text(condition.name)
            if active_name == condition.name:
                active_nbr = count
        self.precon_selection.set_active(active_nbr)
        self.on_precon_changed(self.precon_selection)
        return

    def on_precon_changed(self, widget):
        # get the name out of the widget
        precon_name = widget.get_active_text()
        # update the model
        self.model.precon_name = precon_name
        # Set the Precon Description
        section_dict = db_interaction.get_pre_post_con('pre')
        for condition in section_dict:
            if condition.name == precon_name:
                self.model.precon_descr = condition.description
                self.model.precon_code = condition.condition
        # update the data model viewer
        self.app.update_model_viewer()
        #current_model = self.app.current_model()
        #if current_model:
        #    current_model.precon = precon_name
        return

    def set_postcon_model(self, active_name=None):
        section_dict = db_interaction.get_pre_post_con('post')
        active_nbr = 0
        for count, condition in enumerate(section_dict):
            self.postcon_selection.append_text(condition.name)
            if active_name == condition.name:
                active_nbr = count
        self.postcon_selection.set_active(active_nbr)
        self.on_postcon_changed(self.postcon_selection)
        return

    def on_postcon_changed(self, widget):
        # get the name out of the widget
        postcon_name = widget.get_active_text()
        # update the model
        self.model.postcon_name = postcon_name
        # Set the Postcon Description
        section_dict = db_interaction.get_pre_post_con('post')
        for condition in section_dict:
            if condition.name == postcon_name:
                self.model.postcon_descr = condition.description
                self.model.postcon_code = condition.condition
        # update the data model viewer
        self.app.update_model_viewer()
        #current_model = self.app.current_model()
        #if current_model:
        #    current_model.postcon = postcon_name
        return



    def precon_edit_clicked(self, widget):
        dialog = Edit_Pre_Post_Con_Dialog(self, 'pre', self.precon_selection.get_active())
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.precon_selection.remove_all()
            self.set_precon_model(dialog.selection.get_active_text())
            dialog.destroy()
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()

    def postcon_edit_clicked(self, widget):
        dialog = Edit_Pre_Post_Con_Dialog(self, 'post', self.postcon_selection.get_active())
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.postcon_selection.remove_all()
            self.set_postcon_model(dialog.selection.get_active_text())
            dialog.destroy()
        elif response == Gtk.ResponseType.CANCEL:
            dialog.destroy()

    def on_test_name_change(self, widget):
        """ if the name of test specification is changed update the model and the model viewer

        :param: Gtk.Widget widget: widget
        """
        # get the name out of the widget
        name = widget.get_text()
        # update the model
        self.model.name = name
        # update the data model viewer
        self.app.update_model_viewer()

    def on_test_desc_change(self, widget):
        # get the text out of the buffer
        content = widget.get_text()
        # set the test description in the model
        self.model.description = content
        # update the data model viewer
        self.app.update_model_viewer()

    def on_test_spec_version_change(self, widget):
        # get the Specification Version out of the text buffer of the widget
        spec_version = widget.get_text()
        # update the model
        self.model.spec_version = spec_version
        # update the data model viewer
        self.app.update_model_viewer()

    def on_test_iasw_version_change(self, widget):
        # get the IASW Version out of the text buffer of the widget
        iasw_version = widget.get_text()
        # update the model
        self.model.iasw_version = iasw_version
        # update the data model viewer
        self.app.update_model_viewer()

    def on_test_locked_toggled(self, *args):
        # toggle the value in the widget
        self.test_is_locked = not self.test_is_locked
        # write it back to the data model
        self.model.primary_counter_locked = self.test_is_locked
        # update the data model viewer
        self.app.update_model_viewer()

    def on_comment_change(self, widget):
        """ if the name of test specification is changed update the model and the model viewer

        :param: Gtk.Widget widget: widget
        """
        # get the name out of the widget
        comment = widget.get_text(widget.get_start_iter(), widget.get_end_iter(), True)
        # update the model
        self.model.comment = comment
        # update the data model viewer
        self.app.update_model_viewer()

    def destroy_all_step_widgets(self):
        """
        Destroys all StepWidgets of the current grid
        """
        steps = self.grid.get_children()
        for child in steps:
            child.destroy()

    def build_all_steps(self):
        """
        Creates for every step in the instance of TestSequence a StepWidget-Widget and adds it to the grid.
        """
        def get_top_attach_seq_start(grid, seq_num):
            y = None
            for child in grid.get_children():
                if isinstance(child, StepWidget):
                    if hasattr(child, 'start_sequence'):
                        if child.start_sequence == seq_num:
                            y = grid.child_get_property(child, 'top-attach')
            return y

        def count_seq_children(grid, seq_num):
            count = 0
            for child in grid.get_children():
                x = grid.child_get_property(child, 'left-attach')
                if x == seq_num:
                    count += 1
            return count

        for seq in self.model.sequences:
            assert isinstance(seq, data_model.TestSequence)
            seq_num = seq.sequence
            for step in seq.steps:
                number = step.step_number
                step_to_add = StepWidget(model=self.model, seq_num=seq_num, step_number=number, app=self.app, board=self, logger=self.logger)
                inter_step = InterStepWidget(model=self.model, seq_num=seq_num, app=self.app, board=self, logger=self.logger)

                # the top-attach value is calculated from:
                # position where the sequence starts + already placed steps of this sequence
                nchilds = count_seq_children(grid=self.grid, seq_num=seq_num)
                if seq_num == 0:
                    # the first step starts at the top-attach position 0, because there is no start sequence step
                    top_attach = nchilds
                else:
                    # get the top-attach value of the start sequence step which starts this sequence
                    top_attach_start_seq = get_top_attach_seq_start(grid=self.grid, seq_num=seq_num)
                    top_attach = top_attach_start_seq + nchilds

                self.grid.attach(step_to_add, seq_num, top_attach, 1, 1)
                self.grid.attach(inter_step, seq_num, top_attach+1, 1, 1)

        def get_grid_columns(grid):
            cols = 0
            for child in grid.get_children():
                x = grid.child_get_property(child, 'left-attach')
                width = grid.child_get_property(child, 'width')
                cols = max(cols, x + width)
            return cols
        n_col = get_grid_columns(self.grid)
        return

    def get_step_widget(self, seq_num, step_number):
        step_widget = None
        for child in self.grid.get_children():
            if isinstance(child, StepWidget):
                if child.sequence == seq_num:
                    primary, secondary = data_model.parse_step_number(step_number)
                    step_num = data_model.create_step_number(primary, secondary)
                    if child.step_number == step_num:
                        step_widget = child
        return step_widget


class StepWidget(Gtk.EventBox):
    """ StepWidget is a composite widget to represent one step of a test specification. """
    def __init__(self, model, step_number, seq_num, app, board, logger):
        super().__init__()
        assert isinstance(model, data_model.TestSpecification)
        self.model = model
        self.sequence = seq_num
        self.app = app
        self.board = board
        self.logger = logger

        self._step_number = None
        self._step_description = None
        self._short_description = None
        # self._command_code = None
        # self._verification_code = None
        self._step_detail_visible = None
        self._start_sequence = None
        self._stop_sequence = None

        self.frame = Gtk.Frame()
        self.add(self.frame)

        self.vbox = Gtk.Box()
        self.vbox.set_orientation(Gtk.Orientation.VERTICAL)
        self.frame.add(self.vbox)

        # toolbar
        self.tbox = Gtk.Box()
        self.tbox.set_orientation(Gtk.Orientation.HORIZONTAL)

        self.btn_toggle_detail = Gtk.ToolButton()
        self.btn_toggle_detail.set_tooltip_text(_('Show step details'))
        self.btn_toggle_detail.connect('clicked', self.on_toggle_detail)

        self.label_event_box = Gtk.EventBox()
        self.label_event_box.set_visible_window(False)
        self.label_event_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.label_event_box.connect('button-release-event', self.on_toggle_detail)
        self.label_step_number = Gtk.Label()
        self.label_event_box.add(self.label_step_number)
        self.step_number = step_number

        self.is_active = Gtk.CheckButton()
        self.is_active.set_active(True)
        self.is_active.set_tooltip_text(_('Set if the step is active'))
        self.is_active.connect('clicked', self.on_toggled_is_active)

        self.btn_execute_step = Gtk.ToolButton()
        self.btn_execute_step.set_icon_name('media-playback-start-symbolic')
        self.btn_execute_step.set_tooltip_text(_('Execute step'))
        self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.text_label_event_box = Gtk.EventBox()
        self.text_label_event_box.set_visible_window(False)
        self.text_label_event_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.text_label_event_box.connect('button-release-event', self.on_toggle_detail)
        self.text_label = Gtk.Label()
        self.text_label.set_alignment(0, 0.5)
        self.text_label_event_box.add(self.text_label)

        self.btn_delete_step = Gtk.ToolButton()
        self.btn_delete_step.set_icon_name('edit-delete-symbolic')
        self.btn_delete_step.set_tooltip_text(_('Delete this step'))
        self.btn_delete_step.connect('clicked', self.on_delete_step)

        self.tbox.pack_start(self.btn_toggle_detail, False, False, 0)
        self.tbox.pack_start(self.label_event_box, False, False, 0)
        self.tbox.pack_start(self.text_label_event_box, True, True, 0)
        self.tbox.pack_end(self.btn_delete_step, False, False, 0)
        self.tbox.pack_end(self.is_active, False, False, 0)
        self.tbox.pack_end(self.btn_execute_step, False, False, 0)

        self.vbox.pack_start(self.tbox, True, True, 0)

        # detail area
        self.detail_box = Gtk.Box()
        self.detail_box.set_orientation(Gtk.Orientation.VERTICAL)
        self.detail_box.connect('show', self.on_detail_box_show)
        # self.detail_box.set_homogeneous(True)
        Gtk.StyleContext.add_class(self.detail_box.get_style_context(), 'step-detail-box')  # for CSS styling

        self.vbox.pack_start(self.detail_box, True, True, 0)

        self.set_hexpand(True)

        # area for the commands
        self.whole_description_box = Gtk.Grid()
        self.whole_description_box.set_column_homogeneous(True)
        # self.whole_commands_box.set_orientation(Gtk.Orientation.HORIZONTAL)

        # field for the description
        self.lbl_box_desc = Gtk.Box()
        self.lbl_box_desc.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.desc_label = Gtk.Label.new()
        self.desc_label.set_text(_('Description'))
        self.lbl_box_desc.pack_start(self.desc_label, False, True, 0)
        # self.detail_box.pack_start(self.lbl_box_desc, True, True, 0)
        self.desc_scrolled_window = Gtk.ScrolledWindow()
        # self.desc_scrolled_window.set_size_request(50, 100)
        # self.detail_box.pack_start(self.desc_scrolled_window, False, True, 0)
        self.desc_text_view = Gtk.TextView.new()
        self.desc_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.desc_text_view.set_accepts_tab(False)
        self.desc_scrolled_window.add(self.desc_text_view)
        self.desc_text_buffer = self.desc_text_view.get_buffer()

        # Step Comment Area
        # Make the label, inside a own Box to show it on the left end
        self.lbl_box_step_comment = Gtk.Box()
        self.lbl_box_step_comment.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.step_label_comment = Gtk.Label.new()
        self.step_label_comment.set_text(_('Step Comment'))
        self.lbl_box_step_comment.pack_start(self.step_label_comment, False, False, 0)
        # Make the area where the real command is entered
        self.step_comment_scrolled_window = Gtk.ScrolledWindow()
        # self.step_comment_scrolled_window.set_size_request(200, 100)
        self.step_comment_view = GtkSource.View()
        self.step_comment_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.step_comment_view.set_show_line_numbers(False)
        self.step_comment_scrolled_window.add(self.step_comment_view)
        self.step_comment_buffer = self.step_comment_view.get_buffer()

        # ADD everything to the whole grid
        self.whole_description_box.set_column_spacing(10)
        self.whole_description_box.attach(self.lbl_box_desc, 0, 0, 3, 1)
        self.whole_description_box.attach(self.desc_scrolled_window, 0, 1, 3, 5)
        self.whole_description_box.attach_next_to(self.lbl_box_step_comment, self.lbl_box_desc, Gtk.PositionType.RIGHT, 3, 1)
        self.whole_description_box.attach_next_to(self.step_comment_scrolled_window, self.desc_scrolled_window, Gtk.PositionType.RIGHT, 3, 5)
        self.detail_box.pack_start(self.whole_description_box, True, True, 0)

        # fields for commands and verification
        # lm = GtkSource.LanguageManager()

        # Area for the commands
        self.whole_commands_box = Gtk.Box()
        self.whole_commands_box.set_orientation(Gtk.Orientation.VERTICAL)
        # Make the label, inside a own Box to show it on the left side
        self.lbl_box_commands = Gtk.Box()
        self.lbl_box_commands.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.commands_label = Gtk.Label.new()
        self.commands_label.set_text(_('Commands'))
        self.lbl_box_commands.pack_start(self.commands_label, False, False, 0)
        # self.btn_exec_commands = Gtk.Button.new_from_icon_name(icon_name='media-playback-start', size=Gtk.IconSize.BUTTON)
        # self.btn_exec_commands.connect('clicked', self.on_exec_commands)
        # self.lbl_box_commands.pack_start(self.btn_exec_commands, False, False, 0)
        # Make the area where the real command is entered
        # self.detail_box.pack_start(self.lbl_box_commands, True, True, 0)
        self.commands_scrolled_window = Gtk.ScrolledWindow()
        self.commands_scrolled_window.set_size_request(-1, 200)
        self.commands_view = GtkSource.View()
        self.commands_view.set_auto_indent(True)
        self.commands_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.commands_view.set_show_line_numbers(True)
        # self.commands_view.set_show_right_margin(True)
        self.commands_view.set_highlight_current_line(True)
        self.commands_view.set_indent_on_tab(True)
        self.commands_view.set_insert_spaces_instead_of_tabs(True)
        self.commands_buffer = self.commands_view.get_buffer()
        # draganddrop here
        """
        self.commands_view.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.commands_view.drag_dest_set_target_list(None)
        self.commands_view.drag_dest_add_text_targets()
        
        self.commands_view.connect("drag-motion", self.on_drag_motion_2)
        self.commands_view.connect("drag-leave", self.on_drag_leave)
        """

        self.commands_buffer.set_language(lngg)
        # self.commands_buffer.set_style_scheme(self.board.current_scheme)
        self.commands_scrolled_window.add(self.commands_view)

        self.whole_commands_box.pack_start(self.lbl_box_commands, False, False, 0)
        self.whole_commands_box.pack_start(self.commands_scrolled_window, True, True, 0)
        self.detail_box.pack_start(self.whole_commands_box, True, True, 0)
        # area for the verification
        self.whole_verification_box = Gtk.Grid()
        self.whole_verification_box.set_column_homogeneous(True)

        # Left side of the verification area, where the verification-commands a entered
        # Make the label, inside a own Box to show it on the left side
        self.lbl_box_verification = Gtk.Box()
        self.lbl_box_verification.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.verification_label = Gtk.Label.new()
        self.verification_label.set_text(_('Verification'))
        #self.btn_exec_verification = Gtk.Button.new_from_icon_name(icon_name='media-playback-start', size=Gtk.IconSize.BUTTON)
        #self.btn_exec_verification.connect('clicked', self.on_exec_verification)
        self.lbl_box_verification.pack_start(self.verification_label, False, False, 0)
        # self.lbl_box_verification.pack_start(self.btn_exec_verification, False, False, 0)
        #self.detail_box.pack_start(self.lbl_box_verification, True, True, 0)
        self.verification_scrolled_window = Gtk.ScrolledWindow()
        #self.verification_scrolled_window.set_size_request(50, 100)
        self.verification_view = GtkSource.View()
        self.verification_view.set_auto_indent(True)
        self.verification_view.set_show_line_numbers(True)
        self.verification_view.set_wrap_mode(Gtk.WrapMode.WORD)
        # self.verification_view.set_show_right_margin(True)
        self.verification_view.set_highlight_current_line(True)
        self.verification_view.set_indent_on_tab(True)
        self.verification_view.set_insert_spaces_instead_of_tabs(True)
        self.verification_buffer = self.verification_view.get_buffer()
        self.verification_buffer.set_language(lngg)
        # self.verification_buffer.set_style_scheme(self.board.current_scheme)
        self.verification_scrolled_window.add(self.verification_view)

        # Right side of the verification area, the comment box
        # Make the label, inside a own Box to show it on the left end
        self.lbl_box_verification_description = Gtk.Box()
        self.lbl_box_verification_description.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.verification_label_description = Gtk.Label.new()
        self.verification_label_description.set_text(_('Verification Description'))
        self.lbl_box_verification_description.pack_start(self.verification_label_description, False, False, 0)
        # Make the area where the real command is entered
        self.verification_description_scrolled_window = Gtk.ScrolledWindow()
        #self.verification_comment_scrolled_window.set_size_request(200, 100)
        self.verification_description_view = GtkSource.View()
        self.verification_description_view.set_show_line_numbers(False)
        self.verification_description_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.verification_description_scrolled_window.add(self.verification_description_view)
        self.verification_description_buffer = self.verification_description_view.get_buffer()

        #ADD everything to the whole grid
        self.whole_verification_box.set_column_spacing(10)
        self.whole_verification_box.attach(self.lbl_box_verification, 0, 0, 3, 1)
        self.whole_verification_box.attach(self.verification_scrolled_window, 0, 1, 3, 5)
        self.whole_verification_box.attach_next_to(self.lbl_box_verification_description, self.lbl_box_verification, Gtk.PositionType.RIGHT, 3, 1)
        self.whole_verification_box.attach_next_to(self.verification_description_scrolled_window, self.verification_scrolled_window, Gtk.PositionType.RIGHT, 3, 5)
        self.detail_box.pack_start(self.whole_verification_box, True, True, 0)

        # fill the step with data before connecting the signals (!)
        self.set_data_in_widget()

        # default behavior: step details are hidden
        self.step_detail_visible = False

        # drag and drop: the StepWidget as a drag source
        self.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        self.drag_source_set_target_list(None)

        # drag and drop: the StepWidget as a drag destination
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_set_target_list(None)

        self.drag_dest_add_text_targets()
        self.drag_source_add_text_targets()

        self.connect('drag-data-received', self.on_drag_data_received)
        self.connect('drag-motion', self.on_drag_motion)
        self.connect('drag-leave', self.on_drag_leave)
        self.connect('drag-begin', self.on_drag_begin)
        self.connect('drag-data-get', self.on_drag_data_get)
        self.connect('drag-drop', self.on_drag_drop)

        # right click menu (context menu)
        self.menu = StepRightClickMenu(step_widget=self)

        self.connect('button-press-event', self.on_button_press)

        # connect the signals
        self.desc_text_buffer.connect('changed', self.on_description_buffer_changed)
        self.commands_buffer.connect('changed', self.on_commands_buffer_changed)
        self.step_comment_buffer.connect('changed', self.on_step_comment_buffer_changed)
        self.verification_buffer.connect('changed', self.on_verification_buffer_changed)
        self.verification_description_buffer.connect('changed', self.on_verification_description_buffer_changed)

        Gtk.StyleContext.add_class(self.get_style_context(), 'step-widget')

    @property
    def step_detail_visible(self):
        return self._step_detail_visible

    @step_detail_visible.setter
    def step_detail_visible(self, value: bool):
        assert isinstance(value, bool)
        self._step_detail_visible = value
        # set the visibility status of the widget
        self.detail_box.set_visible(self.step_detail_visible)
        if self.step_detail_visible is True:
            self.btn_toggle_detail.set_icon_name('pan-down-symbolic')
        else:
            self.btn_toggle_detail.set_icon_name('pan-end-symbolic')

    @property
    def step_number(self):
        return self._step_number

    @step_number.setter
    def step_number(self, value: str):
        """ If the attribute step_description is set, other actions are triggered."""
        assert isinstance(value, (str, int, float))
        stp_nmbr_pri, stp_nmbr_sec = data_model.parse_step_number(value)
        stp_nmbr = data_model.create_step_number(stp_nmbr_pri, stp_nmbr_sec)
        self._step_number = stp_nmbr
        # set the text in the step number label
        self.label_step_number.set_text('{} {}: '.format(_('Step'), str(self.step_number)))

    @property
    def start_sequence(self):
        return self._start_sequence

    @start_sequence.setter
    def start_sequence(self, value: int):
        assert isinstance(value, int) or value is None
        self._start_sequence = value

    @property
    def stop_sequence(self):
        return self._stop_sequence

    @stop_sequence.setter
    def stop_sequence(self, value: int):
        assert isinstance(value, int) or value is None
        self._stop_sequence = value

    @property
    def step_description(self):
        return self._step_description

    @step_description.setter
    def step_description(self, value: str):
        """ If the attribute step_description is set, other actions are triggered."""
        assert isinstance(value, str)
        self._step_description = value
        # Setting the description for a step in the data model
        # find the correct step within the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_in_data_model = self.model.get_sequence(self.sequence).steps[stp_ndx]
        # use the setter of the data model
        if isinstance(step_in_data_model, data_model.Step):
            step_in_data_model.description = self.step_description
        else:
            self.logger('step with the step number {} could not be found'.format(self.step_number))
        # set the short description attribute
        self.short_description = self.step_description

    @property
    def short_description(self):
        return self._short_description

    @short_description.setter
    def short_description(self, value: str):
        """ Creates the short description of the step out of the description. Sets the text in the StepWidget toolbar
        label
        """
        assert isinstance(value, str)
        len_short_desc = 42
        if len(value) > len_short_desc:
            short_d = value[0:len_short_desc] + '...'
        else:
            short_d = value
        self._short_description = short_d
        # update the text of the label
        self.text_label.set_text(self.short_description)
        self.text_label.set_tooltip_text(self.step_description)

    def set_data_in_widget(self):
        self.set_is_active_in_widget()
        self.set_description_in_widget()
        self.set_commands_in_widget()
        self.set_step_comment_in_widget()
        self.set_verification_in_widget()
        self.set_verification_description_in_widget()
        self.set_start_sequence_in_widget()
        self.set_stop_sequence_in_widget()
        return

    def set_is_active_in_widget(self):
        """ Toggles the checkbox"""
        # Change the active state of a step in the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        state = self.model.get_sequence(self.sequence).steps[stp_ndx].is_active
        self.is_active.set_active(state)
        return

    def set_description_in_widget(self):
        """
        copy the description of the step from the model to the text view buffer and make a short description for
        the StepWidget toolbar
        """
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        desc = self.model.get_sequence(self.sequence).steps[stp_ndx].description
        self.desc_text_buffer.set_text(desc)
        self.step_description = desc
        return

    def set_commands_in_widget(self):
        """ gets the commands from the model and sets it in the commands buffer in order to display it """
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        commands = self.model.get_sequence(self.sequence).steps[stp_ndx].command_code
        self.commands_buffer.set_text(commands)
        return

    def set_step_comment_in_widget(self):
        """ gets the commands comment from the model and sets it in the commands comment buffer in order to display it """
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_comment = self.model.get_sequence(self.sequence).steps[stp_ndx].step_comment
        self.step_comment_buffer.set_text(step_comment)
        return

    def set_verification_in_widget(self):
        """ gets the commands from the model and sets it in the commands buffer in order to display it """
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        verification = self.model.get_sequence(self.sequence).steps[stp_ndx].verification_code
        self.verification_buffer.set_text(verification)
        return

    def set_verification_description_in_widget(self):
        """ gets the commands comment from the model and sets it in the commands comment buffer in order to display it """
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        verification_description = self.model.get_sequence(self.sequence).steps[stp_ndx].verification_description
        self.verification_description_buffer.set_text(verification_description)
        return

    def set_start_sequence_in_widget(self):
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step = self.model.get_sequence(self.sequence).steps[stp_ndx]
        if hasattr(step, 'start_sequence'):
            self.start_sequence = step.start_sequence
        return

    def set_stop_sequence_in_widget(self):
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step = self.model.get_sequence(self.sequence).steps[stp_ndx]
        if hasattr(step, 'stop_sequence'):
            self.stop_sequence = step.stop_sequence
        return

    @staticmethod
    def read_out_text_buffer(buffer: Gtk.TextBuffer):
        """
        Reads out the text buffer
        :rtype: str
        """
        assert isinstance(buffer, Gtk.TextBuffer)
        content = buffer.get_text(start=buffer.get_start_iter(),
                                  end=buffer.get_end_iter(),
                                  include_hidden_chars=True)
        return content

    def get_commands_from_widget(self):
        """
        Reads out the source buffer of the commands
        :return: The code of the commands of the step
        :rtype: str
        """
        commands_buffer = self.commands_buffer
        content = commands_buffer.get_text(start=commands_buffer.get_start_iter(),
                                           end=commands_buffer.get_end_iter(),
                                           include_hidden_chars=True)
        return content

    def get_verification_from_widget(self):
        """
        Reads out the source buffer for the verification
        :return: The code of the verification of the step
        :rtype: str
        """
        verification_buffer = self.verification_buffer
        content = verification_buffer.get_text(start=verification_buffer.get_start_iter(),
                                               end=verification_buffer.get_end_iter(),
                                               include_hidden_chars=True)
        return content

    def get_active_state_from_widget(self):
        """
        Get the current status of the checkbox if a step is active.
        :return: state of the toggle button
        :rtype: bool
        """
        return self.is_active.get_active()

    def on_drag_begin(self, widget, drag_context):
        pass

    def on_drag_data_get(self, widget, drag_context, data, info, time):
        """
        Collect data about the step that is dragged. Set it as the selection-data in order to transfer it to the receiving widget.
        """
        step_index = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step = self.model.get_sequence(self.sequence).steps[step_index]
        assert isinstance(step, data_model.Step)
        step_number = step.step_number
        description = step.description
        comment = step.step_comment
        command_code = step.command_code
        verification_code = step.verification_code
        verification_descr = step.verification_description
        data_type = dnd_data_parser.data_type_step if (verification_descr or verification_code) else dnd_data_parser.data_type_snippet
        data_string = dnd_data_parser.create_datastring(data_type,
                                                        self.sequence,
                                                        step_number,
                                                        description,
                                                        comment,
                                                        command_code,
                                                        verification_code,
                                                        verification_descr,
                                                        logger=self.logger)
        # set the text in the selection data object
        data.set_text(data_string, -1)

    def on_drag_motion(self, widget, drag_context, x, y, time):
        # get the widget position in the grid, the widget below and above
        grid = self.get_parent()
        left = grid.child_get_property(self, 'left-attach')
        top = grid.child_get_property(self, 'top-attach')
        widget_above = grid.get_child_at(left, top - 1)
        widget_below = grid.get_child_at(left, top + 1)
        # decide if the cursor position is in he upper or lower quarter of the widget
        widget_height = widget.get_allocated_height()
        if y < widget_height * widget_grip_upper:  # upper quarter
            # highlight the widget above
            if widget_above is not None:
                Gtk.StyleContext.add_class(widget_above.get_style_context(), 'highlight')
            if widget_below is not None:
                Gtk.StyleContext.remove_class(widget_below.get_style_context(), 'highlight')
            Gtk.StyleContext.remove_class(widget.get_style_context(), 'highlight')
        elif y > widget_height * widget_grip_lower:  # lower quarter
            # highlight the widget below
            if widget_below is not None:
                Gtk.StyleContext.add_class(widget_below.get_style_context(), 'highlight')
            if widget_above is not None:
                Gtk.StyleContext.remove_class(widget_above.get_style_context(), 'highlight')
            Gtk.StyleContext.remove_class(widget.get_style_context(), 'highlight')
        else:
            # highlight the widget itself
            Gtk.StyleContext.add_class(widget.get_style_context(), 'highlight')
            if widget_above is not None:
                Gtk.StyleContext.remove_class(widget_above.get_style_context(), 'highlight')
            if widget_below is not None:
                Gtk.StyleContext.remove_class(widget_below.get_style_context(), 'highlight')
        widget.show_all()

    def on_drag_leave(self, widget, drag_context, time):
        # removing the highlighting which was done in on_drag_motion
        Gtk.StyleContext.remove_class(widget.get_style_context(), 'highlight')
        widget.show_all()

    def on_drag_drop(self, widget, drag_context, x, y, timestamp, *args):
        pass

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data, info, time):
        """
        Depending on the source of the drag operation, the widget shows different behavior.
        If the drag source was another step widget the order of the steps should be changed,
        thus an indicator for inserting above/below is shown.
        If the drag source was and entry in the codereuse-feature, the step should be highlighted, indicating to insert
        a description and code.

        Also the drop position will influence what happens.
        """
        # decide if the cursor position is in he upper or lower quarter of the widget
        widget_height = widget.get_allocated_height()

        # parse the received data
        data_string = selection_data.get_text()
        data = dnd_data_parser.read_datastring(data_string, logger=self.logger)
        drag_source_type = data['data_type']
        #print(drag_source_type)
        if drag_source_type == dnd_data_parser.data_type_snippet:  # data gets copied
            if y < widget_height * widget_grip_upper:  # upper quarter
                # add a step above
                step = self.model.get_sequence(self.sequence).add_step_above(reference_step_position=self.step_number)
            elif y > widget_height * widget_grip_lower:  # lower quarter
                # add a step below
                step = self.model.get_sequence(self.sequence).add_step_below(reference_step_position=self.step_number)
            else:
                step = self.model.get_sequence(self.sequence).get_step(self.step_number)
            # set the data into the test script data model
            step.description = data['description']
            step.command_code = data['command_code']
            step.step_comment = data['comment']
            step.verification_code = data['verification_code']
            step.verification_description = data['verification_descr']
        if drag_source_type == dnd_data_parser.data_type_step:  # a step is moved
            step_number = data['step_number']
            dragged_step_idx = self.model.get_sequence(self.sequence).get_step_index(step_number)
            dropped_on_step_idx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
            widget_height = self.get_allocated_height()
            if y < widget_height * widget_grip_upper:
                if dragged_step_idx < dropped_on_step_idx:
                    self.model.get_sequence(self.sequence).move_step(dragged_step_idx, dropped_on_step_idx-1)
                elif dragged_step_idx > dropped_on_step_idx:
                    self.model.get_sequence(self.sequence).move_step(dragged_step_idx, dropped_on_step_idx)
            elif y > widget_height * widget_grip_lower:
                if dragged_step_idx < dropped_on_step_idx:
                    self.model.get_sequence(self.sequence).move_step(dragged_step_idx, dropped_on_step_idx)
                elif dragged_step_idx > dropped_on_step_idx:
                    self.model.get_sequence(self.sequence).move_step(dragged_step_idx, dropped_on_step_idx+1)
        # update the board
        self.board.update_widget_data()
        # update the model view
        self.app.update_model_viewer()

    def on_delete_step(self, button):
        """ Deletes the step from the data model (TestSequence)
        :param button: the button widget
        """
        # deletes the step from the data model (TestSequence)
        self.model.get_sequence(self.sequence).remove_step(self.step_number)
        # update the board
        self.board.update_widget_data()
        # update the model view
        self.app.update_model_viewer()

    def on_toggled_is_active(self, toggled_button):
        """
        Signal if the checkbox of a steps active status was toggled.
        """
        current_state = self.get_active_state_from_widget()
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        self.model.get_sequence(self.sequence).steps[stp_ndx].is_active = current_state
        self.app.update_model_viewer()

    def on_description_buffer_changed(self, text_buffer):
        """
        Signal 'changed' for the description text buffer. For example the user typed.
        """
        # get the description out of the text buffer of the widget
        # description = self.get_description_from_widget()
        self.step_description = self.read_out_text_buffer(text_buffer)
        # Setting the description string for a step in the data model
        # find the correct step within the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_in_data_model = self.model.get_sequence(self.sequence).steps[stp_ndx]
        # use the setter of the data model
        if isinstance(step_in_data_model, data_model.Step):
            step_in_data_model.description = self.step_description
        else:
            self.logger('step with the step number {} could not be found'.format(self.step_number))
        # update the model
        # ToDo
        # update the data model viewer
        self.app.update_model_viewer()
        # update short desc
        # self.update_short_description()

    def on_commands_buffer_changed(self, text_buffer):
        """
        Signal 'changed' for the commands source buffer
        """
        # get the code of the commands out of the buffer of the widget
        commands = self.get_commands_from_widget()
        # Setting the commands string for a step in the data model
        # find the correct step within the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_in_data_model = self.model.get_sequence(self.sequence).steps[stp_ndx]
        # use the setter of the data model
        if isinstance(step_in_data_model, data_model.Step):
            step_in_data_model.command_code = commands
        else:
            self.logger('step with the step number {} could not be found'.format(self.step_number))
        # update the data model viewer
        self.app.update_model_viewer()

    def on_step_comment_buffer_changed(self, text_buffer):
        """
        Signal 'changed' for the commands comment buffer
        """
        # get the text of the commands comment out of the buffer of the widget
        step_comment = self.read_out_text_buffer(text_buffer)
        # Setting the commands string for a step in the data model
        # find the correct step within the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_in_data_model = self.model.get_sequence(self.sequence).steps[stp_ndx]
        # use the setter of the data model
        if isinstance(step_in_data_model, data_model.Step):
            step_in_data_model.step_comment = step_comment
        else:
            self.logger('step with the step number {} could not be found'.format(self.step_number))
        # update the data model viewer
        self.app.update_model_viewer()

    def on_verification_buffer_changed(self, text_buffer):
        """
        Signal 'changed' for the verification source buffer
        """
        # get the code of the verification out of the buffer of the widget
        verification = self.get_verification_from_widget()
        # Setting the verification string for a step in the data model
        # find the correct step within the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_in_data_model = self.model.get_sequence(self.sequence).steps[stp_ndx]
        # use the setter of the data model
        if isinstance(step_in_data_model, data_model.Step):
            step_in_data_model.verification_code = verification
        else:
            self.logger('step with the step number {} could not be found'.format(self.step_number))
        # update the data model viewer
        self.app.update_model_viewer()

    def on_verification_description_buffer_changed(self, text_buffer):
        """
        Signal 'changed' for the verification description buffer
        """
        # get the code of the verification out of the buffer of the widget
        verification_description = self.read_out_text_buffer(text_buffer)
        # Setting the verification string for a step in the data model
        # find the correct step within the data model
        stp_ndx = self.model.get_sequence(self.sequence).get_step_index(self.step_number)
        step_in_data_model = self.model.get_sequence(self.sequence).steps[stp_ndx]
        # use the setter of the data model
        if isinstance(step_in_data_model, data_model.Step):
            step_in_data_model.verification_description = verification_description
        else:
            self.logger('step with the step number {} could not be found'.format(self.step_number))
        # update the data model viewer
        self.app.update_model_viewer()

    def on_exec_commands(self, button):
        # get the code of the commands out of the buffer of the widget
        commands = str(self.get_commands_from_widget())
        #Check if CCS is open
        if not cfl.is_open('editor'):
            print('CCS-Editor has to be started first')
            logger.info('CCS-Editor has to be running if a step should be executed')
            return

        # Connect to the editor and send the commands to the terminal via D-Bus
        ed = cfl.dbus_connection('editor')
        cfl.Functions(ed, '_to_console_via_socket', commands)
        #import editor
        #x = editor.CcsEditor()
        #x._to_console_via_socket(commands)

    def on_exec_verification(self, button):
        # get the code of the commands out of the buffer of the widget
        verification = self.get_verification_from_widget()
        #ack = misc.to_console_via_socket(verification)
        #print(ack)

    def on_execute_step(self, *args):
        if not cfl.is_open('editor'):
            print('CCS-Editor has to be started first')
            logger.info('CCS-Editor has to be running if a step should be executed')
            return

        commands = str(self.get_commands_from_widget())

        if len(commands) == 0:
            return

        ed = cfl.dbus_connection('editor')
        cfl.Functions(ed, '_to_console_via_socket', commands)

    def on_toggle_detail(self, toolbutton, *args):
        """
        The button to show/hide the step details was clicked.
        The visible status of the detail area is inverted and the button icon is changed.

        :param Gtk.ToolButton toolbutton: the button widget which was clicked
        """
        self.step_detail_visible = not self.detail_box.is_visible()
        # if showing the detail view, set the cursor into the description field
        if self.step_detail_visible is True:
            self.do_grab_focus(self.desc_text_view)
        return False

    def on_detail_box_show(self, *args):
        self.step_detail_visible = self.step_detail_visible

    def on_button_press(self, widget, event, *args):
        if event.button == 3:  # right mouse button clicked
            # show the right-click context menu
            widget.menu.popup_at_pointer()


class InterStepWidget(Gtk.Box):
    """
    This widget is used to be put between two steps.
    It is used to highlight if a step is dragged over it and draw an arrow between two steps.
    """
    def __init__(self, model, seq_num, app, board, logger=logger):
        super().__init__()
        Gtk.StyleContext.add_class(self.get_style_context(), 'inter-step-widget')

        self.model = model
        self.app = app
        self.board = board
        self.logger = logger
        self.sequence = seq_num

        # add the drawing area for the arrow
        self.drawingarea = Gtk.DrawingArea()
        self.drawingarea_height = 16
        self.hovered_over = False
        self.drawingarea.set_size_request(10, self.drawingarea_height)
        self.pack_start(self.drawingarea, True, True, 0)
        self.drawingarea.connect('draw', self.draw)
        # self.drawingarea.connect('realize', self.realize)
        # self.drawingarea.connect('size-allocate', self.size_allocate)

        # drag and drop: make this widget a drag destination
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_set_target_list(None)

        self.drag_dest_add_text_targets()

        self.connect('drag-data-received', self.on_drag_data_received)
        self.connect('drag-motion', self.on_drag_motion)
        self.connect('drag-leave', self.on_drag_leave)
        self.connect('drag-drop', self.on_drag_drop)

    # def draw_arrow(self, ctx, x, y, size):
    #     """
    #     Uses cairo context functions to draw the arrow.
    #     """
    #     ctx.save()
    #     ctx.new_path()
    #
    #     # draw the arrow (construction of the path)
    #     ctx.move_to(x, y)
    #     ctx.rel_line_to(0, 1/3*size)
    #     ctx.rel_line_to(-1/3*size, 0)
    #     ctx.rel_line_to(1/3*size, 2/3*size)
    #     ctx.rel_line_to(1/3*size, -2/3*size)
    #     ctx.rel_line_to(-1/3*size, 0)
    #     ctx.close_path()
    #
    #     # draw the path and fill it
    #     ctx.stroke_preserve()
    #     ctx.fill()
    #     ctx.restore()
    #     return

    def draw_arrow_head(self, ctx, x, y, size):
        """
        Uses cairo context functions to draw the arrow.
        """
        ctx.save()
        ctx.new_path()

        # draw the arrow (construction of the path)
        ctx.move_to(x, y+size)
        ctx.rel_line_to(-1/2*size, -size)
        ctx.rel_line_to(1*size, 0)
        ctx.rel_line_to(-1/2*size, size)
        ctx.close_path()

        # draw the path and fill it
        ctx.stroke_preserve()
        ctx.fill()
        ctx.restore()
        return

    def draw_insert_here_arrows(self, ctx, x, y, size):
        """
        Uses cairo context functions to draw the arrow.
        """
        ctx.save()
        ctx.new_path()
        size = size/2
        # draw the arrow (construction of the path)
        ctx.move_to(x, y+size)
        ctx.rel_line_to(-1/2*size, -size)
        ctx.rel_line_to(1*size, 0)
        ctx.rel_line_to(-1/2*size, size)
        ctx.move_to(0, y+size)
        ctx.rel_line_to(2*x, 0)
        ctx.move_to(x, y+size)
        ctx.rel_line_to(-1/2*size, size)
        ctx.rel_line_to(1*size, 0)
        ctx.rel_line_to(-1/2*size, -1*size)

        ctx.close_path()

        # draw the path and fill it
        ctx.stroke_preserve()
        ctx.fill()
        ctx.restore()
        return

    # def realize(self, *args):
    #     pass
    #
    # def size_allocate(self, *args):
    #     """
    #     Resize the drawing area: figure out the height of a step widget, with no details shown (for the length of the
    #     arrow) and resize the drawing area.
    #     """
    #     for child in self.board.grid.get_children():
    #         if isinstance(child, StepWidget):
    #             if not child.step_detail_visible:
    #                 # height = child.get_allocated_height()
    #                 # width = child.get_allocated_width()
    #                 natural_height = child.get_preferred_height()[1]
    #                 natural_width = child.get_preferred_width()[1]
    #     width = self.get_allocated_width()
    #     # self.drawingarea.set_size_request(width, natural_height)
    #     self.drawingarea.set_size_request(10, 10)

    def draw(self, da, ctx, *args):
        """
        Draws an arrow if:

            * a step is below this interstep-widget (vertical arrows)
            * another sequence is started (horizontal arrows)

        The arrows are drawn:
        starting point is the half width of the widget, because in the grid all are the same width
        The length of the arrow is determined by the height of a step widget with no details shown.
        """
        width = self.get_allocated_width()

        # for child in self.board.grid.get_children():
        #     if isinstance(child, InterStepWidget):
        #         print('{}, {}'.format(self.board.grid.child_get_property(child, 'left-attach'),
        #                               self.board.grid.child_get_property(child, 'top-attach')))
        # print('*****')

        # figure out the height of a step widget, with do details shown (for the length of the arrow)
        for child in self.board.grid.get_children():
            if isinstance(child, StepWidget):
                if not child.step_detail_visible:
                    # height = child.get_allocated_height()
                    height = child.get_preferred_height()[1]

        # figure out the top-attach of this widget
        for child in self.board.grid.get_children():
            if child is self:
                self.top_attach = self.board.grid.child_get_property(child, 'top-attach')
                self.left_attach = self.board.grid.child_get_property(child, 'left-attach')
        # figure out, if there comes another step after this InterStep widget
        another_step_follows = False
        for child in self.board.grid.get_children():
            if isinstance(child, StepWidget):
                child_top_attach = self.board.grid.child_get_property(child, 'top-attach')
                child_left_attach = self.board.grid.child_get_property(child, 'left-attach')
                if child_left_attach == self.left_attach:  # only widgets in the same column are considered
                    if child_top_attach > self.top_attach:
                        another_step_follows = True
        # figure out, if there is another step in front this InterStep widget
        another_step_in_front = False
        for child in self.board.grid.get_children():
            if isinstance(child, StepWidget):
                child_top_attach = self.board.grid.child_get_property(child, 'top-attach')
                child_left_attach = self.board.grid.child_get_property(child, 'left-attach')
                if child_left_attach == self.left_attach:  # only widgets in the same column are considered
                    if child_top_attach < self.top_attach:
                        another_step_in_front = True

        # draw the arrow if another step follows
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(self.drawingarea_height / 10)
        ctx.set_tolerance(0.1)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)

        if self.hovered_over:
            self.draw_insert_here_arrows(ctx, width/2, 0, self.drawingarea_height)
        else:
            if another_step_follows:
                self.draw_arrow_head(ctx, width/2, 0, self.drawingarea_height)
        return

    def on_drag_motion(self, widget, drag_context, x, y, time):
        self.hovered_over = True
        self.drawingarea.queue_draw()
        Gtk.StyleContext.add_class(widget.get_style_context(), 'highlight-2')
        widget.show_all()

    def on_drag_leave(self, widget, drag_context, time):
        self.hovered_over = False
        # removing the highlighting which was done in on_drag_motion
        Gtk.StyleContext.remove_class(widget.get_style_context(), 'highlight-2')
        widget.show_all()

    def on_drag_drop(self, widget, drag_context, x, y, timestamp, *args):
        pass

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data, info, time):
        self.hovered_over = False
        # figure out what was the source of the drag operation
        data_string = selection_data.get_text()
        data = dnd_data_parser.read_datastring(data_string, logger=self.logger)
        drag_source_type = data['data_type']
        # get the widget above
        grid = self.get_parent()
        left = grid.child_get_property(self, 'left-attach')
        top = grid.child_get_property(self, 'top-attach')
        widget_above = grid.get_child_at(left, top - 1)
        # create a new step and fill it with data
        if drag_source_type == dnd_data_parser.data_type_snippet:
            # add a step below the position of the widget above
            if isinstance(widget_above, StepWidget):
                dest_step_above_number = widget_above.step_number
                new_step = self.model.get_sequence(self.sequence).add_step_below(reference_step_position=dest_step_above_number)
                # set the data into the test script data model
                new_step.description = data['description']
                new_step.step_comment = data['comment']
                new_step.command_code = data['command_code']
                new_step.verification_code = data['verification_code']
                new_step.verification_description = data['verification_descr']
        if drag_source_type == dnd_data_parser.data_type_step:  # a step is moved
            source_sequence = int(data['sequence'])
            source_step_number = data['step_number']
            source_step_idx = self.model.get_sequence(source_sequence).get_step_index(source_step_number)
            if isinstance(widget_above, StepWidget):
                dest_step_above_number = widget_above.step_number
                dest_step_above_sequence = widget_above.sequence
                dest_step_above_idx = self.model.get_sequence(dest_step_above_sequence).get_step_index(dest_step_above_number)
                if source_sequence == dest_step_above_sequence:  # moving the step within the same sequence
                    if source_step_idx < dest_step_above_idx:
                        self.model.get_sequence(dest_step_above_sequence).move_step(source_step_idx, dest_step_above_idx)
                    elif source_step_idx > dest_step_above_idx:
                        self.model.get_sequence(dest_step_above_sequence).move_step(source_step_idx, dest_step_above_idx+1)
                else:
                    # the step is moved to another sequence:
                    # add the step within the new sequence and remove it from the old sequence
                    seq = self.model.get_sequence(dest_step_above_sequence)
                    new_step = self.model.get_sequence(dest_step_above_sequence).add_step_below(reference_step_position=dest_step_above_number)
                    # set the data into the test script data model
                    new_step.description = data['description']
                    new_step.step_comment = data['comment']
                    new_step.command_code = data['command_code']
                    new_step.verification_code = data['verification_code']
                    new_step.verification_description = data['verification_descr']
                    # ToDo
                    # remove it from the old sequence
                    dragged_from_seq = self.model.get_sequence(source_sequence)
                    dragged_from_seq.remove_step(step_number=source_step_number)

        # update the board
        self.board.update_widget_data()
        # update the model view
        self.app.update_model_viewer()


class StepRightClickMenu(Gtk.Menu):
    def __init__(self, step_widget):
        super().__init__()
        self.step_widget = step_widget

        entry_1 = Gtk.MenuItem('Insert step above')
        self.attach(entry_1, 0, 1, 0, 1)
        entry_1.show()
        entry_1.connect('activate', self.on_insert_step_above, self.step_widget)

        entry_2 = Gtk.MenuItem('Insert step below')
        self.attach(entry_2, 0, 1, 1, 2)
        entry_2.show()
        entry_2.connect('activate', self.on_insert_step_below, self.step_widget)

    def on_insert_step_above(self, menu_item, step_widget, *args):
        step_clicked_on = step_widget.step_number
        step_widget.model.get_sequence(step_widget.sequence).add_step_above(reference_step_position=step_clicked_on)
        self.step_widget.board.update_widget_data()

    def on_insert_step_below(self, menu_item, step_widget, *args):
        step_clicked_on = step_widget.step_number
        step_widget.model.get_sequence(step_widget.sequence).add_step_below(reference_step_position=step_clicked_on)
        self.step_widget.board.update_widget_data()


class Edit_Pre_Post_Con_Dialog(Gtk.Dialog):
    def __init__(self, parent, pre_post, selection):
        #Gtk.Dialog.__init__(self, title='PRE-Conditions', transient_for=parent, flags=0)
        Gtk.Dialog.__init__(self, title=pre_post.upper() + ' -Conditions')
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        self.set_default_size(400, 400)
        self.first_entry = selection
        self.win = parent
        self.file_path = os.path.join(confignator.get_option('paths', 'tst'),
                                      'tst/generator_templates/co_'+pre_post+'_condition_entry.py')
        self.pre_post = pre_post

        self.make_section_dict()

        self.view()

        self.show_all()

    def make_section_dict(self):
        if self.pre_post == 'pre':
            self.section_dict = db_interaction.get_pre_post_con('pre')
        else:
            self.section_dict = db_interaction.get_pre_post_con('post')

    def view(self):
        self.main_box = Gtk.Box()
        self.main_box.set_orientation(Gtk.Orientation.VERTICAL)

        self.selection_box = Gtk.Box()
        self.selection_box.set_orientation(Gtk.Orientation.HORIZONTAL)

        self.make_description_viewer()
        self.make_text_viewer()

        self.selection = Gtk.ComboBoxText.new_with_entry()
        self.make_con_sections_model()
        self.selection.connect("changed", self.on_name_combo_changed)
        self.selection.set_entry_text_column(0)
        self.selection.set_active(self.first_entry)

        self.save_button = Gtk.Button.new_with_label('Save')
        self.save_button.connect("clicked", self.on_save_button)

        self.delete_button = Gtk.Button.new_with_label('Delete')
        self.delete_button.connect("clicked", self.on_delete_button)

        self.selection_box.pack_start(self.selection, False, True, 0)
        self.selection_box.pack_start(self.save_button, False, True, 0)
        self.selection_box.pack_start(self.delete_button, False, True, 0)

        box = self.get_content_area()
        box.pack_start(self.selection_box, False, True, 0)
        box.pack_start(self.descr_lbl_box, False, False, 0)
        box.pack_start(self.descr_scrolled_window, False, False, 0)
        box.pack_start(self.con_lbl_box, False, False, 0)
        box.pack_start(self.con_scrolled_window, True, True, 0)
        #box.add(self.selection_box)
        #box.pack_end(self.scrolled_window, True, True, 0)

    def make_con_sections_model(self):
        for condition in self.section_dict:
            self.selection.append_text(condition.name)
        return

    def on_name_combo_changed(self, widget):
        name = widget.get_active_text()

        if name:
            for condition in self.section_dict:
                if condition.name == name:
                    self.descr_textview.get_buffer().set_text(condition.description)
                    self.con_buffer.set_text(condition.condition)
        else:
            self.descr_textview.get_buffer().set_text('')
            self.con_buffer.set_text('')

        return

    def on_save_button(self, widget):
        descr_buffer = self.descr_textview.get_buffer()
        name = self.selection.get_active_text()

        if not name:
            return

        descr = descr_buffer.get_text(descr_buffer.get_start_iter(), descr_buffer.get_end_iter(), True)
        condition = self.con_buffer.get_text(self.con_buffer.get_start_iter(), self.con_buffer.get_end_iter(), True)
        db_interaction.write_into_pre_post_con(code_type=self.pre_post, name=name, description=descr, code_block=condition)

        time.sleep(0.1)  # Sleep shorty so the condition can be written to the database
        # Refresh the combo box entries
        self.make_section_dict()
        self.selection.remove_all()
        self.make_con_sections_model()
        return

    def on_delete_button(self, widget):
        name = self.selection.get_active_text()

        for con in self.section_dict:
            if con.name == name:
                db_interaction.delete_db_row_pre_post(con.id)

        time.sleep(0.1)  # Sleep shorty so the condition can be deleted from the database
        # Refresh the combo box entries
        self.make_section_dict()
        self.selection.remove_all()
        self.make_con_sections_model()
        self.selection.set_active(0)
        return

    def make_description_viewer(self):
        # Label in a Box to have it on the left boarder
        self.descr_lbl_box = Gtk.HBox()
        descr_lbl = Gtk.Label()
        descr_lbl.set_text('Description: ')
        self.descr_lbl_box.pack_start(descr_lbl, False, False, 0)

        # a scrollbar for the child widget (that is going to be the textview)
        self.descr_scrolled_window = Gtk.ScrolledWindow()
        self.descr_scrolled_window.set_border_width(5)
        # we scroll only if needed
        self.descr_scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # a text buffer (stores text)
        buffer = Gtk.TextBuffer()

        # a textview (displays the buffer)
        self.descr_textview = Gtk.TextView(buffer=buffer)
        # wrap the text, if needed, breaking lines in between words
        self.descr_textview.set_wrap_mode(Gtk.WrapMode.WORD)

        # textview is scrolled
        self.descr_scrolled_window.add(self.descr_textview)

    def make_text_viewer(self):
        # Label in a Box to have it on the left boarder
        self.con_lbl_box = Gtk.HBox()
        con_lbl = Gtk.Label()
        con_lbl.set_text('Condition: ')
        self.con_lbl_box.pack_start(con_lbl, False, False, 0)

        self.con_scrolled_window = Gtk.ScrolledWindow()
        self.con_scrolled_window.set_tooltip_text('Set variable "success" to True/False, to check if {}-Conditon is fulfilled'.format(self.pre_post.upper()))
        #self.commands_scrolled_window.set_size_request(50, 100)
        self.con_view = GtkSource.View()
        self.con_view.set_auto_indent(True)
        self.con_view.set_show_line_numbers(False)
        # self.commands_view.set_show_right_margin(True)
        self.con_view.set_highlight_current_line(True)
        self.con_view.set_indent_on_tab(True)
        self.con_view.set_insert_spaces_instead_of_tabs(True)
        self.con_buffer = self.con_view.get_buffer()
        self.con_buffer.set_language(lngg)
        # self.commands_buffer.set_style_scheme(self.board.current_scheme)
        self.con_scrolled_window.add(self.con_view)

        #box = self.get_content_area()
        #box.add(self.selection_box)

        return




