import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '3.0')

from gi.repository import Gtk, Gdk, GtkSource, Pango
import configparser



""" sanity checks missing """
class CreateConfig(Gtk.Dialog):


    def __init__(self, parent = None):
        Gtk.Dialog.__init__(self, parent = parent)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_SAVE, Gtk.ResponseType.OK)

        self.set_border_width(10)
        self.set_default_size(400,600)

        self.set_title("Create New Configuration")

        box = self.get_content_area()
        
        hbox = Gtk.HBox()
        sw = Gtk.ScrolledWindow()
        sw.add(hbox)
        box.pack_start(sw,1,1,0)
        
        self._add_entries(hbox)

        self.show_all()

    def _destroy_window(self, action, widget, id, mask):
        widget.destroy()

    def _add_entries(self, hbox):

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        hbox.pack_start(listbox, True, True, 0)
        
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
        row.add(hbox)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(vbox, True, True, 0)

        label = Gtk.Label()
        label.set_text("Init script")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(vbox, True, True, 0)

        self.init_script = Gtk.Entry()
        self.init_script.set_alignment(1.0)

        vbox.pack_start(self.init_script, True, True, 0)
        listbox.add(row)
        
        listbox.add(Gtk.Separator())
        
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing = 50)
        row.add(hbox)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(vbox, True, True, 0)

        label = Gtk.Label()
        label.set_text("Target IP")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        label = Gtk.Label()
        label.set_text("TM Port")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        label = Gtk.Label()
        label.set_text("TC Port")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(vbox, True, True, 0)

        self.target_ip = Gtk.Entry()
        self.target_ip.set_alignment(0.5)
        self.target_ip.set_max_length(15)

        self.tm_port = Gtk.Entry()
        self.tm_port.set_alignment(1.0)
        self.tm_port.set_max_length(5)

        self.tc_port = Gtk.Entry()
        self.tc_port.set_alignment(1.0)
        self.tc_port.set_max_length(5)

        vbox.pack_start(self.target_ip, True, True, 0)
        vbox.pack_start(self.tm_port, True, True, 0)
        vbox.pack_start(self.tc_port, True, True, 0)

        listbox.add(row)

        listbox.add(Gtk.Separator())


        row = Gtk.ListBoxRow()
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
        row.add(hbox)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(vbox, True, True, 0)

        label = Gtk.Label()
        label.set_text("Database")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        label = Gtk.Label()
        label.set_text("User")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        label = Gtk.Label()
        label.set_text("Password")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)

        label = Gtk.Label()
        label.set_text("Host IP")
        label.set_xalign(0)
        vbox.pack_start(label, True, True, 0)
        
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.pack_start(vbox, True, True, 0)

        self.database = Gtk.Entry()
        self.database.set_alignment(1.0)

        self.user = Gtk.Entry()
        self.user.set_alignment(1.0)

        self.password = Gtk.Entry()
        self.password.set_alignment(1.0)

        self.host_ip = Gtk.Entry()
        self.host_ip.set_alignment(1.0)
        self.host_ip.set_max_length(15)

        vbox.pack_start(self.database, True, True, 0)
        vbox.pack_start(self.user, True, True, 0)
        vbox.pack_start(self.password, True, True, 0)
        vbox.pack_start(self.host_ip, True, True, 0)
        listbox.add(row)
        
        listbox.add(Gtk.Separator())
        
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing = 50)
        row.add(hbox)

        vbox1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        hbox.pack_start(vbox1, True, True, 0)
        hbox.pack_start(vbox2, True, True, 0)

        self.action_dict = {}
        for n in range(10):
            label = Gtk.Label()
            label.set_text("Action {}".format(n+1))
            label.set_xalign(0)
            vbox1.pack_start(label, True, True, 0)
            
            self.action_dict['action_{}'.format(n+1)] = Gtk.Entry()
            self.action_dict['action_{}'.format(n+1)].set_alignment(1.0)
            self.action_dict['action_{}'.format(n+1)].set_placeholder_text('Path to Python script')
            
            vbox2.pack_start(self.action_dict['action_{}'.format(n+1)], True, True, 0)
            
            label = Gtk.Label()
            label.set_text("Action {} Image".format(n+1))
            label.set_xalign(0)
            vbox1.pack_start(label, True, True, 0)
            
            self.action_dict['action_{}_img'.format(n+1)] = Gtk.Entry()
            self.action_dict['action_{}_img'.format(n+1)].set_alignment(1.0)
            self.action_dict['action_{}_img'.format(n+1)].set_placeholder_text('Path to image file')
            
            vbox2.pack_start(self.action_dict['action_{}_img'.format(n+1)], True, True, 0)

        listbox.add(row)
        
    
    def get_config(self):
        cfg = configparser.ConfigParser()

        cfg.add_section('init')
        cfg.set('init', 'init_script', self.init_script.get_text())

        cfg.add_section('pus_connection')
        cfg.set('pus_connection', 'target_ip', self.target_ip.get_text())
        cfg.set('pus_connection', 'tm_port',   self.tm_port.get_text())
        cfg.set('pus_connection', 'tc_port',   self.tc_port.get_text())

        cfg.add_section('database')
        cfg.set('database', 'name',     self.database.get_text())
        cfg.set('database', 'user',     self.user.get_text())
        cfg.set('database', 'password', self.password.get_text())
        cfg.set('database', 'host_ip',  self.host_ip.get_text())

        cfg.add_section('actions')
        for n in range(10):
            cfg.set('actions', 'action{}'.format(n+1), self.action_dict['action_{}'.format(n+1)].get_text())
            cfg.set('actions', 'action{}_img'.format(n+1), self.action_dict['action_{}_img'.format(n+1)].get_text())
        return cfg

