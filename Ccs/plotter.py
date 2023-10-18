import json
import os.path
from packaging import version
import struct
import threading
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import DBus_Basic

import ccs_function_lib as cfl

from typing import NamedTuple
import confignator
import gi
import sys

import matplotlib
matplotlib.use('Gtk3Cairo')

from matplotlib.figure import Figure
# from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar

import numpy as np

from database.tm_db import DbTelemetryPool, DbTelemetry, scoped_session_maker
from sqlalchemy.sql.expression import func
# from sqlalchemy.orm import load_only

import importlib

MPL_VERSION = version.parse(matplotlib._get_version())

cfg = confignator.get_config(check_interpolation=False)

project = 'packet_config_{}'.format(cfg.get('ccs-database', 'project'))
packet_config = importlib.import_module(project)
TM_HEADER_LEN, TC_HEADER_LEN, PEC_LEN = [packet_config.TM_HEADER_LEN, packet_config.TC_HEADER_LEN, packet_config.PEC_LEN]

gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Notify  # NOQA

# from event_storm_squasher import delayed

ActivePoolInfo = NamedTuple(
    'ActivePoolInfo', [
        ('filename', str),
        ('modification_time', int),
        ('pool_name', str),
        ('live', bool)])

# fmtlist = {'INT8': 'b', 'UINT8': 'B', 'INT16': 'h', 'UINT16': 'H', 'INT32': 'i', 'UINT32': 'I', 'INT64': 'q',
#            'UINT64': 'Q', 'FLOAT': 'f', 'DOUBLE': 'd', 'INT24': 'i24', 'UINT24': 'I24', 'bit*': 'bit'}

# pi1_length_in_bits = {8: 'B', 16: 'H'}


class PlotViewer(Gtk.Window):

    def __init__(self, loaded_pool=None, refresh_rate=1, parameters=None, start_live=False, **kwargs):
        Gtk.Window.__init__(self)

        Notify.init('PlotViewer')
        self.set_default_size(900, 560)

        self.set_title('Parameter Viewer')

        self.parameter_limits = set()

        self.data_dict = {}
        self.data_dict_info = {}  # row idx of last data point in data_dict
        self.max_datapoints = 0
        self.data_min_idx = None
        self.data_max_idx = None
        self.pi1_lut = {}

        self._pkt_buffer = {}  # local store for TM packets extracted from SQL DB, for speedup

        self.cfg = confignator.get_config()

        # Set up the logger
        self.logger = cfl.start_logging('ParameterPlotter')

        self.refresh_rate = refresh_rate

        if not self.cfg.has_section(cfl.CFG_SECT_PLOT_PARAMETERS):
            self.cfg.add_section(cfl.CFG_SECT_PLOT_PARAMETERS)
        self.user_parameters = self.cfg[cfl.CFG_SECT_PLOT_PARAMETERS]

        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        # load specified pool
        if loaded_pool is not None and isinstance(loaded_pool, str):
            res = self.session_factory_storage.execute('SELECT * FROM tm_pool WHERE pool_name="{}"'.format(loaded_pool))
            try:
                iid, filename, protocol, modtime = res.fetchall()[0]
                self.loaded_pool = ActivePoolInfo(filename, modtime, filename, bool(not filename.count('/')))
            except IndexError:
                self.logger.error('Could not load pool {}'.format(loaded_pool))
        else:
            self.loaded_pool = None

        box = Gtk.VBox()
        self.add(box)

        hbox = Gtk.HBox()

        self.user_tm_decoders = cfl.user_tm_decoders_func()

        self.canvas = self.create_canvas()
        toolbar = self.create_toolbar()  # self.loaded_pool)

        param_view = self.create_param_view()

        box.pack_start(toolbar, 0, 0, 3)
        box.pack_start(hbox, 1, 1, 0)

        hbox.pack_start(self.canvas, 1, 1, 0)
        hbox.pack_start(param_view, 0, 0, 0)

        navbar = self._create_navbar()
        box.pack_start(navbar, 0, 0, 0)

        # selection = self.treeview.get_selection()

        self.liveplot = self.live_plot_switch.get_active()

        # self.connect('delete-event', self.write_cfg)
        self.connect('delete-event', self.live_plot_off)

        if parameters is None:
            parameters = {}

        self.plot_parameters = parameters
        if len(parameters) != 0:
            for hk in parameters:
                for par in parameters[hk]:
                    self.plot_parameter(parameter=(hk, par))

        self.live_plot_switch.set_active(start_live)
        self.show_all()

        # self.pool_selector.set_active_iter(self.pool_selector_pools.get_iter(0))

    def create_toolbar(self):  #, pool_info=None):
        toolbar = Gtk.HBox()

        # if pool_selector is not None:
        #     pools = Gtk.ListStore(str)
        #     # pools = pool_selector.get_model()
        #     for pool_name in self.loaded_pools:
        #         pools.append(pool_name)
        #     self.pool_box.set_model(pools)
        #     self.pool_box.set_active(pool_selector.get_active())
        # else:
        #     pools = Gtk.ListStore(str)
        #     [pools.append([pool]) for pool in self.pool.keys()]
        #     self.pool_box.set_model(pools)

        self.pool_selector = Gtk.ComboBoxText(tooltip_text='Select Pool to Plot')
        self.pool_selector_pools = Gtk.ListStore(str, int, str, bool)

        if self.loaded_pool is not None and isinstance(self.loaded_pool, ActivePoolInfo):
            self.pool_selector_pools.append([*self.loaded_pool])

        self.pool_selector.set_model(self.pool_selector_pools)
        self.pool_selector.connect('changed', self.pool_changed)

        toolbar.pack_start(self.pool_selector, 0, 0, 0)
        #self.pool_changed(self.pool_selector, 'Select Pool')

        #self.select_pool_button = Gtk.Button.new_with_label("Select Pool")
        #self.select_pool_button.connect("clicked", self.select_pool)
        #toolbar.pack_start(self.select_pool_button, 0, 0, 0)
        #toolbar.pack_start(Gtk.Separator.new(Gtk.Orientation.VERTICAL), 0, 0, 0)

        self.filter_tl2 = Gtk.CheckButton(label='t<2', active=True)
        self.filter_tl2.set_tooltip_text("Plot datapoints with CUC time < 2")
        toolbar.pack_start(self.filter_tl2, 0, 0, 0)

        self.linlog = Gtk.CheckButton(label='logscale')
        self.linlog.set_tooltip_text('Toggle y-axis scale')
        self.linlog.connect("toggled", self.toggle_yscale)
        toolbar.pack_start(self.linlog, 0, 0, 0)

        self.scaley = Gtk.CheckButton(label='Fix Y axis', active=False)
        self.scaley.set_tooltip_text("If enabled, don't rescale Y axis when new parameter is plotted.")
        toolbar.pack_start(self.scaley, 0, 0, 0)

        self.show_legend = Gtk.CheckButton(label='Legend', active=True)
        self.show_legend.set_tooltip_text('Show/hide legend')
        self.show_legend.connect("toggled", self.toggle_legend)
        toolbar.pack_start(self.show_legend, 0, 0, 0)

        self.show_limits = Gtk.CheckButton(label='Limits', active=False)
        self.show_limits.set_tooltip_text('Show/hide parameter limits')
        self.show_limits.connect("toggled", self._toggle_limits)
        toolbar.pack_start(self.show_limits, 0, 0, 0)

        self.calibrate = Gtk.CheckButton(label='Cal', active=True)
        self.calibrate.set_tooltip_text('Plot engineering values, if available')
        # self.calibrate.connect("toggled", self._toggle_limits)
        toolbar.pack_start(self.calibrate, 0, 0, 0)

        toolbar.pack_start(Gtk.Separator.new(Gtk.Orientation.VERTICAL), 0, 0, 0)

        max_data_label = Gtk.Label(label='#')
        max_data_label.set_tooltip_text('Plot at most ~NMAX data points (0 for unlimited), between MIN and MAX packet indices.')
        self.max_data = Gtk.Entry()
        self.max_data.set_width_chars(6)
        self.max_data.set_alignment(1)
        self.max_data.set_placeholder_text('NMAX')
        self.max_data.set_input_purpose(Gtk.InputPurpose.DIGITS)
        # self.max_data.connect('activate', self._set_max_datapoints)
        self.max_data.set_tooltip_text('At most ~NMAX data points plotted (0 for unlimited)')
        toolbar.pack_start(max_data_label, 0, 0, 3)
        toolbar.pack_start(self.max_data, 0, 0, 0)

        self.min_idx = Gtk.Entry()
        self.min_idx.set_width_chars(7)
        self.min_idx.set_alignment(1)
        self.min_idx.set_placeholder_text('MIN')
        self.min_idx.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.min_idx.set_tooltip_text('Get parameters starting from packet index')
        self.max_idx = Gtk.Entry()
        self.max_idx.set_width_chars(7)
        self.max_idx.set_alignment(1)
        self.max_idx.set_placeholder_text('MAX')
        self.max_idx.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.max_idx.set_tooltip_text('Get parameters up to packet index')
        toolbar.pack_start(self.min_idx, 0, 0, 0)
        toolbar.pack_start(self.max_idx, 0, 0, 0)

        toolbar.pack_start(Gtk.Separator.new(Gtk.Orientation.VERTICAL), 0, 0, 0)

        self.live_plot_switch = Gtk.Switch()
        self.live_plot_switch.set_tooltip_text('Toggle real time parameter plotting')
        self.live_plot_switch.connect("state-set", self.on_switch_liveplot)
        live_plot_label = Gtk.Label(label='Live plot:')

        live_plot = Gtk.HBox()
        live_plot.pack_start(live_plot_label, 0, 0, 5)
        live_plot.pack_start(self.live_plot_switch, 0, 0, 0)

        univie_box = self.create_univie_box()

        toolbar.pack_end(univie_box, 0, 0, 0)
        toolbar.pack_end(live_plot, 0, 0, 0)

        return toolbar

    def create_canvas(self):
        fig = Figure()
        self.subplot = fig.add_subplot(111)
        self.subplot.grid()
        self.subplot.set_xlabel('CUC Time [s]')
        self.subplot.callbacks.connect('xlim_changed', self._update_plot_xlimit_values)
        self.subplot.callbacks.connect('ylim_changed', self._update_plot_ylimit_values)

        canvas = FigureCanvas(fig)
        canvas.set_size_request(500, 500)

        return canvas

    def _create_navbar(self):
        # window argument to be removed
        if MPL_VERSION < version.parse('3.6.0'):
            navbar = NavigationToolbar(self.canvas, self)
        else:
            navbar = NavigationToolbar(self.canvas)

        limits = Gtk.HBox()
        self.xmin = Gtk.Entry()
        self.xmin.set_width_chars(9)
        self.xmin.connect('activate', self.set_plot_limits)
        xmin_label = Gtk.Label(label='xmin:')
        self.xmax = Gtk.Entry()
        self.xmax.set_width_chars(9)
        self.xmax.connect('activate', self.set_plot_limits)
        xmax_label = Gtk.Label(label='xmax:')

        self.ymin = Gtk.Entry()
        self.ymin.connect('activate', self.set_plot_limits)
        self.ymin.set_width_chars(9)
        ymin_label = Gtk.Label(label='ymin:')
        self.ymax = Gtk.Entry()
        self.ymax.set_width_chars(9)
        self.ymax.connect('activate', self.set_plot_limits)
        ymax_label = Gtk.Label(label='ymax:')

        [i.set_text('{:.1f}'.format(j)) for j, i in
         zip(self.subplot.get_xlim() + self.subplot.get_ylim(), (self.xmin, self.xmax, self.ymin, self.ymax))]

        limits.pack_start(xmin_label, 0, 0, 0)
        limits.pack_start(self.xmin, 0, 0, 2)
        limits.pack_start(xmax_label, 0, 0, 0)
        limits.pack_start(self.xmax, 0, 0, 2)
        limits.pack_start(ymin_label, 0, 0, 0)
        limits.pack_start(self.ymin, 0, 0, 2)
        limits.pack_start(ymax_label, 0, 0, 0)
        limits.pack_start(self.ymax, 0, 0, 2)

        limitbox = Gtk.ToolItem()
        limitbox.add(limits)
        navbar.insert(limitbox, 9)
        return navbar

    def create_param_view(self):
        self.treeview = Gtk.TreeView(model=self.create_parameter_model())

        self.treeview.append_column(Gtk.TreeViewColumn("Parameters", Gtk.CellRendererText(), text=0))

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(270, -1)
        # workaround for allocation warning GTK bug
        # grid = Gtk.Grid()
        # grid.attach(self.treeview, 0, 0, 1, 1)
        # sw.add(grid)
        sw.add(self.treeview)

        bbox = Gtk.HBox(homogeneous=True)

        add_button = Gtk.Button(label='Add')
        add_button.connect('clicked', self.plot_parameter)

        clear_button = Gtk.Button(label='Clear')
        clear_button.connect('clicked', self.clear_parameter)

        self.plot_diff = Gtk.CheckButton(label='DIFF', active=False)
        self.plot_diff.set_tooltip_text('Plot difference between consecutive parameter values')

        bbox.pack_start(add_button, 1, 1, 0)
        bbox.pack_start(clear_button, 1, 1, 0)
        bbox.pack_start(self.plot_diff, 0, 0, 0)

        hbox = Gtk.HBox(homogeneous=True)
        data_button = Gtk.Button(label='View plot data')
        data_button.set_image(Gtk.Image.new_from_icon_name('gtk-justify-fill', Gtk.IconSize.BUTTON))
        data_button.set_always_show_image(True)
        data_button.connect('clicked', self.show_plot_data)

        save_button = Gtk.Button(label='Save plot data')
        save_button.set_image(Gtk.Image.new_from_icon_name('gtk-save', Gtk.IconSize.BUTTON))
        save_button.set_always_show_image(True)
        save_button.connect('clicked', self.save_plot_data)

        hbox.pack_start(data_button, 1, 1, 0)
        hbox.pack_start(save_button, 1, 1, 0)

        box = Gtk.HBox()
        add_userpar_butt = Gtk.Button(label='Add User Defined Parameter')
        add_userpar_butt.connect('clicked', self.add_user_parameter, self.treeview)
        edit_userpar_butt = Gtk.Button()
        edit_userpar_butt.set_image(Gtk.Image.new_from_icon_name('gtk-edit', Gtk.IconSize.BUTTON))
        edit_userpar_butt.connect('clicked', self.edit_user_parameter, self.treeview)
        edit_userpar_butt.set_tooltip_text('Edit user defined parameter')
        rm_userpar_butt = Gtk.Button()
        rm_userpar_butt.set_image(Gtk.Image.new_from_icon_name('list-remove', Gtk.IconSize.BUTTON))
        rm_userpar_butt.connect('clicked', self.remove_user_parameter, self.treeview)
        rm_userpar_butt.set_tooltip_text('Remove user defined parameter')
        box.pack_start(add_userpar_butt, 1, 1, 0)
        box.pack_start(edit_userpar_butt, 0, 0, 0)
        box.pack_start(rm_userpar_butt, 0, 0, 0)

        vbox = Gtk.VBox()
        vbox.pack_start(box, 0, 0, 0)
        vbox.pack_start(sw, 1, 1, 0)
        vbox.pack_start(bbox, 0, 0, 0)
        vbox.pack_start(hbox, 0, 0, 0)

        return vbox

    def create_parameter_model(self):
        parameter_model = Gtk.TreeStore(str)
        self.store = parameter_model

        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pid_descr,pid_spid,pid_type from pid order by pid_type,pid_stype,pid_pi1_val')
        hks = dbres.fetchall()

        topleveliters = {}
        for hk in hks:

            if not hk[2] in topleveliters:
                serv = parameter_model.append(None, ['Service ' + str(hk[2])])
                topleveliters[hk[2]] = serv

            it = parameter_model.append(topleveliters[hk[2]], [hk[0]])

            dbres = dbcon.execute('SELECT pcf.pcf_descr from pcf left join plf on pcf.pcf_name=plf.plf_name left join pid on \
                                   plf.plf_spid=pid.pid_spid where pid.pid_spid={} ORDER BY pcf.pcf_descr'.format(hk[1]))
            params = dbres.fetchall()
            for par in params:
                parameter_model.append(it, [par[0]])

        dbcon.close()

        # add user defined PACKETS
        topit = parameter_model.append(None, ['UDEF'])
        for hk in self.user_tm_decoders:
            it = parameter_model.append(topit, ['UDEF|{}'.format(self.user_tm_decoders[hk][0])])
            for par in self.user_tm_decoders[hk][1]:
                parameter_model.append(it, [par[1]])

        # add user defined PARAMETERS
        self.useriter = parameter_model.append(None, ['User defined'])
        for userpar in self.cfg[cfl.CFG_SECT_PLOT_PARAMETERS]:
            parameter_model.append(self.useriter, [userpar])

        return parameter_model

    def pool_changed(self, combobox, pool=False):
        if pool:
            model = self.pool_selector.get_model()
            count = 0
            while count < len(model):
                found_pool = []
                x = 0
                while x < 4:
                    found_pool.append(model.get_value(model.get_iter(count), x))  # Get the value
                    x += 1

                value = found_pool[2]

                if self.loaded_pool and value == self.loaded_pool.pool_name:
                    self.pool_selector.set_active_iter(model.get_iter(count))
                    self.loaded_pool = ActivePoolInfo(found_pool[0], found_pool[1], found_pool[2], found_pool[3])
                    break
                count += 1

        else:
            value = self.pool_selector.get_active_text()
            model = self.pool_selector.get_model()
            count = 0
            while count < len(model):
                found_pool = []
                x = 0
                while x < 4:
                    found_pool.append(model.get_value(model.get_iter(count), x))  # Get the value
                    x += 1

                if value == found_pool[2]:
                    self.pool_selector.set_active_iter(model.get_iter(count))
                    self.loaded_pool = ActivePoolInfo(found_pool[0], found_pool[1], found_pool[2], found_pool[3])
                    break
                count += 1
        return

    def update_pool_view(self):

        # Specify which Pool should be used
        # Or check between which Pools should be selected
        all_pools = None
        if cfl.is_open('poolmanager'):
            # pmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
            pmgr = cfl.get_module_handle('poolmanager', instance=cfl.communication['poolmanager'])
            all_pools = pmgr.Dictionaries('loaded_pools')
            # all_pools = cfl.Dictionaries(pmgr, 'loaded_pools')
            #if not all_pools:
            #    found_pools = None
            #elif len(active_pool) == 1:
                #active_pool = list(active_pool.values())
                #loaded_pool = ActivePoolInfo(active_pool[0][0],active_pool[0][1],active_pool[0][2],active_pool[0][3])
                #self.loaded_pool = loaded_pool
            #else:
            #    found_pools = list(all_pools.keys())

        elif cfl.is_open('poolviewer'):
            # pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            pv = cfl.get_module_handle('poolviewer', instance=cfl.communication['poolviewer'])
            all_pools = pv.Variables('active_pool_info')
            # all_pools = cfl.Variables(pv, 'active_pool_info')
            #if all_pools:
                #loaded_pool = ActivePoolInfo(active_pool[0],active_pool[1],active_pool[2],active_pool[3])
            #    found_pools = all_pools[2]
            #else:
            #    found_pools = None
        #else:
        #    pass

        model = self.pool_selector.get_model()

        #model.clear()

        # Check which pool are already in the plotter and which have to be added

        if isinstance(all_pools, dict):
            # Loop over all pools that are in manager
            for pool_info in all_pools.values():
                x = False   # If the pool is already in the plotter
                count = 0
                while count < len(model):   # Loop over all entries in the model to compare to pool
                    i = 0
                    found_pool = [] # Entry in the model (liststore)
                    # Get the full entry, only one of the four values can be gotten at a time -> do 4 times
                    while i < 4:
                        found_pool.append(model.get_value(model.get_iter(count), i))  # Get the value
                        i += 1
                    if pool_info == tuple(found_pool):  # Check if pools match
                        x = True    # If at least one entry matches to the pool it is not necessary to add
                    count += 1
                if not x:   # Add a pool if it is not already in the model (liststore)
                    model.append([pool_info[0], pool_info[1], pool_info[2], pool_info[3]])

        elif all_pools and all_pools[2]:
            pool_info = all_pools
            x = False  # If the pool is already in the plotter
            count = 0
            while count < len(model):  # Loop over all entries in the model to compare to pool
                i = 0
                found_pool = []  # Entry in the model (liststore)
                # Get the full entry, only one of the four values can be gotten at a time -> do 4 times
                while i < 4:
                    found_pool.append(model.get_value(model.get_iter(count), i))  # Get the value
                    i += 1
                if pool_info == tuple(found_pool):  # Check if pools match
                    x = True  # If at least one entry matches to the pool it is not necessary to add
                count += 1
            if not x:  # Add a pool if it is not already in the model (liststore)
                model.append([pool_info[0], pool_info[1], pool_info[2], pool_info[3]])

        #if len(model) == 2:
        #    self.pool_changed(False, pool_info[2])
        return True

    def add_user_parameter(self, widget, treeview):
        parameter_model = treeview.get_model()

        param_values = cfl.add_user_parameter(parentwin=self)

        if param_values:
            label, apid, st, sst, sid, bytepos, fmt, offbi = param_values
            self.user_parameters[label] = json.dumps(
                {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi})

            parameter_model.append(self.useriter, [label])

    def remove_user_parameter(self, widget, treeview):

        selection = treeview.get_selection()
        model, parpath = selection.get_selected_rows()
        # parameter_model = treeview.get_model()

        try:
            if model[parpath].parent is not None and model[parpath].parent[0] == 'User defined':  # Check if selection is an object or the parent tab is selected
                parname = model[parpath][0]
                param_values = cfl.remove_user_parameter(parname)
            else:
                param_values = None

        except Exception as err:
            self.logger.warning(err)
            # param_values = cfl.remove_user_parameter(parentwin=self)
            return

        if param_values:
            parameter_model = self.treeview.get_model()
            self.user_parameters.pop(param_values)
            parameter_model.remove(self.useriter)
            self.useriter = self.store.append(None, ['User defined'])
            for userpar in self.cfg[cfl.CFG_SECT_PLOT_PARAMETERS]:
                parameter_model.append(self.useriter, [userpar])

    def edit_user_parameter(self, widget, treeview):
        selection = treeview.get_selection()
        model, parpath = selection.get_selected_rows()

        try:
            if model[parpath].parent is not None and model[parpath].parent[0] == 'User defined':  # Check if selection is an object or the parent tab is selected
                parname = model[parpath][0]
                param_values = cfl.edit_user_parameter(self, parname)
                if param_values:
                    self.user_parameters.pop(parname)
                    label, apid, st, sst, sid, bytepos, fmt, offbi = param_values
                    self.user_parameters[label] = json.dumps(
                        {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi})

                    model[parpath][0] = label

            else:
                return
                # param_values = cfl.edit_user_parameter(self)
                # if param_values:
                #     label, apid, st, sst, sid, bytepos, fmt, offbi = param_values
                #     self.user_parameters[label] = json.dumps(
                #         {'APID': apid, 'ST': st, 'SST': sst, 'SID': sid, 'bytepos': bytepos, 'format': fmt, 'offbi': offbi})

        except Exception as err:
            self.logger.warning(err)
            return

    def create_univie_box(self):
        """
        Creates the Univie Button which can be found in every application, Used to Start all parts of the CCS and
        manage communication
        :return:
        """
        univie_box = Gtk.HBox()
        univie_button = Gtk.ToolButton()
        # button_run_nextline.set_icon_name("media-playback-start-symbolic")
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            self.cfg.get('paths', 'ccs') + '/pixmap/Icon_Space_blau_en.png', 24, 24)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        univie_button.set_icon_widget(icon)
        univie_button.set_tooltip_text('Applications and About')
        univie_button.connect("clicked", self.on_univie_button)
        univie_box.add(univie_button)

        # Popover creates the popup menu over the button and lets one use multiple buttons for the same one
        self.popover = Gtk.Popover()
        # Add the different Starting Options
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin=4)
        for name in self.cfg['ccs-dbus_names']:
            start_button = Gtk.Button.new_with_label("Start " + name.capitalize())
            start_button.connect("clicked", cfl.on_open_univie_clicked)
            vbox.pack_start(start_button, False, True, 0)

        # Add the manage connections option
        conn_button = Gtk.Button.new_with_label('Communication')
        conn_button.connect("clicked", self.on_communication_dialog)
        vbox.pack_start(conn_button, False, True, 0)

        # Add the option to see the Credits
        about_button = Gtk.Button.new_with_label('About')
        about_button.connect("clicked", self._on_select_about_dialog)
        vbox.pack_start(about_button, False, True, 10)

        self.popover.add(vbox)
        self.popover.set_position(Gtk.PositionType.BOTTOM)
        self.popover.set_relative_to(univie_button)

        return univie_box

    def on_univie_button(self, action):
        """
        Adds the Popover menu to the UNIVIE Button
        :param action: Simply the button
        :return:
        """
        self.popover.show_all()
        self.popover.popup()

    def on_communication_dialog(self, button):
        cfl.change_communication_func(main_instance=self.main_instance, parentwin=self)

    def _on_select_about_dialog(self, action):
        cfl.about_dialog(self)
        return

    def get_active_pool_name(self):
        return self.pool_selector.get_active_text()

    def sid_position_query(self, st, sst, apid, sid):

        if (st, sst, apid) in self.pi1_lut:
            sid_offset, sid_bitlen = self.pi1_lut[(st, sst, apid)]
        else:
            # dbcon = self.session_factory_idb
            # que = 'SELECT PIC_PI1_OFF, PIC_PI1_WID FROM pic WHERE PIC_TYPE ="{}" AND PIC_STYPE ="{}" AND PIC_APID ="{}"'.format(st, sst, apid)
            # dbres = dbcon.execute(que)
            # sid_offset, sid_bitlen = dbres.fetchall()[0]
            # dbcon.close()
            sidinfo = cfl.get_sid(st, sst, apid)
            if sidinfo:
                sid_offset, sid_bitlen = sidinfo
                self.pi1_lut[(st, sst, apid)] = (sid_offset, sid_bitlen)
            else:
                return

        if sid_offset == -1 or sid == 0:
            return

        # sid_search = b''
        # i = 0
        # while i < sid_offset:
        #     i += 1
        #     sid_search += b'_'
        #
        # sid_search += struct.pack('>' + pi1_length_in_bits[sid_length], sid)
        # sid_search += b'%'

        return sid_offset, sid_bitlen // 8

    def plot_parameter(self, widget=None, parameter=None):

        nocal = not self.calibrate.get_active()

        if parameter is not None:
            hk, parameter = parameter
        else:
            selection = self.treeview.get_selection()
            model, treepath = selection.get_selected()

            if treepath is None:
                return

            parameter = model[treepath][0]

            if model[treepath].parent is None:
                return

            hk = model[treepath].parent[0]

        rows = cfl.get_pool_rows(self.loaded_pool.filename)
        rows = self.set_plot_range(rows)

        dbcon = self.session_factory_idb

        if hk != 'User defined' and not hk.startswith('UDEF|'):
            que = 'SELECT pid_type,pid_stype,pid_pi1_val,pid_apid FROM pid LEFT JOIN plf ON pid.pid_spid=plf.plf_spid ' \
                  'LEFT JOIN pcf ON plf.plf_name=pcf.pcf_name WHERE pcf.pcf_descr="{}" AND ' \
                  'pid.pid_descr="{}"'.format(parameter, hk)
            dbres = dbcon.execute(que).fetchall()

            if not dbres:
                self.logger.error('{} is not a valid parameter.'.format(parameter))
                return

            st, sst, sid, apid = dbres[0]

        elif hk.startswith('UDEF|'):
            label = hk.replace('UDEF|', '')
            tag = [k for k in self.user_tm_decoders if self.user_tm_decoders[k][0] == label][0]
            pktinfo = tag.split('-')
            st = int(pktinfo[0])
            sst = int(pktinfo[1])
            apid = int(pktinfo[2]) if pktinfo[2] != 'None' else None
            sid = int(pktinfo[3]) if pktinfo[3] != 'None' else None

        else:
            userpar = json.loads(self.cfg[cfl.CFG_SECT_PLOT_PARAMETERS][parameter])
            st, sst, apid = userpar['ST'], userpar['SST'], userpar['APID']

            if 'SID' in userpar and userpar['SID']:
                sid = userpar['SID']
            else:
                sid = None

        if self.sid_position_query(st, sst, apid, sid) is None:
            if sid:
                self.logger.error('{}: SID not applicable.'.format(parameter))
                return

            sid = None

        rows = cfl.filter_rows(rows, st=st, sst=sst, apid=apid, sid=sid)

        if not self.filter_tl2.get_active():
            rows = cfl.filter_rows(rows, time_from=2.)
            # rows = rows.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) > 2.)

        try:
            # TODO: speedup?
            if hk in self._pkt_buffer:
                bufidx, pkts = self._pkt_buffer[hk]

                rows = cfl.filter_rows(rows, idx_from=bufidx+1)
                if rows.first() is not None:
                    bufidx = rows.order_by(DbTelemetry.idx.desc()).first().idx
                    pkts += [row.raw for row in rows.yield_per(1000)]
                    self._pkt_buffer[hk] = (bufidx, pkts)

            else:
                pkts = [row.raw for row in rows.yield_per(1000)]
                if len(pkts) > 0:
                    bufidx = rows.order_by(DbTelemetry.idx.desc()).first().idx
                    self._pkt_buffer[hk] = (bufidx, pkts)

            xy, (descr, unit) = cfl.get_param_values(pkts, hk=hk, param=parameter,
                                                     numerical=True, tmfilter=False, nocal=nocal)

            if len(xy) == 0:
                return

        except (ValueError, TypeError) as err:
            self.logger.debug(err)
            self.logger.error("Can't plot {}".format(parameter))
            return

        # store packet info for update worker
        self.data_dict[hk + ':' + descr] = xy
        self.data_dict_info[hk + ':' + descr] = {}
        self.data_dict_info[hk + ':' + descr]['idx_last'] = bufidx
        # self.data_dict_info[hk + ':' + descr]['idx_last'] = rows.order_by(DbTelemetry.idx.desc()).first().idx
        self.data_dict_info[hk + ':' + descr]['st'] = st
        self.data_dict_info[hk + ':' + descr]['sst'] = sst
        self.data_dict_info[hk + ':' + descr]['apid'] = apid
        self.data_dict_info[hk + ':' + descr]['sid'] = sid

        # npoints = self.count_datapoints(self.subplot.get_xlim(), self.subplot.get_ylim())
        # if npoints > self.max_datapoints > 0:
        #     xy = xy.T[::npoints // self.max_datapoints + 1].T
        self.subplot.autoscale(enable=not self.scaley.get_active(), axis='y')

        try:
            if self.plot_diff.get_active():
                x, y = xy
                x1 = x[1:]
                dy = np.diff(y)
                line = self.subplot.plot(x1, dy, marker='.', label=descr, gid=hk)
            else:
                line = self.subplot.plot(*xy, marker='.', label=descr, gid=hk)
        except TypeError:
            self.logger.error("Can't plot data of type {}".format(xy.dtype[1]))
            return

        self.reduce_datapoints(self.subplot.get_xlim(), self.subplot.get_ylim(), fulldata=False)

        # draw limits if available
        dbres = dbcon.execute('SELECT pcf.pcf_name, pcf.pcf_descr, pcf.pcf_categ, pcf.pcf_unit, ocf.ocf_nbool,\
                                            ocp.ocp_lvalu, ocp.ocp_hvalu from pcf left join ocf on\
                                            pcf.pcf_name=ocf.ocf_name left join ocp on ocf_name=ocp_name\
                                            where pcf.pcf_descr="{}"'.format(parameter))
        limits = dbres.fetchall()
        dbcon.close()

        try:
            nlims = limits[0][-3]
            if nlims is not None:
                if nlims == 1:
                    param_id, plabel, fmt, unit, _, lolim, hilim = limits[0]
                    hardlim = (float(lolim), float(hilim))
                    softlim = (None, None)
                else:
                    param_id, plabel, fmt, unit = limits[0][:4]
                    softlim, hardlim = [(float(x[-2]), float(x[-1])) for x in limits]
                show_limits = self.show_limits.get_active()
                if softlim != (None, None):
                    for pos, y in zip(('lo', 'hi'), softlim):
                        limitline = self.subplot.axhline(y, color=line[0].get_color(), alpha=0.5, ls=':',
                                                         label='_lim_soft_{}_{}'.format(pos, parameter))
                        limitline.set_visible(show_limits)
                        self.parameter_limits.add(limitline)
                for pos, y in zip(('lo', 'hi'), hardlim):
                    limitline = self.subplot.axhline(y, color=line[0].get_color(), alpha=0.5, ls='--',
                                                     label='_lim_hard_{}_{}'.format(pos, parameter))
                    limitline.set_visible(show_limits)
                    self.parameter_limits.add(limitline)
        except IndexError:
            self.logger.info('Parameter {} does not have limits to plot'.format(parameter))

        # self.subplot.fill_between([-1e9,1e9],[1,1],[2,2],facecolor='orange',alpha=0.5,hatch='/')
        # self.subplot.fill_between([-1e9,1e9],2,10,facecolor='red',alpha=0.5)

        self.subplot.legend(loc=2, framealpha=0.5)  # bbox_to_anchor=(0.,1.02,1.,.102),mode="expand", borderaxespad=0)
        if self.subplot.get_legend() is not None:
            self.subplot.get_legend().set_visible(self.show_legend.get_active())

        self.subplot.set_ylabel('[{}]'.format(unit))
        self.canvas.draw()

    def set_plot_range(self, rows):
        try:
            self.data_min_idx = int(self.min_idx.get_text())
            rows = rows.filter(DbTelemetry.idx >= self.data_min_idx)
        except (TypeError, ValueError):
            self.data_min_idx = None
        try:
            self.data_max_idx = int(self.max_idx.get_text())
            rows = rows.filter(DbTelemetry.idx <= self.data_max_idx)
        except (TypeError, ValueError):
            self.data_max_idx = None

        try:
            self.max_datapoints = int(self.max_data.get_text())
        except (TypeError, ValueError):
            self.max_datapoints = 0

        return rows

    def _toggle_limits(self, widget=None):
        if widget.get_active():
            for line in self.parameter_limits:
                line.set_visible(1)
        else:
            for line in self.parameter_limits:
                line.set_visible(0)
        self.canvas.draw()

    # def _set_max_datapoints(self, widget=None):
    #     try:
    #         n = int(widget.get_text())
    #         if n < 0:
    #             widget.set_text('0')
    #             n = 0
    #     except (TypeError, ValueError):
    #         if widget.get_text() == '':
    #             n = 0
    #             widget.set_text('0')
    #         else:
    #             widget.set_text('0')
    #             return
    #     self.max_datapoints = n

    def reduce_datapoints(self, xlim, ylim, fulldata=True):

        ax = self.canvas.figure.get_axes()[0]

        if self.max_datapoints > 0:
            n_datapoints = self.count_datapoints(xlim, ylim)
            if n_datapoints > self.max_datapoints:
                red_fac = n_datapoints // self.max_datapoints + 1
                for line in ax.lines:
                    if not line.get_label().startswith('_lim_'):
                        x, y = self.data_dict[line.get_gid() + ':' + line.get_label()]
                        if self.plot_diff.get_active():
                            x = x[1:]
                            y = np.diff(y)
                        line.set_xdata(x[::red_fac])
                        line.set_ydata(y[::red_fac])
        elif fulldata:
            for line in ax.lines:
                if not line.get_label().startswith('_lim_'):
                    x, y = self.data_dict[line.get_gid() + ':' + line.get_label()]
                    if self.plot_diff.get_active():
                        x = x[1:]
                        y = np.diff(y)
                    line.set_xdata(x)
                    line.set_ydata(y)

    def count_datapoints(self, xlim, ylim):
        try:
            n = sum([len(np.where((xlim[0] < x) & (x < xlim[1]) & (ylim[0] < y) & (y < ylim[1]))[0]) for x, y in
                     self.data_dict.values()])
        except ValueError:
            n = 0
        self.max_data.set_tooltip_text('{} datapoints'.format(n))
        return n

    def clear_parameter(self, widget):
        self.data_dict.clear()
        self.data_dict_info.clear()
        self.parameter_limits.clear()
        self.subplot.clear()
        self.subplot.grid()
        self.subplot.set_xlabel('CUC Time [s]')
        self.subplot.callbacks.connect('xlim_changed', self._update_plot_xlimit_values)
        self.subplot.callbacks.connect('ylim_changed', self._update_plot_ylimit_values)
        self._update_plot_xlimit_values()
        self._update_plot_ylimit_values()
        self.canvas.draw()

    def update_plot_worker(self, plot=None, parameter=None):
        # pool_name = self.pool_box.get_active_text()
        rows = cfl.get_pool_rows(self.loaded_pool.filename)
        rows = self.set_plot_range(rows)
        # xmin, xmax = self.subplot.get_xlim()
        lines = self.subplot.lines

        nocal = not self.calibrate.get_active()

        for line in lines:
            parameter = line.get_label()
            if not parameter.startswith('_lim_'):
                hk = line.get_gid()

                xold, yold = self.data_dict[hk + ':' + parameter]
                # time_last = round(float(xold[-1]), 6)  # np.float64 not properly understood in sql comparison below
                # new_rows = rows.filter(func.left(DbTelemetry.timestamp, func.length(DbTelemetry.timestamp) - 1) > time_last)
                pinfo = self.data_dict_info[hk + ':' + parameter]
                new_rows = cfl.filter_rows(rows, st=pinfo['st'], sst=pinfo['sst'], apid=pinfo['apid'],
                                           sid=pinfo['sid'], idx_from=pinfo['idx_last'] + 1)

                try:
                    # xnew, ynew = cfl.get_param_values([row.raw for row in new_rows], hk, parameter, numerical=True)[0]
                    xnew, ynew = cfl.get_param_values([row.raw for row in new_rows], hk, parameter, numerical=True, tmfilter=False, nocal=nocal)[0]
                    idx_new = new_rows.order_by(DbTelemetry.idx.desc()).first().idx
                except ValueError:
                    continue

                xy = np.stack([np.append(xold, xnew), np.append(yold, ynew)], -1).T
                self.data_dict[hk + ':' + parameter] = xy
                self.data_dict_info[hk + ':' + parameter]['idx_last'] = idx_new

        self.reduce_datapoints(self.subplot.get_xlim(), self.subplot.get_ylim())

        def set_view():
            self.subplot.autoscale(enable=not self.scaley.get_active(), axis='y')
            self.subplot.relim()
            self.subplot.autoscale_view()
            self.canvas.draw()

        GLib.idle_add(set_view, priority=GLib.PRIORITY_HIGH)

    def set_plot_limits(self, widget):
        limitbox = widget.get_parent()
        limits = [x.get_text() for x in limitbox.get_children()[1::2]]

        xmin, xmax, ymin, ymax = map(float, limits)
        self.subplot.set_xlim(xmin, xmax)
        self.subplot.set_ylim(ymin, ymax)
        self.reduce_datapoints((xmin, xmax), (ymin, ymax))
        self.canvas.draw()

    def _update_plot_xlimit_values(self, axes=None):
        if axes is None:
            axes = self.subplot
        xlim = axes.get_xlim()
        self.xmin.set_text(str(xlim[0]))
        self.xmax.set_text(str(xlim[1]))

    def _update_plot_ylimit_values(self, axes=None):
        if axes is None:
            axes = self.subplot
        ylim = axes.get_ylim()
        self.ymin.set_text(str(ylim[0]))
        self.ymax.set_text(str(ylim[1]))

    def toggle_yscale(self, button):
        active = button.get_active()

        if active:
            self.subplot.set_yscale('log')
            self.canvas.draw()
        else:
            self.subplot.set_yscale('linear')
            self.canvas.draw()

    def toggle_legend(self, button):
        active = button.get_active()
        if self.subplot.get_legend():
            self.subplot.get_legend().set_visible(active)
            self.canvas.draw()

    def on_switch_liveplot(self, widget, onoff=None):
        self.liveplot = onoff
        if onoff:
            thread = threading.Thread(target=self.update_plot)
            thread.name = 'Plot-updater'
            thread.daemon = True
            thread.start()

    def update_plot(self):
        while self.liveplot:
            t1 = time.time()
            # GLib.idle_add(self.update_plot_worker, priority=GLib.PRIORITY_HIGH)
            self.update_plot_worker()
            dt = self.refresh_rate - (time.time() - t1)
            if dt > 0:
                time.sleep(dt)

    def set_refresh_rate(self, rate):
        self.refresh_rate = rate

    def save_plot_data(self, widget=None, data=None, filename=None):

        def save(fname):
            d = {}
            # for line in self.subplot.lines:
            #     parameter = line.get_label()
            #     if not parameter.startswith('_lim_'):
            #         hk = line.get_gid()
            #         xy = line.get_xydata()
            #         try:
            #             d[hk][parameter] = xy
            #         except KeyError:
            #             d.setdefault(hk, {parameter: xy})

            for parameter in self.data_dict:
                hk, param = parameter.split(':')
                try:
                    d[hk][param] = self.data_dict[parameter].T
                except KeyError:
                    d.setdefault(hk, {param: self.data_dict[parameter].T})

            hkblocks = []
            for n in d:
                params = list(d[n].keys())
                head = '# {}\n# CUC_Time\t'.format(n) + '\t'.join(params) + '\n'
                datablock = '\n'.join(
                    ['{:.6F}\t'.format(
                        d[n][params[0]][i, 0]) +
                     '\t'.join(['{:.12G}'.format(d[n][param][i, 1]) for param in params])
                     for i in range(len(d[n][params[0]][:, 1]))])
                hkblocks.append(head + datablock)

            with open(fname, 'w') as fdesc:
                fdesc.write('# Source: {}\n'.format(self.loaded_pool.pool_name) + '\n\n'.join(hkblocks))

        if filename:
            save(filename)
            return

        else:
            dialog = Gtk.FileChooserDialog(title="Save data as", parent=self,
                                           action=Gtk.FileChooserAction.SAVE)
            dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                               Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
            dialog.set_transient_for(self)
            response = dialog.run()

            if response == Gtk.ResponseType.OK:
                filename = dialog.get_filename()
                save(filename)
            dialog.destroy()

    def show_plot_data(self, widget=None, data=None):
        datawin = DataWindow()
        d = {}
        for parameter in self.data_dict:
            hk, param = parameter.split(':')
            try:
                d[hk][param] = self.data_dict[parameter].T
            except KeyError:
                d.setdefault(hk, {param: self.data_dict[parameter].T})

        hkblocks = []
        text = ''
        for n in d:
            params = list(d[n].keys())
            head = '# {}\n# CUC_Time\t\t'.format(n) + '\t\t'.join(params) + '\n'
            datablock = '\n'.join(['{:.6F}\t\t'.format(d[n][params[0]][i, 0]) + '\t\t'.join(
                ['{:.12G}'.format(d[n][param][i, 1]) for param in params]) for i in range(len(d[n][params[0]][:, 1]))])
            hkblocks.append(head + datablock)
            text = '\n\n'.join(hkblocks)

        buf = datawin.textview.get_buffer()
        buf.set_text(text)

        datawin.show_all()

    # def write_cfg(self, widget=None, dummy=None):
    #     try:
    #         self.cfg.save_to_file()
    #
    #     except AttributeError:
    #         return

    def live_plot_off(self, widget, dummy):
        self.liveplot = False

    def select_pool(self, widget=None, pool=None):
        if not pool:
            dialog = SelectPoolDialog(self.logger, self.loaded_pool, parent=self)

            while True:
                response = dialog.run()
                if response == Gtk.ResponseType.OK:
                    try:
                        pool = dialog.selected_pool
                        self.loaded_pool = pool
                        self.pool_label.set_text(self.loaded_pool.pool_name)
                        break
                    except:
                        pass

                else:
                    break

            dialog.destroy()

        else:
            self.loaded_pool = pool
            self.pool_label.set_text(self.loaded_pool.pool_name)

        return

    def get_prev_loaded_pools(self):
        #if self.loaded_pool:
        #    return
        if cfl.is_open('poolviewer'):
            # pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            pv = cfl.get_module_handle('poolviewer')
            active_pool = cfl.Variables(pv, 'active_pool_info')
            #active_pool = pv.Variables('active_pool_info')
            if active_pool and active_pool[0]:
                loaded_pool = ActivePoolInfo(active_pool[0],active_pool[1],active_pool[2],active_pool[3])
                self.loaded_pool = loaded_pool
            #else:
            #    Notify.Notification.new('No Pool could be found! Please open one and specify it.').show()
            #    print('No Pool could be found! Please open one and specify it.')
            #    self.loaded_pool = None

        elif cfl.is_open('poolmanager'):
            # pmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
            pmgr = cfl.get_module_handle('poolmanager')
            active_pool = cfl.Dictionaries(pmgr, 'loaded_pools')
            #active_pool = pmgr.Dictionaries('loaded_pools')
            #if not active_pool:
            #    Notify.Notification.new('No Pool could be found! Please open one and specify it.').show()
            #    print('No Pool could be found! Please open one and specify it.')
            #    self.loaded_pool = None
            #elif len(active_pool) == 1:
            if len(active_pool) == 1:
                active_pool = list(active_pool.values())
                loaded_pool = ActivePoolInfo(active_pool[0][0],active_pool[0][1],active_pool[0][2],active_pool[0][3])
                self.loaded_pool = loaded_pool
            #else:
                #sys.exit('There is more than one pool available! Please specify which one should be used, by selecting it '
                      #'in the Poolviewer')
                #print('Could not determin which Pool should be used. Please specify the Pool')
                #Notify.Notification.new('Could not determin which Pool should be used. Please specify the Pool').show()
                #self.loaded_pool = None
        #else:
            #sys.exit('No pool could be found! Please open one and try again.')
            #Notify.Notification.new('No Pool could be found! Please open one and specify it.').show()
            #print('No Pool could be found! Please open one and specify it.')
            #self.loaded_pool = None

        if self.loaded_pool:
            #self.update_pool_view()
            self.pool_changed(self.pool_selector, pool=True) #self.loaded_pool)

        #if self.loaded_pool:
        #    self.select_pool(pool=self.loaded_pool)

    def quit_func(self, *args):
        # Try to tell terminal in the editor that the variable is not longer availabe
        for service in dbus.SessionBus().list_names():
            if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                editor = cfl.dbus_connection(service[0:-1].split('.')[1], service[-1])
                if self.main_instance == editor.Variables('main_instance'):
                    nr = self.my_bus_name[-1]
                    if nr == str(1):
                        nr = ''
                    editor.Functions('_to_console_via_socket', 'del(paramplot' + str(nr) + ')')

        self.update_all_connections_quit()
        Gtk.main_quit()
        return False

    def update_all_connections_quit(self):
        '''
        Tells all running applications that it is not longer availabe and suggests another main communicatior if one is
        available
        :return:
        '''
        our_con = [] # All connections to running applications without communicions form the same applications as this
        my_con = [] # All connections to same applications as this
        for service in dbus.SessionBus().list_names():
            if service.split('.')[1] in self.cfg['ccs-dbus_names']:   # Check if connection belongs to CCS
                if service == self.my_bus_name:     #If own allplication do nothing
                    continue
                conn = cfl.dbus_connection(service.split('.')[1], service[-1])
                if conn.Variables('main_instance') == self.main_instance:   #Check if running in same project
                    if service.startswith(self.my_bus_name[:-1]):   #Check if it is same application type
                        my_con.append(service)
                    else:
                        our_con.append(service)

        instance = my_con[0][-1] if my_con else 0   # Select new main application if possible, is randomly selected
        our_con = our_con + my_con  # Add the instances of same application to change the main communication as well
        for service in our_con:     # Change the main communication for all applications+
            conn = cfl.dbus_connection(service.split('.')[1], service[-1])
            comm = conn.Functions('get_communication')
            # Check if this application is the main applications otherwise do nothing
            if str(comm[self.my_bus_name.split('.')[1]]) == self.my_bus_name[-1]:
                conn.Functions('change_communication', self.my_bus_name.split('.')[1], instance, False)
        return

    def change_communication(self, application, instance=1, check=True):
        # If it is checked that both run in the same project it is not necessary to do it again
        if check:
            conn = cfl.dbus_connection(application, instance)
            # Both are not in the same project do not change

            if not conn.Variables('main_instance') == self.main_instance:
                self.logger.error('Application {} is not in the same project as {}: Can not communicate'.format(
                    self.my_bus_name, self.cfg['ccs-dbus_names'][application] + str(instance)))
                return

        cfl.communication[application] = int(instance)
        return

    def get_communication(self):
        return cfl.communication

    def connect_to_all(self, My_Bus_Name, Count):
        self.my_bus_name = My_Bus_Name

        # Look if other applications are running in the same project group
        our_con = []
        # Look for all connections starting with com, therefore only one loop over all connections is necessary
        for service in dbus.SessionBus().list_names():
            if service.startswith('com'):
                our_con.append(service)

        # Check if a com connection has the same name as given in cfg file
        for app in our_con:
            if app.split('.')[1] in self.cfg['ccs-dbus_names']:
                # If name is the name of the program skip
                if app == self.my_bus_name:
                    continue

                # Otherwise save the main connections in cfl.communication
                conn_name = app.split('.')[1]

                conn = cfl.dbus_connection(conn_name, app[-1])
                if conn.Variables('main_instance') == self.main_instance:
                    cfl.communication = conn.Functions('get_communication')
                    conn_com = conn.Functions('get_communication')
                    if conn_com[self.my_bus_name.split('.')[1]] == 0:
                        conn.Functions('change_communication', self.my_bus_name.split('.')[1], self.my_bus_name[-1], False)

        if not cfl.communication[self.my_bus_name.split('.')[1]]:
            cfl.communication[self.my_bus_name.split('.')[1]] = int(self.my_bus_name[-1])

        # Connect to all terminals
        if Count == 1:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "paramplot = dbus.SessionBus().get_object('" +
                                     str(My_Bus_Name) + "', '/MessageListener')")

        else:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "paramplot" + str(Count) +
                                     " = dbus.SessionBus().get_object('" + str(My_Bus_Name) +
                                     "', '/MessageListener')")

        # Get the prev loaded Pools form Viewer and Manager if none is given
        self.update_pool_view()
        self.get_prev_loaded_pools()
        GLib.timeout_add_seconds(5, self.update_pool_view)
        return


# This class seems to be no longer needed
class NavigationToolbarX(NavigationToolbar):

    def __init__(self, *args, **kwargs):
        super(NavigationToolbarX, self).__init__(*args, **kwargs)
        self._ids_zoom = []

    # override this function to avoid call to Gtk.main_iteration,
    # which causes crash when multiple PlotViewer instances are running
    def set_cursor(self, cursor):
        # self.canvas.get_property("window").set_cursor(cursord[cursor])
        self.canvas.set_cursor(cursor)

    def release_zoom(self, event):
        """the release mouse button callback in zoom to rect mode"""
        for zoom_id in self._ids_zoom:
            self.canvas.mpl_disconnect(zoom_id)
        # self._ids_zoom = []

        self.remove_rubberband()

        if not self._xypress:
            return

        last_a = []

        for cur_xypress in self._xypress:
            x, y = event.x, event.y
            lastx, lasty, a, ind, view = cur_xypress
            # ignore singular clicks - 5 pixels is a threshold
            # allows the user to "cancel" a zoom action
            # by zooming by less than 5 pixels
            if ((abs(x - lastx) < 5 and self._zoom_mode!="y") or
                    (abs(y - lasty) < 5 and self._zoom_mode!="x")):
                self._xypress = None
                self.release(event)
                self.draw()
                return

            # detect twinx,y axes and avoid double zooming
            twinx, twiny = False, False
            if last_a:
                for la in last_a:
                    if a.get_shared_x_axes().joined(a, la):
                        twinx = True
                    if a.get_shared_y_axes().joined(a, la):
                        twiny = True
            last_a.append(a)

            if self._button_pressed == 1:
                direction = 'in'
            elif self._button_pressed == 3:
                direction = 'out'
            else:
                continue

            a._set_view_from_bbox((lastx, lasty, x, y), direction,
                                  self._zoom_mode, twinx, twiny)

        xlim, ylim = a.get_xlim(), a.get_ylim()
        self.canvas.get_parent().get_parent().get_parent().reduce_datapoints(xlim, ylim)

        self.draw()
        self._xypress = None
        self._button_pressed = None

        self._zoom_mode = None

        self.push_current()
        self.release(event)


class DataWindow(Gtk.Window):
    def __init__(self, parent=None):
        Gtk.Window.__init__(self)

        self.set_title('Data Viewer')
        self.set_default_size(400, 600)
        sv = Gtk.ScrolledWindow()
        self.add(sv)

        self.textview = Gtk.TextView(cursor_visible=False, editable=False)
        sv.add(self.textview)


class SelectPoolDialog(Gtk.Dialog):

    def __init__(self, logger, pool_list, parent=None):
        Gtk.Dialog.__init__(self, "Pool Selection", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        self.explain_label = Gtk.Label()
        self.explain_label.set_text("Please select one of the shown pools to plot.")

        self.set_border_width(5)

        box = self.get_content_area()
        ok_button = self.get_action_area().get_children()[0]

        self.bytebox = Gtk.HBox()
        self.pools = self.check_for_multiple_pools()

        if self.pools is not None:
            if len(self.pools) == 1:
                self.make_buttons(self.pools[0])
            else:
                for pool in self.pools:
                    self.make_buttons(pool)

            self.label = Gtk.Label()
            self.label.set_text("Your selection is: ")

        else:
            self.label = Gtk.Label()
            self.label.set_text("No pools could be found")
            ok_button.set_sensitive(False)

        box.pack_start(self.explain_label, 0, 0, 0)
        box.pack_start(self.bytebox, 0, 0, 0)
        box.pack_end(self.label, 0, 0, 0)
        box.set_spacing(10)
        self.show_all()

    def check_for_multiple_pools(self):
        # Specify which Pool should be used
        # Or check between which Pools should be selected

        if cfl.is_open('poolmanager'):
            # pmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
            pmgr = cfl.get_module_handle('poolmanager')
            self.all_pools = pmgr.Dictionaries('loaded_pools')
            if not self.all_pools:
                self.loaded_pool = None
            #elif len(active_pool) == 1:
                #active_pool = list(active_pool.values())
                #loaded_pool = ActivePoolInfo(active_pool[0][0],active_pool[0][1],active_pool[0][2],active_pool[0][3])
                #self.loaded_pool = loaded_pool
            else:
                self.loaded_pool = list(self.all_pools.keys())

        elif cfl.is_open('poolviewer'):
            # pv = cfl.dbus_connection('poolviewer', cfl.communication['poolmanager'])
            pv = cfl.get_module_handle('poolviewer')
            self.all_pools = pv.Variables('active_pool_info')
            if self.all_pools:
                #loaded_pool = ActivePoolInfo(active_pool[0],active_pool[1],active_pool[2],active_pool[3])
                self.loaded_pool = self.all_pools[2]
            else:
                self.loaded_pool=None

        else:
            self.loaded_pool = None

        return self.loaded_pool

    def make_buttons(self, button_name):
        button = Gtk.Button.new_with_label(button_name)
        button._value = button_name
        button.connect("clicked", self.got_selection)
        self.bytebox.pack_start(button, True, True, 0)

    def got_selection(self, button):
        pool = button._value
        if isinstance(self.all_pools, dict):
            pool_info = self.all_pools[pool]
            self.selected_pool = ActivePoolInfo(pool_info[0],pool_info[1],pool_info[2],pool_info[3])
            self.label.set_text("Your selection is: "+str(self.selected_pool[2]))
            return
        elif self.all_pools:
            pool_info = self.all_pools
            self.selected_pool = ActivePoolInfo(pool_info[0],pool_info[1],pool_info[2],pool_info[3])
            self.label.set_text("Your selection is: " + str(self.selected_pool[2]))
            return
        else:
            return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pool = sys.argv[1]
    else:
        pool = None

    # Important to tell Dbus that Gtk loop can be used before the first dbus command
    DBusGMainLoop(set_as_default=True)
    if pool:
        win = PlotViewer(loaded_pool=pool)
    else:
        win = PlotViewer()
    Bus_Name = cfg.get('ccs-dbus_names', 'plotter')
    # DBusGMainLoop(set_as_default=True)
    DBus_Basic.MessageListener(win, Bus_Name, *sys.argv)
    win.connect("delete-event", win.quit_func)
    win.show_all()
    Gtk.main()