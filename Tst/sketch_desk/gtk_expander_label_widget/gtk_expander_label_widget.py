import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class StepExpanderLabelToolbar(Gtk.EventBox):
    def __init__(self, stepwidget, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.vbox = Gtk.Box()
        self.vbox.set_orientation(Gtk.Orientation.HORIZONTAL)

        self.stepwidget = stepwidget

        # toolbar
        self.set_above_child(True)
        self.set_visible_window(True)

        self.is_active = Gtk.CheckButton()
        self.is_active.set_active(True)
        self.is_active.connect('clicked', self.on_toggled_is_active)

        # self.btn_execute_step = Gtk.Button()
        # self.btn_execute_step.new_from_icon_name('media-playback-start-symbolic', Gtk.IconSize.BUTTON)
        # self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.btn_execute_step = Gtk.ToolButton()
        self.btn_execute_step.set_icon_name('media-playback-start-symbolic')
        self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.text_label = Gtk.Label()
        self.set_label_text()

        self.btn_delete_step = Gtk.ToolButton()
        self.btn_delete_step.set_icon_name('edit-delete-symbolic')
        self.btn_delete_step.connect('clicked', self.on_delete_step)

        self.vbox.pack_start(self.is_active, True, True, 0)
        self.vbox.pack_start(self.btn_execute_step, True, True, 0)
        self.vbox.pack_start(self.text_label, True, True, 0)
        self.vbox.pack_start(self.btn_delete_step, True, True, 0)

        self.add(self.vbox)

    def set_label_text(self):
        text = 'Label widget as Class'
        self.text_label.set_text(text)

    def on_toggled_is_active(self, *args):
        print('on_toggled_is_active')

    def on_execute_step(self, *args):
        print('on_execute_step')

    def on_delete_step(self, *args):
        print('on_delete_step')


class StepExpander(Gtk.Box):
    def __init__(self, stepwidget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_orientation(Gtk.Orientation.VERTICAL)

        # toolbar
        self.tbox = Gtk.Box()
        self.tbox.set_orientation(Gtk.Orientation.HORIZONTAL)
        self.stepwidget = stepwidget

        self.btn_toggle_detail = Gtk.ToolButton()
        self.btn_toggle_detail.set_icon_name('pan-end-symbolic')
        self.btn_toggle_detail.connect('clicked', self.on_toggle_detail)

        self.is_active = Gtk.CheckButton()
        self.is_active.set_active(True)
        self.is_active.connect('clicked', self.on_toggled_is_active)

        # self.btn_execute_step = Gtk.Button()
        # self.btn_execute_step.new_from_icon_name('media-playback-start-symbolic', Gtk.IconSize.BUTTON)
        # self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.btn_execute_step = Gtk.ToolButton()
        self.btn_execute_step.set_icon_name('media-playback-start-symbolic')
        self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.text_label = Gtk.Label()
        self.set_label_text()

        self.btn_delete_step = Gtk.ToolButton()
        self.btn_delete_step.set_icon_name('edit-delete-symbolic')
        self.btn_delete_step.connect('clicked', self.on_delete_step)

        self.tbox.pack_start(self.btn_toggle_detail, True, True, 0)
        self.tbox.pack_start(self.is_active, True, True, 0)
        self.tbox.pack_start(self.btn_execute_step, True, True, 0)
        self.tbox.pack_start(self.text_label, True, True, 0)
        self.tbox.pack_start(self.btn_delete_step, True, True, 0)

        self.pack_start(self.tbox, True, True, 0)

        # detail area
        self.detail_box = Gtk.Box()
        self.detail_box.set_orientation(Gtk.Orientation.HORIZONTAL)

        self.detail_label = Gtk.Label()
        self.detail_label.set_text('DETAILS')

        self.detail_box.pack_start(self.detail_label, True, True, 0)

        self.pack_start(self.detail_box, True, True, 0)

    def set_label_text(self):
        text = 'Label widget as Class'
        self.text_label.set_text(text)

    def on_toggled_is_active(self, *args):
        print('on_toggled_is_active')

    def on_execute_step(self, *args):
        print('on_execute_step')

    def on_delete_step(self, *args):
        print('on_delete_step')

    def on_toggle_detail(self, *args):
        self.detail_box.set_visible(not self.detail_box.is_visible())


class LabelWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="Label Example")

        vbox = Gtk.Box(spacing=10)
        vbox.set_orientation(Gtk.Orientation.VERTICAL)
        vbox.set_homogeneous(False)

        label = Gtk.Label()
        label.set_text('an expander')

        expander = Gtk.Expander()

        # expander.set_label('click to expand')
        # expander_label_widget = StepExpanderLabelToolbar(None)
        # expander_label_widget.connect('button-press-event', self.on_button_pressed)
        # expander.set_label_widget(expander_label_widget)

        self.vbox = Gtk.Box()
        self.vbox.set_orientation(Gtk.Orientation.HORIZONTAL)

        # self.btn_execute_step = Gtk.Button()
        # self.btn_execute_step.new_from_icon_name('media-playback-start-symbolic', Gtk.IconSize.BUTTON)
        # self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.btn_execute_step = Gtk.ToolButton()
        self.btn_execute_step.set_icon_name('media-playback-start-symbolic')
        self.btn_execute_step.connect('clicked', self.on_execute_step)

        self.text_label = Gtk.Label()
        self.text_label.set_text('Label has a text')

        self.vbox.pack_start(self.btn_execute_step, True, True, 0)
        self.vbox.pack_start(self.text_label, True, True, 0)
        expander.set_label_widget(self.vbox)

        text_field = Gtk.Entry()
        expander.add(text_field)

        vbox.pack_start(label, True, True, 0)
        vbox.pack_start(expander, True, True, 0)

        sepp = Gtk.Separator()
        vbox.pack_start(sepp, True, True, 0)

        another_label_widget = StepExpanderLabelToolbar(None)
        another_label_widget.connect('button-press-event', self.on_button_pressed)
        vbox.pack_start(another_label_widget, True, True, 0)

        expander.set_label_widget(another_label_widget)
        expander.set_label_fill(True)

        expander.connect('activate', self.on_expander_activated)

        # do it with Boxes, Boxes, Boxes, .............................................................................
        sepp = Gtk.Separator()
        vbox.pack_start(sepp, True, True, 0)

        work_with_boxes = StepExpander(None)
        vbox.pack_start(work_with_boxes, True, True, 0)

        self.add(vbox)

    def on_expander_activated(self, *args):
        print('on_expander_activated')

    def on_button_pressed(self, *args):
        print('on_button_pressed')

    def on_execute_step(self, *args):
        pass


window = LabelWindow()
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()


