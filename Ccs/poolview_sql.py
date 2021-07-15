import os
import json
import struct
import threading
import subprocess
import time
import sys
import traceback

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import DBus_Basic

#from ccs_function_lib import General_Functions
#cfl = General_Functions()
import ccs_function_lib as cfl

from typing import NamedTuple

import confignator
import configparser
import gi

import matplotlib

matplotlib.use('Gtk3Cairo')

from matplotlib.figure import Figure
# from matplotlib.backends.backend_gtk3cairo import FigureCanvasGTK3Cairo as FigureCanvas
from matplotlib.backends.backend_gtk3agg import FigureCanvasGTK3Agg as FigureCanvas
from matplotlib.backends.backend_gtk3 import NavigationToolbar2GTK3 as NavigationToolbar
from matplotlib.backends.backend_gtk3 import cursord

import numpy as np

from database.tm_db import DbTelemetryPool, DbTelemetry, RMapTelemetry, FEEDataTelemetry, scoped_session_maker
#from database.tm_db import DbTelemetryPool, DbTelemetry, scoped_session_maker

from sqlalchemy.sql.expression import func, distinct
from sqlalchemy.orm import load_only, lazyload


import importlib
#check_cfg = configparser.ConfigParser()
#check_cfg.read('egse.cfg')
#check_cfg.source = 'egse.cfg'
from confignator import config
check_cfg = config.get_config(file_path=confignator.get_option('config-files', 'ccs'))

project = check_cfg.get('ccs-database', 'project')
project = 'packet_config_' + str(project)
packet_config = importlib.import_module(project)
TM_HEADER_LEN, TC_HEADER_LEN, PEC_LEN = [packet_config.TM_HEADER_LEN, packet_config.TC_HEADER_LEN, packet_config.PEC_LEN]
#from packet_config import TM_HEADER_LEN, TC_HEADER_LEN, PEC_LEN

gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Notify  # NOQA

from event_storm_squasher import delayed

import logging.handlers

ActivePoolInfo = NamedTuple(
    'ActivePoolInfo', [
        ('filename', str),
        ('modification_time', int),
        ('pool_name', str),
        ('live', bool)])

fmtlist = {'INT8': 'b', 'UINT8': 'B', 'INT16': 'h', 'UINT16': 'H', 'INT32': 'i', 'UINT32': 'I', 'INT64': 'q',
           'UINT64': 'Q', 'FLOAT': 'f', 'DOUBLE': 'd', 'INT24': 'i24', 'UINT24': 'I24', 'bit*': 'bit'}


Telemetry = {'PUS': DbTelemetry, 'RMAP': RMapTelemetry, 'FEE': FEEDataTelemetry}
#Telemetry = {'PUS': DbTelemetry}


class TMPoolView(Gtk.Window):
    # (label, data columnt alignment)

    column_labels = {'PUS': [('#', 1), ('TM/TC', 1), ("APID", 1), ("SEQ", 1), ("len-7", 1), ("ST", 1), ("SST", 1),
                             ("Dest ID", 1), ("Time", 1), ("Data", 0)],
                     'RMAP': [('#', 1), ('R/W', 1), ('Verify data', 1), ('Reply', 1), ('Key', 1), ('Transaction ID', 1),
                              ('Address', 1), ('Data Length', 1), ('Raw', 0)],
                     'FEE': [('#', 1), ('Type', 1), ('Frame cnt', 1), ('Seq cnt', 1), ('Raw', 0)]}

    tm_columns = {'PUS': {'#': [DbTelemetry.idx, 0, None], 'TM/TC': [DbTelemetry.is_tm, 0, None],
                          "APID": [DbTelemetry.apid, 0, None], "SEQ": [DbTelemetry.seq, 0, None],
                          "len-7": [DbTelemetry.len_7, 0, None], "ST": [DbTelemetry.stc, 0, None],
                          "SST": [DbTelemetry.sst, 0, None], "Dest ID": [DbTelemetry.destID, 0, None],
                          "Time": [DbTelemetry.timestamp, 0, None], "Data": [DbTelemetry.data, 0, None]},
                  'RMAP': {'#': [RMapTelemetry.idx, 0, None], 'R/W': [RMapTelemetry.write, 0, None],
                           "Verify data": [RMapTelemetry.verify, 0, None], "Reply": [RMapTelemetry.reply, 0, None],
                           "Key": [RMapTelemetry.keystat, 0, None], "Transaction ID": [RMapTelemetry.taid, 0, None],
                           "Address": [RMapTelemetry.addr, 0, None], "Data Length": [RMapTelemetry.datalen, 0, None],
                           "Raw": [RMapTelemetry.raw, 0, None]},
                  'FEE': {'#': [FEEDataTelemetry.idx, 0, None], 'Type': [FEEDataTelemetry.type, 0, None],
                          "Frame cnt": [FEEDataTelemetry.framecnt, 0, None],
                          "Seq cnt": [FEEDataTelemetry.seqcnt, 0, None],
                          "Raw": [FEEDataTelemetry.raw, 0, None]}}

    sort_order_dict = {0: Gtk.SortType.ASCENDING, 1: Gtk.SortType.ASCENDING, 2: Gtk.SortType.DESCENDING}
    filter_rules = {}
    rule_box = None
    tmtc = {0: 'TM', 1: 'TC'}
    w_r = {0: 'R', 1: 'W'}
    autoscroll = 1
    autoselect = 1
    sort_order = Gtk.SortType.ASCENDING
    pckt_queue = None
    queues = {}
    row_colour = ''
    colour_filters = {}
    active_pool_info = None  # type: Union[None, ActivePoolInfo]
    decoding_type = 'PUS'
    live_signal = {True: '[LIVE]', False: None}
    # loaded_pools = {}
    currently_selected = set()
    shift_range = [1, 1]
    active_row = None
    selected_row = 1
    cursor_path = 0
    pool_refresh_rate = 1 / 10.
    last_decoded_row = None
    row_buffer_n = 100
    main_instance = None
    first_run = True
    shown_all_rows = []
    shown_lock = threading.Lock()
    shown_thread = {}
    shown_loaded = False
    shown_limit = 0
    only_scroll = False

    def __init__(self, cfg=None, pool_name=None, cfilters='default', standalone=False):
        Gtk.Window.__init__(self, title="Pool View", default_height=800,
                            default_width=1100)

        #if not pool_name:
        #    self.active_pool_info = ActivePoolInfo(None,None,None,None)
        self.cnt = 0
        self.active_pool_info = ActivePoolInfo(None, None, None, None)
        self.set_border_width(2)
        self.set_resizable(True)
        self.set_default_size(1150, 1280)
        # self.set_position(Gtk.WindowPosition.CENTER)
        self.set_gravity(Gdk.Gravity.NORTH_WEST)

        Notify.init('PoolViewer')

        #self.dbustype = dbus.SessionBus()
        if cfg is None:
            self.cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))
        else:
            self.cfg = cfg

        #self.cfg.source = confignator.get_option('config-files', 'ccs').split('/')[-1] # Used to write into the config file

        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True, position=400)

        self.statusbar = Gtk.Statusbar()
        self.statusbar.set_halign(Gtk.Align.END)
        grid = Gtk.VBox()
        grid.pack_start(self.paned, 1, 1, 0)
        grid.pack_start(self.statusbar, 0, 0, 0)
        self.add(grid)

        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(False)
        self.paned.add2(self.grid)

        self.set_events(self.get_events() | Gdk.EventMask.SCROLL_MASK)

        # self.dbcon = connect_to_db()

        self.treebox = self.create_treeview()

        self.grid.attach(self.treebox, 0, 3, 1, 12)

        self.create_pool_managebar()
        self.grid.attach(self.pool_managebar, 0, 0, 1, 1)

        self.filterbar = self.create_filterbar()
        self.grid.attach(self.filterbar, 0, 1, 1, 1)

        self._add_rulebox()

        dataview = self.create_tm_data_viewer()
        self.paned.add1(dataview)

        self.set_keybinds()
        self.key_held_pressed = False

        sets = self.get_settings()
        sets.set_property('gtk-error-bell', False)

        if self.cfg.has_section('ccs-pool_colour_filters') and (cfilters is not None):
            for cfilter in json.loads(self.cfg['ccs-pool_colour_filters'][cfilters]):
                self.add_colour_filter(cfilter)

        self.rgba_black = Gdk.RGBA()
        self.rgba_black.parse('black')

        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        #self.check_pmgr_pool()

        #self.show_all()

        # Session Maker
        # self.session_factory = cfl.scoped_session

        # Check if pool from poolmanagers should be loaded, default is True
        # No done in connect_to_all function
        #check_for_pools = True
        #if '--not_load' in sys.argv:
        #    check_for_pools = False
        #if check_for_pools:
        #    self.set_pool_from_pmgr()

        # Set up the logging module
        self.logger = cfl.start_logging('Poolviewer')

        if pool_name is not None:
            self.set_pool(pool_name)

        self.stored_packet = []

        self.connect("delete-event", self.quit_func)
        self.show_all()

        '''
        if standalone is not False:
            # This is the Gtk.main command which is used, therefore D_Bus has to be started here
            # Tell DBus to use the Gtk Main loop
            # Get the DBus Name from the cfg file and set up the Bus
            Bus_Name = self.cfg.get('ccs-dbus_names', 'poolviewer')
            DBusGMainLoop(set_as_default=True)
            DBus_Basic.MessageListener(self, Bus_Name, sys.argv)

            # Set up the logging module
            self.logger = cfl.start_logging('Poolviewer')

            if pool_name is not None:
                self.set_pool(pool_name)
            elif check_for_pools:
                self.set_pool_from_pmgr()

            self.connect("delete-event", self.quit_func)
            self.show_all()

            Gtk.main()

        else:
            # Set up the logging module
            self.logger = cfl.start_logging('Poolviewer')

            if pool_name is not None:
                self.set_pool(pool_name)
            elif check_for_pools:
                self.set_pool_from_pmgr()

            self.connect("delete-event", self.quit_func)
            self.show_all()
        '''

    def checking(self):
        self.adj.set_value(60)
        return

    def quit_func(self, *args):
        #Check if Poolmanager is running otherwise just close viewer
        if not cfl.is_open('poolmanager', cfl.communication['poolmanager']):
            self.close_terminal_connection()
            self.update_all_connections_quit()
            Gtk.main_quit()
            return False

        pmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        # Check if Gui and only close poolviewer if it is
        if cfl.Variables(pmgr, 'gui_running'):
            self.close_terminal_connection()
            self.update_all_connections_quit()
            Gtk.main_quit()
            return False

        #Ask if Poolmanager should be cloosed too
        ask = UnsavedBufferDialog(parent=self, msg='Response NO will keep the Poolmanager running in the Background')
        response = ask.run()

        if response == Gtk.ResponseType.NO:
            Notify.Notification.new('Poolmanager is still running without a GUI').show()

        elif response == Gtk.ResponseType.CANCEL:
            ask.destroy()
            return True

        else:
            self.close_terminal_connection()
            self.update_all_connections_quit()
            ask.destroy()
            pmgr.Functions('quit_func_pv', ignore_reply=True)
            Gtk.main_quit()
            return False

        self.close_terminal_connection()
        self.update_all_connections_quit()
        ask.destroy()
        Gtk.main_quit()
        return False

    def close_terminal_connection(self):
        # Try to tell terminal in the editor that the variable is not longer availabe
        ed_con = []
        for service in dbus.SessionBus().list_names():
            if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                editor = cfl.dbus_connection(service[0:-1].split('.')[1], service[-1])
                if self.main_instance == editor.Variables('main_instance'):
                    nr = self.my_bus_name[-1]
                    if nr == str(1):
                        nr = ''
                    editor.Functions('_to_console_via_socket', 'del(pv'+str(nr)+')')
        return

    def update_all_connections_quit(self):
        '''
        Tells all running applications that it is not longer availabe and suggests another main communicator if one is
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

    def send_cfg(self):
        return self.cfg

    def set_pool_from_pmgr(self):
        try:
            poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
            pools = cfl.Functions(poolmgr, 'loaded_pools_export_func')
            for pool in pools:
                self.set_pool(pool[0])
        except:
            return

    def set_pool(self, pool_name, pmgr_pools=None, instance=None):
        if not pmgr_pools:
            try:
                poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
                if not poolmgr:
                    raise TypeError
                self.Active_Pool_Info_append(cfl.Dictionaries(poolmgr, 'loaded_pools', pool_name))
                cfl.Functions(poolmgr, 'loaded_pools_func', self.active_pool_info.pool_name, self.active_pool_info)
            except:
                if '/' in pool_name:
                    pool_name = pool_name.split('/')[-1]

                # change_error
                attribute = [str(os.path.realpath(pool_name)), int(round(time.time())), str(pool_name), False]
                self.Active_Pool_Info_append(attribute)
        else:
            for pool in pmgr_pools:
                if pool_name == pool[2]:
                    self.Active_Pool_Info_append(list(pool))
            #self.Active_Pool_Info_append(pmgr_pools[pool_name])
        #print(self.active_pool_info)
        #print(type(self.active_pool_info))


        self._set_pool_list_and_display(instance=instance)
        if self.active_pool_info.live:
            self.refresh_treeview(pool_name)
            # print('THIS STEP IS NOT NEEDED ANYMORE')
            # if self.pool is None:
            #     self.pool = pool
            #
            # thread = threading.Thread(target = self.update_packets)
            # thread.daemon = True
            # thread.start()
        return
    # def set_queue(self, pool_name, pckt_queue):
    #
    #     self.queues.update({pool_name: pckt_queue})
    #
    #     model = self.pool_selector.get_model()
    #
    #     iter = model.append([pool_name])
    #
    #     if model.iter_n_children() == 1:
    #         self.pool_selector.set_active_iter(iter)
    #         self.pool_liststore.clear()
    #         self.pckt_queue = pckt_queue
    #         self.pool_name = pool_name

    # def update_packets_worker(self):

    #     pckt_queue = self.pckt_queue
    #     if pckt_queue is None or self.pool is None or pckt_queue.empty():
    #         return True

    #     print("Worker resumes...")
    #     unpack_pus = self.pool.unpack_pus
    #     getpq = pckt_queue.get
    #     appendls = self.pool_liststore.append
    #     cuctime = self.pool.cuc_time_str

    #     print("Worker resumes 2...")
    #     # self.treeview.set_model(None)
    #     self.treeview.set_model(self.pool_liststore)
    #     self.treeview.freeze_child_notify()
    #     pckt_count = 0
    #     while not pckt_queue.empty():
    #         (seq, pckt) = getpq()
    #         tm = unpack_pus(pckt)
    #         appendls([seq] + [self.tmtc[tm[1]]] + [tm[3]] + tm[5:7] + tm[10:13] + [cuctime(tm)] + [tm[-2]])
    #         pckt_count+=1
    #         if (pckt_count % 128) == 127:
    #             # self.treeview.set_model(self.pool_liststore)
    #             self.treeview.thaw_child_notify()
    #             print("Added:", pckt_count, "...")
    #             return True
    #
    #     self.treeview.thaw_child_notify()
    #     print("Completed - Added:", pckt_count, "\n")
    #     # self.change_cursor(self.scrolled_treelist.get_window(),'default')
    #     return True

    def change_communication(self, application, instance=1, check=True):
        # If it is checked that both run in the same project it is not necessary to do it again
        if check:
            conn = cfl.dbus_connection(application, instance)
            # Both are not in the same project do not change

            if not cfl.Variables(conn, 'main_instance') == self.main_instance:
                print('Both are not running in the same project, no change possible')
                self.logger.info('Application {} is not in the same project as {}: Can not communicate'.format(
                    self.my_bus_name, self.cfg['ccs-dbus_names'][application] + str(instance)))
                return

        cfl.communication[application] = int(instance)
        return

    def get_communication(self):
        return cfl.communication

    def connect_to_all(self, My_Bus_Name, Count):
        self.my_bus_name = My_Bus_Name
        #print(My_Bus_Name)
        # Look if other applications are running in the same project group
        our_con = []
        #Look for all connections starting with com, therefore only one loop over all connections is necessary
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
                        conn.Functions('change_communication', self.my_bus_name.split('.')[1], self.my_bus_name [-1], False)

        if not cfl.communication[self.my_bus_name.split('.')[1]]:
            cfl.communication[self.my_bus_name.split('.')[1]] = int(self.my_bus_name[-1])

        # Connect to the Terminal
        if Count == 1:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "pv = dbus.SessionBus().get_object('" + str(My_Bus_Name)
                                     + "', '/MessageListener')")

        else:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "pv" +str(Count)+ " = dbus.SessionBus().get_object('" +
                                     str(My_Bus_Name) + "', '/MessageListener')")

        #####
        # Check if pool from poolmanagers should be loaded, default is True
        check_for_pools = True
        if '--not_load' in sys.argv:
            check_for_pools = False

        if check_for_pools:
            self.set_pool_from_pmgr()

        return

    def add_colour_filter(self, colour_filter):
        seq = len(self.colour_filters.keys())
        rgba = Gdk.RGBA()
        rgba.parse(colour_filter['colour'])
        colour_filter['colour'] = rgba
        self.colour_filters.update({seq: colour_filter})

    def update_colour_filter(self, index, colour_filter):
        self.colour_filters.update({index: colour_filter})

    def del_colour_filter(self, filter_index):
        self.colour_filters.pop(filter_index)

    def get_colour_filters(self):
        return self.colour_filters

    def text_colour(self, column, cell, tree_model, iter, data=None):

        # labels = list(map(list, zip(*self.column_labels)))[0]

        """ this is a bit stupid and inefficient, but it does the job """

        if column == self.treeview.get_column(0):
            labels = [x[0] for x in self.column_labels[self.decoding_type]]

            self.row_colour = self.rgba_black
            for filter in self.colour_filters:
                d = {}
                cf = self.colour_filters[filter].copy()
                cf.pop('colour')

                for key in cf.keys():
                    d.update({key: tree_model[iter][labels.index(key)]})

                if d == cf:
                    self.row_colour = self.colour_filters[filter]['colour']

        # cell.set_property('foreground', self.row_colour)

        cell.set_property('foreground-rgba', self.row_colour)

    def text_colour2(self, column, cell, tree_model, iter, data=None):
        if column == self.treeview.get_column(0):
            labels = [x[0] for x in self.column_labels[self.decoding_type]]

            d = {key: tree_model[iter][labels.index(key)] for key in labels[1:-2]}  # skip idx, time and data fields

            self.row_colour = self.rgba_black
            for f in self.colour_filters:
                cf = self.colour_filters[f].copy()
                colour = cf.pop('colour')

                if cf.items() <= d.items():
                    self.row_colour = colour
                    break
                else:
                    continue

        cell.set_property('foreground-rgba', self.row_colour)

    def create_treeview(self):

        self.pool_liststore = self.create_liststore()

        self.treeview = Gtk.TreeView()
        self.treeview.set_model(self.pool_liststore)
        self.treeview.set_rubber_banding(False)
        self.treeview.set_activate_on_single_click(True)
        # self.treeview.set_fixed_height_mode(True)

        self.create_treeview_columns()

        self.scrolled_treelist = Gtk.ScrolledWindow()
        self.scrolled_treelist.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.ALWAYS)
        self.scrolled_treelist.set_overlay_scrolling(False)
        self.scrolled_treelist.set_min_content_height(235)
        self.scrolled_treelist.set_vexpand(True)

        self.scrolled_treelist.add(self.treeview)
        self.scrolled_treelist.add_events(Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.scrolled_treelist.add_events(Gdk.EventMask.SCROLL_MASK)

        self.connect('configure-event', self.set_number_of_treeview_rows)
        # self.connect('check-resize', self.set_number_of_treeview_rows)
        self.connect('window-state-event', self.resize_treeview)

        self.treeview.connect('size-allocate', self.treeview_update)
        # self.treeview.connect('size-allocate', self.set_tm_data_view)
        self.treeview.connect('key-press-event', self.key_pressed)
        # self.treeview.connect('key-press-event', self.set_tm_data_view)
        # self.treeview.connect('key-press-event', self.set_currently_selected)
        self.treeview.connect('button-release-event', self.set_currently_selected)
        self.treeview.connect('button-press-event', self._set_current_row)

        # something like that
        # self.scrolled_treelist.connect('edge-reached', self.edge_reached)
        # self.scrolled_treelist.connect('edge-overshot', self.edge_reached)
        self.scrolled_treelist.connect('scroll-event', self.scroll_event)
        # self.scrolled_treelist.connect('scroll-event', self.reselect_rows)
        # self.scrolled_treelist.connect('button-release-event', self.scroll_event)
        self.scrolled_treelist.connect('scroll-child', self.scroll_child)
        # self.scrolled_treelist.get_vscrollbar().connect('value-changed', self.scroll_bar)
        self.scrolled_treelist.get_vscrollbar().set_visible(False)

        self.selection = self.treeview.get_selection()
        self.selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        # self.selection.connect('changed', self.tree_selection_changed)
        self.selection.connect('changed', self.set_tm_data_view)
        # self.selection.connect('changed', self.unselect_bottom)

        scrollbar = Gtk.VScrollbar()
        self.adj = scrollbar.get_adjustment()
        # get size of tmpool

        if self.active_pool_info.pool_name is not None:
            self.adj.set_upper(self.count_current_pool_rows())
        self.adj.set_page_size(25)
        scrollbar.connect('value_changed', self._on_scrollbar_changed, self.adj, False)
        scrollbar.connect('button-press-event', self.scroll_bar)
        # scrollbar.connect('value_changed', self.reselect_rows)

        hbox = Gtk.HBox()
        hbox.pack_start(self.scrolled_treelist, 1, 1, 0)
        hbox.pack_start(scrollbar, 0, 0, 0)

        return hbox

    def create_treeview_columns(self):
        for i, (column_title, align) in enumerate(self.column_labels[self.decoding_type]):
            render = Gtk.CellRendererText(xalign=align)
            if column_title == "Data":
                render.set_property('font', 'Monospace')

            column = Gtk.TreeViewColumn(column_title, render, text=i)
            column.set_cell_data_func(render, self.text_colour2)

            # column.set_sort_column_id(i)
            column.set_clickable(True)
            column.set_resizable(True)
            column.connect('clicked', self.column_clicked)
            self.treeview.append_column(column)

    def _set_current_row(self, widget=None, event=None):
        x, y = event.x, event.y
        path = widget.get_path_at_pos(x, y)
        if path is not None:
            self.active_row = widget.get_model()[path[0]][0]
            self.set_shift_range(self.active_row)
            self.autoselect = 0
            self.set_tm_data_view()

    def set_shift_range(self, row):
        self.shift_range[0] = self.shift_range[1]
        self.shift_range[1] = row

    # @delayed(10)
    def set_number_of_treeview_rows(self, widget=None, allocation=None):
        # alloc = widget.get_allocation()
        height = self.treeview.get_allocated_height()
        cell = self.treeview.get_columns()[0].cell_get_size()[-1] + 2
        nlines = height // cell
        self.adj.set_page_size(nlines-3)
        # self._scroll_treeview()
        self.reselect_rows()

    def resize_treeview(self, widget, event):
        if (Gdk.WindowState.MAXIMIZED == event.new_window_state):
            self.set_number_of_treeview_rows()

    # @delayed(10)
    def _on_scrollbar_changed(self, widget=None, adj=None, force=True):
        if self.autoscroll and not force:
            return
        if self.only_scroll:    # Stops second scroll event after scrollbar zeiger was reset,if scrolled by scroll wheel
            return
        self.offset = int(self.adj.get_value())
        self.limit = int(self.adj.get_page_size())
        #self.feed_lines_to_view(
        #    self.fetch_lines_from_db(offset=self.offset, limit=self.limit))
        self.fetch_lines_from_db(offset=self.offset, limit=self.limit, force_import=True)
        self.reselect_rows()

    def count_current_pool_rows(self, pool_info=None):
        if pool_info is not None:
            self.Active_Pool_Info_append(pool_info)

        if self.active_pool_info is None:
            return 0
        new_session = self.session_factory_storage
        rows = new_session.query(
            Telemetry[self.decoding_type]
        ).join(
            DbTelemetryPool,
            Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename
        )
        if rows.first() is None:
            cnt = 0
        else:
            cnt = rows.order_by(Telemetry[self.decoding_type].idx.desc()).first().idx
        new_session.close()
        return cnt

    def get_current_pool_rows(self, dbsession=None):
        if self.active_pool_info is None:
            return 0
        new_session = self.session_factory_storage
        rows = new_session.query(
            Telemetry[self.decoding_type]
        ).join(
            DbTelemetryPool,
            Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename
        )
        new_session.close()
        return rows


    def fetch_lines_from_db(self, offset=0, limit=None, sort=None, order='asc', buffer=10, rows=None, scrolled=False,
                            force_import=False):
        """
        Reads the packages from the Database and shows it according to the position of the scrollbar
        @param offset: Index of first line - 1
        @param limit: How many packages should be displayed
        @param sort: If the packages are sorted in any way
        @param order: In which order the packages should be displayed
        @param buffer: How many packages should be loaded but are not shown
        @param rows: Show these rows if given
        @param scrolled: True if view is scrolled
        @param force_import: Import all rows again from the Database
        @return: -
        """

        if self.active_pool_info is None:
            return
        limit = self.adj.get_page_size() if not limit else limit  # Check if a limit is given

        sort = False
        # Check if the rows should be shown in any specific order
        for col in self.tm_columns[self.decoding_type]:
            if self.tm_columns[self.decoding_type][col][1] in [1,2]:
                sort = True

        position = int(len(self.shown_all_rows) - self.adj.get_page_size())
        if position < 0:
            position = 0
        #offset = 0 if offset < 0 else offset
        self.shown_lock.acquire()   # Thread lock to changes shared variables between threads

        # If the offset is still in buffer range get new packages from buffer and reload the buffer in a thread, if autoscroll dont use buffer (makes no sense)
        #if self.shown_loaded and offset in range(self.shown_upper_limit, self.shown_offset+buffer) and not force_import:
        if self.shown_loaded and offset in range(self.shown_all_rows[0][0], self.shown_all_rows[position][0]+1) and not force_import and not sort and not self.autoscroll:
            if self.filter_rules_active and scrolled:
                for x, row in enumerate(self.shown_all_rows, start=0):
                    if row[0] >= self.shown_offset:
                        position_shown_offset = x
                        break
                for x, row in enumerate(self.shown_all_rows, start=0):
                    if row[0] >= self.offset:
                        position_offset = x
                        break

                shown_diff = position_offset - position_shown_offset
            else:
                shown_diff = offset - self.shown_offset     # How far has been scrolled

            if isinstance(self.shown_diff, int):
                self.shown_diff += shown_diff   # Thread is already loading, load additional ones
            else:
                self.shown_diff = shown_diff    # New thread knows how much should be loaded
        elif self.shown_loaded and self.shown_offset and abs(self.shown_offset-self.offset) < buffer and sort and not force_import and not self.autoscroll: # If sorted and inside buffer
            shown_diff = offset - self.shown_offset

            if isinstance(self.shown_diff, int):
                self.shown_diff += shown_diff   # Thread is already loading, load additional ones
            else:
                self.shown_diff = shown_diff    # New thread knows how much should be loaded

        else:   # Scrolled outside of loaded buffer, reload all shown packages
            self.shown_offset = offset  # Index of the first package shown, does not update if buffer does not update
            self.shown_diff = None  # How far hs been scrolled
            shown_diff = None
            self.shown_upper_limit = 0 if (offset - buffer) < 0 else offset - buffer  # Upper limit of buffer

        local_offset = 0 if offset - buffer < 0 else offset - buffer
        # If the limit changes reload all packages, important for end of pool and if pool is loaded during starting process
        if self.shown_limit != (limit + 2*buffer):
            self.shown_limit_changed = True
        else:
            self.shown_limit_changed = False

        self.shown_limit = int(limit + 2*buffer)     # Length of all loaded packages including buffer
        self.shown_buffer = buffer  # Buffer length
        self.shown_lock.release()
        if shown_diff == 0 and not rows and not self.shown_limit_changed:   # If nothing changed do nothing
            return  # Necessary, sometimes function is called from different plays, but should not be executed multiple times
        elif shown_diff and not rows and not self.shown_limit_changed:  # Update buffer and scroll within buffer
            # If no thread is running start one to update the buffer
            self.shown_lock.acquire()
            if not self.shown_thread:
                t_shown_rows = threading.Thread(target=self.update_shown_buffer)
                t_shown_rows.daemon = True
                t_shown_rows.start()
                self.shown_thread.update({t_shown_rows.getName(): True})
            self.shown_lock.release()
                # self.shown_thread_running = True
            # Start the updating from buffer

            self.feed_lines_to_view(shown_diff)
            return
        ####### Reload all packages
        # If a thread is still loading, tell it to not add them to the buffer
        self.shown_lock.acquire()
        if self.shown_thread:
            self.shown_thread = {}

        self.shown_lock.release()

        # Set up the query
        if rows is None:
            # Combine the Storage Tables and filter only the packages for the given pool
            new_session = self.session_factory_storage
            rows = new_session.query(
                Telemetry[self.decoding_type]
            ).join(
                DbTelemetryPool,
                Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
            ).filter(
                DbTelemetryPool.pool_name == self.active_pool_info.filename
            )
            new_session.close()

        sorted = False
        # Check if the rows should be shown in any specific order
        for col in self.tm_columns[self.decoding_type]:
            if self.tm_columns[self.decoding_type][col][1] == 1:
                rows = rows.order_by(self.tm_columns[self.decoding_type][col][0], Telemetry[self.decoding_type].idx)
                sorted = True
            elif self.tm_columns[self.decoding_type][col][1] == 2:
                rows = rows.order_by(self.tm_columns[self.decoding_type][col][0].desc(), Telemetry[self.decoding_type].idx.desc())
                sorted = True

        # Check if a filter has been applied
        if self.filter_rules_active:
            rows = self._filter_rows(rows)

            # if self.tm_columns[col][2] is not None:
            #     try:
            #         rows = rows.filter(self.tm_columns[col][0] == self.tm_columns[col][2])
            #     except:
            #         print("filtering error")
        # self.adj.set_upper(rows.count())
        # If sorted use different query, this is slower but there is no other possibility
        if sorted:
            # rows = rows[offset:offset+limit]
            #rows = rows.options(load_only()).yield_per(1000).offset(offset).limit(limit)
            if local_offset < 1:    # No buffer needed on the upper side if index is 1
                rows = rows.options(load_only()).yield_per(1000).offset(local_offset).limit(self.shown_limit - self.shown_buffer + offset)
            else:
                rows = rows.options(load_only()).yield_per(1000).offset(local_offset).limit(self.shown_limit)
            #rows = rows.offset(local_offset).limit(self.shown_limit)
        else:   # Query is faster this way, only possible if not sorted
            #rows = rows.filter(DbTelemetry.idx > offset).limit(limit)  # .all
            if local_offset < 1:    # No buffer needed on the upper side if index is 1
                rows = rows.filter(Telemetry[self.decoding_type].idx > local_offset).limit(self.shown_limit - self.shown_buffer + offset) # .all()
            else:
                rows = rows.filter(Telemetry[self.decoding_type].idx > local_offset).limit(self.shown_limit) # .all()
            #rows = rows.offset(local_offset).limit(self.shown_limit)


        self.treeview.freeze_child_notify()
        #starttime = time.time()
        self.reload_all_shown_rows(rows)    # Load all rows
        #print('TIME:::', time.time()-starttime)
        self.treeview.thaw_child_notify()


        return

    def _filter_rows(self, rows):
        
        def f_rule(x):
            if x[1] == '==':
                return x[0] == x[2]
            elif x[1] == '!=':
                return x[0] != x[2]
            elif x[1] == '<':
                return x[0] < x[2]
            elif x[1] == '>':
                return x[0] > x[2]
            
        # for fid in self.filter_rules:
        #     ff = self.filter_rules[fid]
        #     if ff[1] == '==':
        #         rows = rows.filter(ff[0] == ff[2])
        #     elif ff[1] == '!=':
        #         rows = rows.filter(ff[0] != ff[2])
        #     elif ff[1] == '<':
        #         rows = rows.filter(ff[0] < ff[2])
        #     elif ff[1] == '>':
        #         rows = rows.filter(ff[0] > ff[2])

        first = 1
        for fil in self.filter_rules.values():
            if first:
                rule = f_rule(fil)
                first = 0
            elif fil[3] == 'AND':
                rule = rule & f_rule(fil)
            elif fil[3] == 'OR':
                rule = rule | f_rule(fil)

        # filter_chain = [f_rule(self.filter_rules[ff]) for ff in self.filter_rules]
        if not first:
            rows = rows.filter(rule)

        return rows

    def feed_lines_to_view(self, shown_diff):
        """
        Updates the shown packages from the buffer
        @param shown_diff: how many lines has been scrolled
        @return: -
        """

        self.treeview.freeze_child_notify()
        #self.pool_liststore.clear()
        #something = []
        #for i in self.shown_all_rows:
        #    something.append(i[0])
        sorted = False
        for col in self.tm_columns[self.decoding_type]:
            if self.tm_columns[self.decoding_type][col][1] in [1,2]:
                sorted = True

        # Empty the liststore and refill it from buffer
        #x = 0
        #for tm_row in self.shown_all_rows:  # Loop over all loaded packages and only use the once in the view area
        #    if x in range(self.shown_offset + shown_diff - self.shown_upper_limit,
        #                  self.shown_offset + shown_diff + int(self.adj.get_page_size()) - self.shown_upper_limit):
        #        liststore_rows.append(tm_row)
        #    x += 1
        if sorted:
            liststore_rows = []
            #print(self.shown_all_rows)
            first_row_idx = self.pool_liststore[0][0]
            position = False
            # Check at which position should be started to fill in
            for x, row in enumerate(self.shown_all_rows, start=0):
                if row[0] == first_row_idx:
                    position = x
                    break
            if not position:
                self.fetch_lines_from_db(force_import=True)

            # Only load the packages that should be shown
            for count, tm_row in enumerate(self.shown_all_rows):
                if count in range(position+shown_diff, position+shown_diff+int(self.adj.get_page_size())):
                    liststore_rows.append(tm_row)


            if len(liststore_rows) < self.adj.get_page_size():
                liststore_rows = self.shown_all_rows[-int(self.adj.get_page_size()):]
            self.pool_liststore.clear()


        else:
            self.pool_liststore.clear()
            liststore_rows = []
            #Check at which position should be started to fill in
            for x, row in enumerate(self.shown_all_rows, start=0):
                if row[0] >= self.offset:
                    position = x
                    break

            # Only load the packages that should be shown
            for count, tm_row in enumerate(self.shown_all_rows):
                if tm_row[0] >= self.offset and count <= self.adj.get_page_size()+position:
                    liststore_rows.append(tm_row)


            if len(liststore_rows) < self.adj.get_page_size():
                liststore_rows = self.shown_all_rows[-int(self.adj.get_page_size()):]
        #something = []
        for row in liststore_rows:
            #something.append(row[0])
            self.pool_liststore.append(row)
        #print(something)
            #print(something, self.shown_offset, self.shown_upper_limit)
        self.treeview.thaw_child_notify()   # Tell GTk to reload

        '''
        # ndel = len(self.pool_liststore)
        unfiltered_rows = dbrows[2]
        sorted = dbrows[1]
        dbrows = dbrows[0]
        if not dbrows:
            return

        self.shown_lock.acquire()
        #self.treeview.freeze_child_notify()
        #self.pool_liststore.clear()

        if self.shown_diff or self.shown_diff == 0:
            if self.shown_diff > 0:
                self.treeview.freeze_child_notify()
                self.pool_liststore.clear()
                if sorted:
                    dbrows = unfiltered_rows.offset(self.shown_offset + self.shown_limit - self.shown_buffer).limit(self.shown_diff)
                else:
                    dbrows = unfiltered_rows.filter(DbTelemetry.idx > (self.shown_offset + self.shown_limit - self.shown_buffer)).limit(
                        self.shown_diff)

                #for row in self.pool_liststore:
                #    if row[0] == range(self.shown_upper_limit, self.shown_upper_limit - self.shown_diff):
                #        self.pool_liststore.remove(row.iter)

                if self.shown_offset > self.shown_buffer:
                    del self.shown_all_rows[0:self.shown_diff]

                x = 0
                for tm_row in self.shown_all_rows:
                    if x in range(self.shown_offset + self.shown_diff - self.shown_upper_limit,
                                  self.shown_offset + self.shown_diff + int(
                                      self.adj.get_page_size()) - self.shown_upper_limit):
                        self.pool_liststore.append(tm_row)
                    x += 1

                if not self.dbrows_list:
                    t_shown_rows = threading.Thread(target=self.update_shown_buffer)
                    t_shown_rows.daemon = True
                    t_shown_rows.start()

                self.dbrows_list.append([dbrows, self.shown_diff])
                self.treeview.thaw_child_notify()

            elif self.shown_diff == 0:
                pass

            else:
                self.treeview.freeze_child_notify()
                self.pool_liststore.clear()
                if sorted:
                    if self.shown_upper_limit > abs(self.shown_diff):
                        dbrows = unfiltered_rows.offset((self.shown_upper_limit + self.shown_diff)).limit(
                            self.shown_diff * -1)
                    else:
                        dbrows = unfiltered_rows.offset(0).limit(self.shown_diff * -1)
                else:
                    if self.shown_upper_limit > abs(self.shown_diff):
                        dbrows = unfiltered_rows.filter(
                            DbTelemetry.idx > (self.shown_upper_limit + self.shown_diff)).limit(
                            self.shown_diff * -1)
                    else:
                        dbrows = unfiltered_rows.filter(DbTelemetry.idx > 0).limit(self.shown_diff * -1)

                #for row in self.pool_liststore:
                #    if row[0] == range(self.offset + self.shown_limit - self.shown_buffer + self.shown_diff,
                #                       self.offset + self.shown_limit - self.shown_buffer):
                #        self.pool_liststore.remove(row.iter)

                self.shown_all_rows = self.shown_all_rows[:self.shown_diff]

                if not self.dbrows_list:
                    t_shown_rows = threading.Thread(target=self.update_shown_buffer)
                    t_shown_rows.daemon = True
                    t_shown_rows.start()

                x = 0
                for tm_row in self.shown_all_rows:
                    if x in range(self.shown_offset + self.shown_diff - self.shown_upper_limit,
                                  self.shown_offset + self.shown_diff + int(self.adj.get_page_size()) - self.shown_upper_limit):
                        self.pool_liststore.append(tm_row)
                    #if x in range(self.shown_offset + self.shown_diff - self.shown_upper_limit,
                    #              self.shown_offset - self.shown_upper_limit):
                        #self.pool_liststore.insert(0, tm_row)
                    x += 1
                self.dbrows_list.append([dbrows, self.shown_diff])
                self.treeview.thaw_child_notify()

            self.shown_offset = 0 if self.shown_offset < 0 else self.shown_offset + self.shown_diff
            self.shown_upper_limit = 0 if (self.shown_offset - self.shown_buffer) < 0 else self.shown_offset -self.shown_buffer
            #thread1 = threading.Thread(target=self.update_shown_buffer, kwargs={'rows': dbrows})
            #thread1.daemon = True
            #thread1.start()

        else:
            self.treeview.freeze_child_notify()
            self.pool_liststore.clear()
            self.reload_all_shown_rows(dbrows)
            self.dbrows_list = []
            self.treeview.thaw_child_notify()
        #print(time.time()-starttime)
        # del self.pool_liststore[:ndel]
        #self.treeview.thaw_child_notify()
        self.shown_lock.release()
        self.loaded = 1
        return
        '''
        return

    def reload_all_shown_rows(self, dbrows):
        """
        Reload all Packages (shown and in buffer) from the Database
        @param dbrows: The query to get the packages from the Database
        @return: -
        """
        self.filter_spinner.start()
        #self.shown_all_rows = []    # Empty buffer
        self.shown_all_rows = self.format_loaded_rows(dbrows)
        liststore_rows = []    # Empty liststore

        #for tm in dbrows:   # Get all rows from the query, (this step can take some time if filter is active)
        #    tm_row = [tm.idx, self.tmtc[tm.is_tm], tm.apid, tm.seq, tm.len_7, tm.stc, tm.sst, tm.destID,
        #              str(tm.timestamp), tm.data.hex()]     # Get needed information
        x = 0
        for tm_row in self.shown_all_rows:
            # Check if package should be added to buffer or if it should be shown
            if x in range(self.shown_offset - self.shown_upper_limit,
                          self.shown_offset + (self.shown_limit - 2*self.shown_buffer) - self.shown_upper_limit):
                # tm_row = [tm.idx, self.tmtc[tm.is_tm], tm.apid, tm.seq, tm.len_7, tm.stc, tm.sst, tm.destID,
                #          str(tm.timestamp), tm.data.hex()]
                liststore_rows.append(tm_row)
            #self.shown_all_rows.append(tm_row)
            x += 1
        self.pool_liststore.clear()

        #something = []
        #for i in liststore_rows:
        #    something.append(i[0])
        #print(something)

        #if len(liststore_rows) < int(self.adj.get_page_size()):
        #    print(1)
        #    liststore_rows = self.shown_all_rows[-int(self.adj.get_page_size()):]

        for tm in liststore_rows:
            self.pool_liststore.append(tm)
        if liststore_rows:
            self.shown_loaded = True
        else:
            self.shown_loaded = False
        self.filter_spinner.stop()
        return


    def update_shown_buffer(self):
        """
        Update the buffer for the shown packages in a seperate thread
        @return:
        """
        # Run until told otherwise
        while True:
            # Get all needed global variables to local variabels so that there is no confilct
            self.shown_lock.acquire()
            shown_offset = self.shown_offset
            shown_diff = self.shown_diff
            shown_upper_limit = self.shown_upper_limit - 2
            shown_limit = self.shown_limit
            shown_buffer = self.shown_buffer
            offset = self.offset

            if not shown_diff:  # If there has been no change since the last update close the thread
                try:
                    self.shown_thread = {}
                except:
                    pass
                self.shown_lock.release()
                break
            self.shown_lock.release()

            # Make the query to load packages from the Database
            new_session = self.session_factory_storage
            # Join both storage table from the database and filter all package that belong to the given pool
            rows = new_session.query(
                Telemetry[self.decoding_type]
            ).join(
                DbTelemetryPool,
                Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
            ).filter(
                DbTelemetryPool.pool_name == self.active_pool_info.filename
            )

            sorted = False
            # Check if the packages should be shown in a specific order
            for col in self.tm_columns[self.decoding_type]:
                if self.tm_columns[self.decoding_type][col][1] == 1:
                    rows = rows.order_by(self.tm_columns[self.decoding_type][col][0], Telemetry[self.decoding_type].idx)
                    sorted = True
                elif self.tm_columns[self.decoding_type][col][1] == 2:
                    rows = rows.order_by(self.tm_columns[self.decoding_type][col][0].desc(), Telemetry[self.decoding_type].idx.desc())
                    sorted = True

            # Check if a filter has applied
            if self.filter_rules_active:
                rows = self._filter_rows(rows)
                #filtered = True
            if shown_diff < 0:  # Scrolled up
                reverse = True
                # Complete the query to only get the few packages which are actually needed to update the buffer
                if sorted:
                    if shown_upper_limit > abs(shown_diff):
                        dbrows = rows.offset(shown_upper_limit + shown_diff).limit(shown_diff * -1)
                    else:
                        dbrows = rows.offset(0).limit(shown_diff * -1)
                else:
                    #if shown_upper_limit > abs(shown_diff):
                    #dbrows = rows.filter(Telemetry[self.decoding_type].idx > (shown_upper_limit + shown_diff + 1)).limit(shown_diff * -1)
                    reverse = False
                    dbrows = rows.filter(Telemetry[self.decoding_type].idx < self.shown_all_rows[0][0]).order_by(Telemetry[self.decoding_type].idx.desc()).limit(shown_diff * -1)

                    #else:
                        #dbrows = rows.filter(Telemetry[self.decoding_type].idx > 0).limit(shown_diff * -1)

                #tm_rows = []
                tm_rows = self.format_loaded_rows(dbrows)
                #print(tm_rows)
                # Get the information from the DB, do this before lock is aquired it can take a bit
                store_rows = []
                if reverse:
                    for tm in reversed(tm_rows):
                        store_rows.append(tm)
                else:
                    for tm in tm_rows:
                        store_rows.append(tm)
                # Get the information of the packages
                #for tm in dbrows:
                #    tm_row = [tm.idx, self.tmtc[tm.is_tm], tm.apid, tm.seq, tm.len_7, tm.stc, tm.sst, tm.destID,
                #              str(tm.timestamp), tm.data.hex()]
                #    tm_rows.append(tm_row)
                self.shown_lock.acquire()
                # Check if the thread should still run, or if it is not longer necessary
                try:
                    a = self.shown_thread[threading.currentThread().getName()]
                except:
                    self.shown_lock.release()
                    break

                # Insert the rows at the very beginning of the buffer (scrolled up)
                for tm in store_rows:
                    self.shown_all_rows.insert(0, tm)

                # Delete the same amount of rows at the very end of the buffer
                #if shown_offset > shown_buffer:
                #if len(self.shown_all_rows) > shown_limit + abs(shown_diff):
                #    self.shown_all_rows = self.shown_all_rows[:shown_diff]
                if len(store_rows) > 0:
                    self.shown_all_rows = self.shown_all_rows[:-len(store_rows)]
                else:
                    if len(self.shown_all_rows) > shown_limit-shown_buffer:
                        self.shown_all_rows = self.shown_all_rows[:-min(abs(len(self.shown_all_rows) - shown_limit + shown_buffer), abs(shown_diff))]
                # Tell how many packages have been done
                self.shown_diff -= shown_diff

            elif shown_diff > 0:    # Scroled down
                # Complete the query to only get the few packages which are actually needed to update the buffer
                if sorted:
                    dbrows = rows.offset(shown_offset + shown_limit - shown_buffer).limit(shown_diff)
                    # dbrows = rows.offset(int(self.shown_all_rows[-1][0])).limit(shown_diff)
                else:
                    # dbrows = rows.filter(Telemetry[self.decoding_type].idx > (shown_offset + shown_limit - shown_buffer)).limit(shown_diff)
                    dbrows = rows.filter(Telemetry[self.decoding_type].idx > int(self.shown_all_rows[-1][0])).limit(shown_diff)

                #tm_rows = []
                tm_rows = self.format_loaded_rows(dbrows)

                # Get the information from the DB, do this before lock is aquired it can take a bit
                store_rows = []
                for tm in tm_rows:
                    store_rows.append(tm)
                # Get the information of the packages
                #for tm in dbrows:
                #    tm_row = [tm.idx, self.tmtc[tm.is_tm], tm.apid, tm.seq, tm.len_7, tm.stc, tm.sst, tm.destID,
                #              str(tm.timestamp), tm.data.hex()]
                #    tm_rows.append(tm_row)
                self.shown_lock.acquire()
                # Check if the thread should still run, or if it is not longer necessary
                try:
                    a = self.shown_thread[threading.currentThread().getName()]
                except:
                    self.shown_lock.release()
                    break

                # Insert the rows at the very end of the buffer (scrolled down)
                for tm in store_rows:
                    self.shown_all_rows.append(tm)

                # Tell how many packages have been done
                self.shown_diff -= shown_diff

                # Delete the same amount of rows at the very beginning of the buffer
                if len(self.shown_all_rows) > shown_limit+shown_diff:
                    del self.shown_all_rows[0:len(tm_rows)]
            else:
                break

            # Update all global variables
            new_session.close()
            #self.shown_offset = 0 if self.shown_offset < 0 else self.shown_offset + shown_diff
            #self.shown_upper_limit = 0 if (self.shown_offset - self.shown_buffer) < 0 else self.shown_offset -self.shown_buffer
            #x = 0
            #for cnt in self.shown_all_rows:
            #    if int(self.shown_offset) <= int(cnt[0]):
            #        break
            #    x += 1

            if sorted:
                self.shown_offset = 0 if self.shown_offset + shown_diff < 0 else self.shown_offset + shown_diff
            else:
                if len(self.shown_all_rows) < shown_limit:
                    self.shown_offset = self.shown_all_rows[shown_buffer - (shown_limit-len(self.shown_all_rows) - 1)][0]
                #if x < shown_buffer:
                #    self.shown_offset = self.shown_all_rows[x+shown_diff][0] if (x+shown_diff) >= 0 else self.shown_all_rows[0][0]
                else:
                    self.shown_offset = self.shown_all_rows[shown_buffer][0]
            #if self.shown_offset <= 0:
            #    self.shown_offset = self.shown_all_rows[shown_diff-1][0]
            #    print(2)
            #else:
            #    self.shown_offset = self.shown_all_rows[x + shown_diff][0] if (x+shown_diff) >= 0 else self.shown_all_rows[0][0]
            #    print(3)
            #self.shown_upper_limit = 0 if (self.shown_offset - self.shown_buffer) < 0 else self.shown_all_rows[0][0]
            if sorted:
                self.shown_upper_limit = 0 if self.shown_offset - shown_buffer < 0 else self.shown_offset - shown_buffer
            else:
                self.shown_upper_limit = self.shown_all_rows[0][0]
            #self.shown_thread = {}
            #self.session_factory_storage.remove()
            #new_session.close()
            self.shown_lock.release()



        '''
        running = True
        self.shown_lock.acquire()
        first_time = True
        for xx in self.dbrows_list:
            dbrows = xx[0]
            count = xx[1]
            if not running:
                self.shown_lock.release()
                break
            if first_time:
                self.shown_lock.release()
                first_time = False

            try:
                for tm in dbrows:
                    tm_row = [tm.idx, self.tmtc[tm.is_tm], tm.apid, tm.seq, tm.len_7, tm.stc, tm.sst, tm.destID,
                              str(tm.timestamp), tm.data.hex()]
                    self.shown_lock.acquire()
                    if self.dbrows_list:
                        if count < 0:
                            self.shown_all_rows.insert(0, tm_row)
                        elif count > 0:
                            self.shown_all_rows.append(tm_row)
                    else:
                        running = False
                    self.shown_lock.release()
            except:
                self.shown_lock.acquire()
                self.loaded = 0
                self.shown_lock.release()
                print(traceback.format_exc())
                print(2)
        self.dbrows_list = []
        '''
        return

    def format_loaded_rows(self, dbrows):
        '''
        This function converts every packet into a readable form
        @param dbrows: The rows gotten from SQL query
        @return: Same Rows in readable form
        '''

        tm_rows = []
        if self.decoding_type == 'PUS':
            for tm in dbrows:
                tm_row = [tm.idx, self.tmtc[tm.is_tm], tm.apid, tm.seq, tm.len_7, tm.stc, tm.sst, tm.destID,
                          str(tm.timestamp), tm.data.hex()]
                tm_rows.append(tm_row)
        elif self.decoding_type == 'RMAP':
            for tm in dbrows:
                tm_row = [tm.idx, self.w_r[tm.write], tm.verify, tm.reply, tm.keystat, tm.taid, tm.addr, tm.datalen,
                          tm.raw.hex()]
                tm_rows.append(tm_row)
        elif self.decoding_type == 'FEE':
            for tm in dbrows:
                tm_row = [tm.idx, tm.type, tm.framecnt, tm.seqcnt, tm.raw.hex()]
                tm_rows.append(tm_row)
        else:
            print('Error in format_loaded_rows_poolviewer')
            self.logger.error('Given Format is not valid')

        return tm_rows

    def tree_selection_changed(self, selection):
        mode = selection.get_mode()
        model, treepaths = selection.get_selected_rows()

        if len(treepaths) > 0:
            path = treepaths[-1]
        else:

            if mode != Gtk.SelectionMode.SINGLE:
                return

            model, treeiter = selection.get_selected()

            if treeiter is None:
                return

            path = model.get_path(treeiter)

        print('SEL', time.time(), path, self.autoscroll, self.autoselect)
        # I will probably be murdered in my sleep for doing this, but it works!
        entry = int(str(path))
        children = self.pool_liststore.iter_n_children() - 1

        if entry == children:
            self.autoselect = 1
        else:
            self.autoselect = 0
        self.set_tm_data_view()

    def column_clicked(self, widget):
        # widget.get_sort_column_id()
        self._toggle_sort_order(widget)
        self._scroll_treeview(force_db_import=True)

    def _toggle_sort_order(self, column):
        colname = column.get_title()
        newstate = self.tm_columns[self.decoding_type][colname][1] = (self.tm_columns[self.decoding_type][colname][1] + 1) % 3
        column.set_sort_indicator(newstate)
        column.set_sort_order(self.sort_order_dict[newstate])

    def get_last_item(self, model, parent=None):
        n = model.iter_n_children(parent)
        return n and model.iter_nth_child(parent, n - 1)

    def treeview_update(self, widget=None, event=None, data=None, row=1):
        if self.autoscroll:
            # adj = widget.get_vadjustment()
            # if self.sort_order == Gtk.SortType.DESCENDING:
            # adj.set_value(adj.get_upper() - adj.get_page_size())

            if self.autoselect:
                # selection = self.treeview.get_selection()
                # self.selection.set_mode(Gtk.SelectionMode.SINGLE)
                last = self.get_last_item(self.pool_liststore)
                if last != 0:
                    self.selection.select_iter(last)
                    row = self.pool_liststore[self.pool_liststore.get_path(last)][0]
                    if self.selected_row != row:
                        self.set_tm_data_view()
                        self.selected_row = row
                        # self.selection.set_mode(Gtk.SelectionMode.MULTIPLE)

    def edge_reached(self, widget, event, data=None):
        if event.value_name == 'GTK_POS_BOTTOM':
            self.autoscroll = 1
            self.autoselect = 1

    def scroll_bar(self, widget=None, event=None):
        # a little crude, but we want to catch scrollbar-drag events too
        self.autoscroll = 0

    def scroll_child(self, widget, event, data=None):
        # print('Seems like I do not work')
        return

    def scroll_event(self, widget, event, data=None):
        # print(event.direction.value_name, event.delta_x, event.delta_y)
        self.only_scroll = True
        if event.direction.value_name == 'GDK_SCROLL_SMOOTH':
            scroll_lines = 3 * event.delta_y
            if scroll_lines < 0:
                self.autoscroll = 0
            elif scroll_lines > 3:
                self.autoscroll = 1
        # needed for remote desktop
        elif event.direction.value_name == 'GDK_SCROLL_UP':
            scroll_lines = -3
            self.autoscroll = 0
        elif event.direction.value_name == 'GDK_SCROLL_DOWN':
            scroll_lines = 3
        else:
            return

        self._scroll_treeview(scroll_lines)
        self.reselect_rows()
        # Only_scroll is necessary to not launch a second event after the scrollbar is reset to new value
        self.only_scroll = False
        # print(self.offset, self.limit)
        # disable autoscroll on scrollwheel up
        # if event.get_scroll_deltas()[2] == -1:
        #     self.autoscroll = 0

    def _scroll_treeview(self, scroll_lines=0, sort=None, order='asc', rows=None, force_db_import=False):
        sorted = False
        for col in self.tm_columns[self.decoding_type]:
            if self.tm_columns[self.decoding_type][col][1] in [1, 2]:
                sorted = True

        if sorted:
            upper_limit = self.adj.get_upper() - self.adj.get_page_size()
            self.offset = int(min(upper_limit, self.adj.get_value() + scroll_lines))
        else:
            for x, row in enumerate(self.shown_all_rows, start=0):
                if row[0] >= self.offset:
                    position = x
                    break

            try:
                if scroll_lines <0:
                    self.offset = self.shown_all_rows[int(position + scroll_lines)][0] if (position + scroll_lines) > 0 else 0
                else:
                    if len(self.shown_all_rows) < (self.shown_limit):
                        self.offset = self.shown_all_rows[-self.adj.get_page_size()][0]
                    else:
                        self.offset = self.shown_all_rows[int(position + scroll_lines)][0] if (position + scroll_lines) > 0 else 0
            except:
                upper_limit = self.adj.get_upper() - self.adj.get_page_size()
                self.offset = int(min(upper_limit, self.adj.get_value() + scroll_lines))

        self.limit = int(self.adj.get_page_size())
        #self.feed_lines_to_view(
        #    self.fetch_lines_from_db(self.offset, self.limit, sort=sort, order=order, rows=rows, force_import=force_db_import))
        self.fetch_lines_from_db(self.offset, self.limit, sort=sort, order=order, rows=rows, scrolled=True, force_import=force_db_import)
        self.adj.set_value(self.offset)

    def key_pressed(self, widget=None, event=None):
        def unselect_rows():
            # selection = widget.get_selection()
            # self.selection.disconnect_by_func(self.tree_selection_changed)
            model, paths = self.selection.get_selected_rows()
            self.currently_selected = {model[path][0] for path in paths}
            self.reselect_rows()
            # self.selection.connect('changed', self.tree_selection_changed)

        try:
            cursor_path = self.treeview.get_cursor()[0]
            in_row = cursor_path.get_indices()[0]
            # cursor_path.free()
            self.cursor_path = cursor_path
        except AttributeError:
            in_row = 1
            # cursor_path = self.cursor_path
            # in_row = cursor_path.get_indices()[0]

        # if in_row not in (0, self.limit - 1):
        #     return

        if event.keyval == Gdk.KEY_Up and in_row == 0:
            # cursor_path = self.treeview.get_cursor()[0]
            self._scroll_treeview(-1)
            self.treeview.set_cursor(cursor_path)
            self.autoscroll = False
            unselect_rows()
        elif event.keyval == Gdk.KEY_Up:
            self.autoselect = False
            self.autoscroll = False
        elif event.keyval == Gdk.KEY_Down and in_row == self.limit - 1:
            # cursor_path = self.treeview.get_cursor()[0]
            self._scroll_treeview(1)
            self.treeview.set_cursor(cursor_path)
            unselect_rows()
        elif event.keyval == Gdk.KEY_Home:
            self._scroll_treeview(-self.offset)
            # self.treeview.set_cursor(cursor_path)
            self.autoscroll = False
            unselect_rows()
        elif event.keyval == Gdk.KEY_End:
            # cursor_path = self.treeview.get_cursor()[0]
            # self._scroll_treeview(self.adj.get_upper() - self.offset - self.limit)
            # self.treeview.set_cursor(cursor_path)
            self.autoscroll = True
            self.autoselect = True
            self.scroll_to_bottom()
            unselect_rows()
        elif event.keyval == Gdk.KEY_Page_Up:
            # cursor_path = self.treeview.get_cursor()[0]
            self._scroll_treeview(-self.limit)
            self.treeview.set_cursor(cursor_path)
            self.autoscroll = False
            unselect_rows()
        elif event.keyval == Gdk.KEY_Page_Down:
            # cursor_path = self.treeview.get_cursor()[0]
            self._scroll_treeview(self.limit)
            self.treeview.set_cursor(cursor_path)
            self.autoscroll = False
            unselect_rows()
            # else:
            #     print(event.keyval)
            # Gdk.KEY_Page_Up,Gdk.KEY_Page_Down,Gdk.KEY_Home,Gdk.KEY_End

    def set_currently_selected(self, widget=None, event=None):
        state = event.get_state()
        # print(state, state & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK)
        if state & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK:
            # selection = widget.get_selection()
            # model, paths = selection.get_selected_rows()
            idx = self.shift_range[1]
            if idx in self.currently_selected:
                self.currently_selected.remove(idx)
            else:
                self.currently_selected.add(idx)
                # for path in paths:
                #    self.currently_selected.add(model[path][0])
        elif state & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK:
            # selection = widget.get_selection()
            # model, paths = selection.get_selected_rows()
            # for path in paths:
            #     self.currently_selected.add(model[path][0])
            if len(self.currently_selected) > 1:
                for idx in range(min(self.shift_range), max(self.shift_range) + 1):
                    self.currently_selected.add(idx)
            else:
                self.currently_selected = set(range(min(self.shift_range), max(self.shift_range) + 1))
        else:
            # selection = widget.get_selection()
            model, paths = self.selection.get_selected_rows()
            self.currently_selected = {model[path][0] for path in paths}
        self.reselect_rows()

    def select_all_rows(self, widget=None, *args):
        nrows = self.count_current_pool_rows()
        self.currently_selected = set(range(1, nrows + 1))
        self.reselect_rows()

    def reselect_rows(self, widget=None, event=None):
        model = self.pool_liststore  # self.treeview.get_model()
        # self.treeview.get_selection().unselect_all()
        for row in model:
            if row[0] in self.currently_selected:
                try:
                    self.selection.select_path(model.get_path(model.get_iter(row[0] - self.offset)))
                except ValueError:
                    pass
                except TypeError:
                    pass

    def unselect_bottom(self, widget=None):
        if widget.count_selected_rows() > 1:
            bottom_path = widget.get_selected_rows()[-1][-1]
            widget.unselect_path(bottom_path)

    def create_liststore(self):
        if self.decoding_type == 'PUS':
            return Gtk.ListStore('guint', str, 'guint', 'guint', 'guint', 'guint', 'guint', 'guint', str, str)
        elif self.decoding_type == 'RMAP':
            return Gtk.ListStore('guint', str, bool, bool, 'guint', 'guint', 'guint', 'guint', str)
        elif self.decoding_type == 'FEE':
            return Gtk.ListStore('guint', 'guint', 'guint', 'guint', str)
        else:
            print('Unkwown data type')
            self.logger.info('Decoding Type is an unknown Value')
            return

    def set_keybinds(self):

        accel = Gtk.AccelGroup()
        accel.connect(Gdk.keyval_from_name('w'), Gdk.ModifierType.CONTROL_MASK,
                      0, self.quit_func)
        accel.connect(Gdk.keyval_from_name('q'), Gdk.ModifierType.CONTROL_MASK,
                      0, self.quit_func)
        accel.connect(Gdk.keyval_from_name('a'), Gdk.ModifierType.CONTROL_MASK,
                      0, self.select_all_rows)
        self.add_accel_group(accel)

    def create_pool_managebar(self):
        self.pool_managebar = Gtk.HBox()

        self.pool_selector = Gtk.ComboBoxText(tooltip_text='Pool to view')
        pool_names = Gtk.ListStore(str, str, str)

        #        if self.pool != None:
        #            [self.pool_names.append([name]) for name in self.pool.datapool.keys()]

        self.pool_selector.set_model(pool_names)

        cell = Gtk.CellRendererText(foreground='red')
        self.pool_selector.pack_start(cell, 0)
        self.pool_selector.add_attribute(cell, 'text', 1)

        self.pool_selector.connect('changed', self.select_pool)

        plot_butt = Gtk.Button(image=Gtk.Image.new_from_file('pixmap/func.png'), tooltip_text='Parameter Plotter')
        plot_butt.connect('button-press-event', self.show_context_menu, self.context_menu())
        plot_butt.connect('clicked', self.plot_parameters)
        dump_butt = Gtk.Button.new_from_icon_name('gtk-save', Gtk.IconSize.LARGE_TOOLBAR)
        dump_butt.set_tooltip_text('Save pool')
        dump_butt.connect('clicked', self.save_pool)
        load_butt = Gtk.Button.new_from_icon_name('gtk-open', Gtk.IconSize.LARGE_TOOLBAR)
        load_butt.set_tooltip_text('Load pool')
        load_butt.connect('clicked', self.load_pool)
        extract_butt = Gtk.Button.new_from_icon_name('gtk-paste', Gtk.IconSize.LARGE_TOOLBAR)
        extract_butt.set_tooltip_text('Extract packets')
        extract_butt.connect('clicked', self.collect_packet_data)

        # live buttons
        self.rec_butt = Gtk.Button(image=Gtk.Image.new_from_icon_name('gtk-media-record', Gtk.IconSize.LARGE_TOOLBAR),
                                   tooltip_text='Manage recording to LIVE pool')
        self.rec_butt.connect('clicked', self.start_recording)
        self.stop_butt = Gtk.Button(image=Gtk.Image.new_from_icon_name('gtk-media-stop', Gtk.IconSize.LARGE_TOOLBAR),
                                    tooltip_text='Stop recording to currently selected LIVE pool')
        self.stop_butt.set_sensitive(False)
        self.stop_butt.connect('clicked', self.stop_recording)

        clear_butt = Gtk.Button.new_from_icon_name('edit-clear', Gtk.IconSize.LARGE_TOOLBAR)
        clear_butt.set_tooltip_text('Clear current pool')
        clear_butt.connect('clicked', self.clear_pool)

        self.univie_box = self.create_univie_box()

        bigd = Gtk.Button.new_from_icon_name('gtk-justify-fill', Gtk.IconSize.LARGE_TOOLBAR)
        bigd.set_tooltip_text('Open Large Data Viewer')
        bigd.connect('clicked', self.show_bigdata)

        self.pool_managebar.pack_start(self.pool_selector, 1, 1, 0)
        self.pool_managebar.pack_start(plot_butt, 0, 0, 0)
        self.pool_managebar.pack_end(self.univie_box, 0, 0, 0)
        self.pool_managebar.pack_end(clear_butt, 0, 0, 0)
        self.pool_managebar.pack_end(bigd, 0, 0, 0)
        self.pool_managebar.pack_end(self.stop_butt, 0, 0, 0)
        self.pool_managebar.pack_end(self.rec_butt, 0, 0, 0)
        self.pool_managebar.pack_end(dump_butt, 0, 0, 0)
        self.pool_managebar.pack_end(load_butt, 0, 0, 0)
        self.pool_managebar.pack_end(extract_butt, 0, 0, 0)

    def create_filterbar(self):
        filterbar = Gtk.HBox()

        box = Gtk.HBox()

        column_model = Gtk.ListStore(str)
        for name in self.tm_columns[self.decoding_type]:
            column_model.append([name])

        column_name = Gtk.ComboBoxText()
        column_name.set_model(column_model)
        column_name.set_tooltip_text('Select column')

        operator_model = Gtk.ListStore(str)
        for op in ['==', '!=', '<', '>']:
            operator_model.append([op])

        operator = Gtk.ComboBoxText()
        operator.set_model(operator_model)
        operator.set_active(0)
        operator.set_tooltip_text('Select relational operator')

        filter_value = Gtk.Entry()
        filter_value.set_placeholder_text('Filter value')
        filter_value.set_tooltip_text('Filter value')
        filter_value.set_width_chars(14)
        filter_value.connect('activate', self._add_to_rules, filter_value, column_name, operator, 'AND')

        #path_ccs = self.cfg.get(section='ccs-paths', option='ccs')
        path_ccs = confignator.get_option('paths', 'ccs')

        add_to_rule_button_and = Gtk.Button()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(os.path.join(path_ccs, 'pixmap/intersection_icon.svg'), 10, 10)
        add_to_rule_button_and.set_image(Gtk.Image.new_from_pixbuf(pixbuf))
        add_to_rule_button_and.set_tooltip_text('AND')
        add_to_rule_button_and.connect('clicked', self._add_to_rules, filter_value, column_name, operator, 'AND')

        add_to_rule_button_or = Gtk.Button()
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(os.path.join(path_ccs, 'pixmap/union_icon.svg'), 10, 10)
        add_to_rule_button_or.set_image(Gtk.Image.new_from_pixbuf(pixbuf))
        add_to_rule_button_or.set_tooltip_text('OR')
        add_to_rule_button_or.connect('clicked', self._add_to_rules, filter_value, column_name, operator, 'OR')

        box.pack_start(column_name, 1, 1, 0)
        box.pack_start(operator, 1, 1, 0)
        box.pack_start(filter_value, 1, 1, 0)
        box.pack_start(add_to_rule_button_and, 1, 1, 0)
        box.pack_start(add_to_rule_button_or, 1, 1, 0)

        filterbar.pack_start(box, 0, 0, 0)

        # for col in self.column_labels:
        #     if col[0] == 'Data':
        #         continue
        #     filter = Gtk.Entry()
        #     filter.set_placeholder_text(col[0])
        #     filter.set_tooltip_text(col[0])
        #     filter.set_width_chars(5)
        #     filter.connect('activate', self._update_filters)
        #     filterbar.pack_start(filter, 0, 0, 0)

        # filterbar.pack_start(Gtk.Separator.new(Gtk.Orientation.VERTICAL), 1, 0, 0)

        goto_timestamp = Gtk.Entry()
        goto_timestamp.set_placeholder_text('GOTO timestamp')
        goto_timestamp.set_tooltip_text('GOTO timestamp')
        goto_timestamp.set_width_chars(14)
        goto_timestamp.connect('activate', self._goto_timestamp)
        filterbar.pack_end(goto_timestamp, 0, 0, 0)

        goto_idx = Gtk.Entry()
        goto_idx.set_placeholder_text('GOTO idx')
        goto_idx.set_tooltip_text('GOTO idx')
        goto_idx.set_width_chars(10)
        goto_idx.connect('activate', self._goto_idx)
        filterbar.pack_end(goto_idx, 0, 0, 0)

        return filterbar

    def _add_to_rules(self, widget=None, filter_value_box=None, column_name=None, operator=None, and_or=None):

        if and_or == 'AND':
            aosym = '\u2229'
        elif and_or == 'OR':
            aosym = '\u222A'

        column = column_name.get_active_text()
        value = filter_value_box.get_text()
        operator = operator.get_active_text()

        if not column or not value or not operator:
            return

        # if self.rule_box is None:
        #     self._add_rulebox()

        rule = Gtk.HBox()
        if len(self.rule_box) == 1:
            name = Gtk.Label('{}{}{}'.format(column, operator, value))
        else:
            name = Gtk.Label('{} {}{}{}'.format(aosym, column, operator, value))
        rule.pack_start(name, 1, 1, 0)
        close_butt = Gtk.Button()
        close_butt.set_image(Gtk.Image.new_from_icon_name(Gtk.STOCK_CLOSE, Gtk.IconSize.MENU))
        close_butt.set_relief(Gtk.ReliefStyle.NONE)
        close_butt.connect('clicked', self._remove_rule)
        rule.pack_end(close_butt, 0, 0, 0)
        self.filter_rules[hash(rule)] = (self.tm_columns[self.decoding_type][column][0], operator, value, and_or)

        self.rule_box.pack_start(rule, 0, 0, 0)
        self.show_all()

        self._scroll_treeview(force_db_import=True)

    def _add_rulebox(self):
        # if self.rule_box is not None:
        #     self.rule_box.remove()
        #     self.rule_box = None
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        rule_box = Gtk.HBox()
        rule_box.set_spacing(3)
        rule_box.pack_start(Gtk.Label(label='Filters: '), 0, 0, 0)
        scrolled_window.add(rule_box)

        #scrolled_window.add(resize_view_check_button)

        # remove_rule_button = Gtk.Button()
        # remove_rule_button.set_image(Gtk.Image.new_from_icon_name('list-remove', Gtk.IconSize.BUTTON))
        # remove_rule_button.connect('clicked', self._remove_rule)
        # rule_box.pack_end(remove_rule_button, 1, 1, 0)

        rule_active_button = Gtk.Switch()
        # rule_active_button.set_image(Gtk.Image.new_from_icon_name('list-remove', Gtk.IconSize.BUTTON))
        rule_active_button.set_tooltip_text('Toggle filter rules')
        rule_active_button.connect('state-set', self._toggle_rule)
        self.filter_rules_active = rule_active_button.get_active()

        self.filter_spinner = Gtk.Spinner()

        self.rule_box = rule_box

        box = Gtk.HBox()
        box.set_spacing(3)
        box.pack_start(scrolled_window, 1, 1, 5)
        box.pack_start(self.filter_spinner, 1, 1, 1)
        box.pack_end(rule_active_button, 0, 0, 0)
        self.grid.attach(box, 0, 2, 1, 1)
        #self.filter_spinner.start()
        # self.show_all()

    def _resize_scrollbar_toggled(self, widget):
        #self._on_scrollbar_changed()
        pass

    def resize_scrollbar(self):

        if self.first_run or self.resize_thread.is_alive():
            self.first_run = False
            self.resize_thread = threading.Thread(target=self.small_refresh_function)
            return

        self.resize_thread = threading.Thread(target=self.scrollbar_size_worker)
        self.resize_thread.setDaemon(True)
        self.resize_thread.start()

    def scrollbar_size_worker(self):
        #print(1)
        new_session = self.session_factory_storage
        rows = new_session.query(
            Telemetry[self.decoding_type]
        ).join(
            DbTelemetryPool,
            Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename
        )
        #new_session.close()
        cnt = rows.count()
        #print(cnt)
        rows = self._filter_rows(rows)
        cnt = rows.count()
        #count_q = que.statement.with_only_columns([func.count()]).order_by(None)
        #cnt = new_session.execute(count_q).scalar()
        #cnt = new_session.query(que).count()
        #print(2)
        #print(cnt)
        GLib.idle_add(self.adj.set_upper, cnt,)
        #print(3)
        new_session.close()

    def _toggle_rule(self, widget=None, data=None):
        self.filter_rules_active = widget.get_active()
        self._scroll_treeview(force_db_import=True)

    def _remove_rule(self, widget=None):
        rule = widget.get_parent()
        self.filter_rules.pop(hash(rule))
        rule.get_parent().remove(rule)
        self.show_all()

        self._scroll_treeview()

    def _update_filters(self, widget):
        value = widget.get_text()
        value = None if value == '' else value
        self.tm_columns[self.decoding_type][widget.get_placeholder_text()][2] = value
        self._scroll_treeview()

    def _goto_idx(self, widget):
        try:
            widget.set_sensitive(False)
            goto = int(widget.get_text()) - 1
        except ValueError:
            return
        finally:
            widget.set_sensitive(True)
        upper_limit = self.adj.get_upper() - self.adj.get_page_size()
        self.offset = int(min(upper_limit, goto))
        self.limit = int(self.adj.get_page_size())
        #self.feed_lines_to_view(
        #    self.fetch_lines_from_db(self.offset, self.limit, sort=None, order='asc'))
        self.fetch_lines_from_db(self.offset, self.limit, sort=None, order='asc', force_import=True)
        self.adj.set_value(self.offset)

    def _goto_timestamp(self, widget):
        if self.decoding_type != 'PUS':
            print('No Timestamp in RMAP and FEE data')
            return

        try:
            goto = widget.get_text()
        except ValueError:
            return
        upper_limit = self.adj.get_upper() - self.adj.get_page_size()
        rows = self.get_current_pool_rows()
        try:
            widget.set_sensitive(False)
            idx = rows.filter(Telemetry[self.decoding_type].timestamp.like(goto + "%"))[0].idx - 1
        except IndexError:
            return
        finally:
            widget.set_sensitive(True)
        self.offset = int(min(upper_limit, idx))
        self.limit = int(self.adj.get_page_size())
        #self.feed_lines_to_view(
        #    self.fetch_lines_from_db(self.offset, self.limit, sort=None, order='asc'))
        self.fetch_lines_from_db(self.offset, self.limit, sort=None, order='asc', force_import=True)

        self.adj.set_value(self.offset)

        return
    def context_menu(self):
        menu = Gtk.Menu()

        item = Gtk.MenuItem(label='TEST')
        item.connect('activate', self.menu_test)
        menu.append(item)
        return menu

    def show_context_menu(self, widget, event, menu):
        if event.button != 3:
            return
        menu.show_all()
        menu.popup(None, None, None, None, 3, event.time)

    def menu_test(self, widget=None):
        print('BALABALBLABLAL')

    def check_structure_type(self):

        # If pool is changed but not created:
        model = self.pool_selector.get_model()
        if self.pool_selector.get_active_iter():
            current_selected_type = model.get_value(self.pool_selector.get_active_iter(), 2)  # Get the shown decoding type
            current_selected_pool = self.pool_selector.get_active_text()   # get the shown pool
        else:
            current_selected_type = False
            current_selected_pool = False
        if self.active_pool_info.pool_name == current_selected_pool:
            self.decoding_type = current_selected_type
            return
        '''   
        count = 0
        while count < len(model):
            value = model.get_value(model.get_iter(count), 0)  # Get the value
            if value.split(' - ')[0] == self.active_pool_info.pool_name:
                self.pool_selector.set_active_iter(model.get_iter(count))
                changed = True
                break
            count += 1
        # if no other poo'''

        # If pool is created
        # Check in the DB which datatype should be use
        new_session = self.session_factory_storage
        pool = new_session.query(
            DbTelemetryPool.protocol
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename
        )
        pool = pool.all()
        # new_session.commit()
        time.sleep(0.5)  # with no wait query might return empty. WHY???##############################################
        # Still sometimes empty, if not pool abfrage should stopp this behaviour
        #print(pool.all())

        if not pool:
            self.decoding_type = 'PUS'
        elif pool[0][0] in ['PUS', 'PLMSIM']:  # If PUS decode PUS
            self.decoding_type = 'PUS'
        else:   # If a new pool is created always show RMAP
            self.decoding_type = 'RMAP'
        new_session.close()
        return
    # def get_pool_names(self, widget):
    #     if self.pool is None:
    #         return
    #
    #     self.pool_names = Gtk.ListStore(str)
    #     [self.pool_names.append([name]) for name in self.pool.datapool.keys()]
    #     self.pool_selector.set_model(self.pool_names)

    #This function fills the Active pool info variable with data form pus_datapool
    def Active_Pool_Info_append(self, pool_info=None):
        if pool_info is not None:
            self.active_pool_info = ActivePoolInfo(str(pool_info[0]), int(pool_info[1]),
                                                   str(pool_info[2]), bool(pool_info[3]))
        #self.decoding_type = 'PUS'
        self.check_structure_type()
        return self.active_pool_info

    def update_columns(self):
        columns = self.treeview.get_columns()
        for column in columns:
            self.treeview.remove_column(column)
        self.create_treeview_columns()

        self.pool_liststore = self.create_liststore()
        self.treeview.set_model(self.pool_liststore)

        #self.scrolled_treelist.add(self.treeview)

        self.show_all()

    def select_pool(self, selector, new_pool=None):
        if not new_pool:
            pool_name = selector.get_active_text()
        else:
            pool_name = new_pool
        #self.active_pool_info = self.pool.loaded_pools[pool_name]
        # self.active_pool_info = poolmgr.Dictionaries('loaded_pools', pool_name)

        try:
            poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
            if not poolmgr:
                raise TypeError
            self.Active_Pool_Info_append(cfl.Dictionaries(poolmgr, 'loaded_pools', pool_name))

        except:
            new_session = self.session_factory_storage

            if self.active_pool_info.pool_name == pool_name:
                #type = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == self.active_pool_info.filename).first()
                #self.Active_Pool_Info_append([pool_name, type.modification_time, pool_name, False])
                pass
            else:
                type = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name)
                self.Active_Pool_Info_append([pool_name, type.modification_time, pool_name, False])


            new_session.close()

        self.update_columns()
        #self._set_pool_list_and_display()

        if not self.active_pool_info.live:
            self.stop_butt.set_sensitive(False)
        else:
            self.stop_butt.set_sensitive(True)
            self.refresh_treeview(pool_name)
        self.adj.set_upper(self.count_current_pool_rows())
        self.adj.set_value(0)
        self._on_scrollbar_changed(adj=self.adj)


        # queue = self.queues[pool_name]
        #
        # if queue is not None:
        #     self.pool_liststore.clear()
        #     self.pckt_queue = queue
        #     self.pool_name = pool_name
        #     if self.pool is not None:
        #         self.model_unset = True
        #         self.pool.reset_queue_seq(pool_name, queue)
        #         # self.change_cursor(self.scrolled_treelist.get_window(),'progress')

    def clear_pool(self, widget):
        poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        widget.set_sensitive(False)
        pool_name = self.get_active_pool_name()

        if pool_name is None:
            return

        #self.pool._clear_pool(pool_name)
        #self.active_pool_info = self.pool.loaded_pools[pool_name]
        poolmgr.Functions('_clear_pool', pool_name)
        # self.active_pool_info = poolmgr.Dictionaries('loaded_pools', pool_name)
        self.Active_Pool_Info_append(poolmgr.Dictionaries('loaded_pools', pool_name))

        # new_session = self.dbcon
        # new_session.execute(
        #     'UPDATE tm_pool SET pool_name="---TO-BE-DELETED---" WHERE tm_pool.pool_name="{}"'.format(
        #         self.get_active_pool_name()))
        # new_session.commit()
        #
        # # new_session.execute(
        # #     'delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid where tm_pool.pool_name="{}"'.format(
        # #         self.active_pool_info.filename))
        # # new_session.execute('delete tm_pool from tm_pool where tm_pool.pool_name="{}"'.format(
        # #     self.active_pool_info.filename))
        # # # new_session.flush()
        # # new_session.commit()
        # new_session.close()
        self.adj.set_upper(self.count_current_pool_rows())
        self._on_scrollbar_changed()
        widget.set_sensitive(True)

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
            confignator.get_option('paths', 'ccs') + '/pixmap/Icon_Space_blau_en.png', 48, 48)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        univie_button.set_icon_widget(icon)
        univie_button.set_tooltip_text('Applications and About')
        univie_button.connect("clicked", self.on_univie_button)
        univie_box.add(univie_button)

        # Popover creates the popup menu over the button and lets one use multiple buttons for the same one
        self.popover = Gtk.Popover()
        # Add the different Starting Options
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for name in self.cfg['ccs-dbus_names']:
            start_button = Gtk.Button.new_with_label("Start " + name.capitalize() + '   ')
            start_button.connect("clicked", cfl.on_open_univie_clicked)
            vbox.pack_start(start_button, False, True, 10)

        # Add the manage connections option
        conn_button = Gtk.Button.new_with_label('Communication')
        conn_button.connect("clicked", self.on_communication_dialog)
        vbox.pack_start(conn_button, False, True, 10)

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

    def update_pool_view(self, pool_name, pmgr_load_pool=None, instance=1):
        """
        Used to change the view to given pool, or create a new entry if it does not exist
        Mostly used by Poolmanger GUI 'Display' Button
        :param pool_name: Name of the pool to change to or to create
        :return:
        """
        # If Active (Shown) Pool is the one dont do anything
        if pool_name == self.get_active_pool_name():
            return
        changed = False
        #self.select_pool(False, new_pool=pool_name)
        model = self.pool_selector.get_model()
        #It will check all entries in the Pool selector and change to the one if possible
        count = 0
        while count < len(model):
            value = model.get_value(model.get_iter(count), 0)  # Get the value
            if value == pool_name:  # If the wanted connection is found change to it
                self.pool_selector.set_active_iter(model.get_iter(count))
                changed = True
                break
            count += 1
        # if no other pool could be found create a new one
        if not changed:
            if not pmgr_load_pool:
                self.set_pool(pool_name, instance=instance)
            else:
                self.set_pool(pool_name, pmgr_load_pool, instance=instance)

        # Instance has to be used only here, explanation is found in pus_datapool where this function is called
        if instance:
            poolmgr = cfl.dbus_connection('poolmanager', instance)
            cfl.Functions(poolmgr, 'loaded_pools_func', self.active_pool_info.pool_name, self.active_pool_info)
        return


    def create_tm_data_viewer(self):
        box = Gtk.VBox()

        self.decoder_box = Gtk.VBox()
        decoder_bar = self.create_decoder_bar()
        self.decoder_box.pack_start(decoder_bar, 1, 1, 1)
        box.pack_start(self.decoder_box, 0, 0, 0)

        self.rawswitch = Gtk.CheckButton.new_with_label('Decode Source Data')
        self.rawswitch.connect('toggled', self.set_tm_data_view, None, True)
        # self.sortswitch = Gtk.CheckButton.new_with_label('Sort by Name')
        # self.sortswitch.connect('toggled', self.set_tm_data_view, )
        #switchbox = Gtk.Box(Gtk.Orientation.HORIZONTAL)
        switchbox = Gtk.HBox()
        switchbox.pack_start(self.rawswitch, 0, 0, 0)
        # switchbox.pack_end(self.sortswitch, 0, 0, 0)

        self.hexview = Gtk.Label()
        self.hexview.set_selectable(True)
        switchbox.pack_end(self.hexview, 1, 1, 0)

        box.pack_start(switchbox, 0, 0, 3)

        scrolled_header_view = Gtk.ScrolledWindow()
        scrolled_header_view.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        # self.tm_data_viewer.set_hexpand(True)
        self.tm_header_view = Gtk.TextView(editable=False, cursor_visible=False)
        scrolled_header_view.add(self.tm_header_view)
        box.pack_start(scrolled_header_view, 0, 0, 0)

        scrolled_tm_view = Gtk.ScrolledWindow()
        self.tm_data_view = self.create_tm_data_viewer_list(decode=False, create=True)
        data_selection = self.tm_data_view.get_selection()
        data_selection.connect('changed', self.set_hexview)
        scrolled_tm_view.add(self.tm_data_view)
        box.pack_start(scrolled_tm_view, 1, 1, 0)

        return box

    def create_tm_data_viewer_list(self, decode=False, create=False):
        tm_data_model = Gtk.ListStore(str, str, str, str)
        if create:
            listview = Gtk.TreeView()
            listview.set_model(tm_data_model)
        else:
            listview = self.tm_data_view
            for c in listview.get_columns():
                listview.remove_column(c)
            listview.set_model(tm_data_model)

        if decode:
            for i, column_title in enumerate(['Parameter', 'Value', 'Unit']):
                render = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(column_title, render, text=i)
                # column.set_cell_data_func(render, self.text_colour2)

                column.set_sort_column_id(i)
                column.set_clickable(True)
                column.set_resizable(True)
                # column.connect('clicked', self.column_clicked)
                listview.append_column(column)

            render = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn('tooltip', render, text=3)
            column.set_visible(False)
            listview.append_column(column)
            listview.set_tooltip_column(3)

        else:
            for i, column_title in enumerate(['bytepos', 'hex', 'decimal', 'ascii']):
                render = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(column_title, render, text=i)
                # column.set_cell_data_func(render, self.text_colour2)
                column.set_resizable(True)
                listview.append_column(column)

        if create:
            return listview

    def create_decoder_bar(self):
        box = Gtk.VBox()

        box1 = Gtk.HBox()
        package_button = Gtk.Button(label = 'Add Package to Decode')
        package_button.set_image(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.MENU))
        package_button.set_tooltip_text('Add User Defined Package to Decode')
        package_button.set_always_show_image(True)

        parameter_button = Gtk.Button()
        parameter_button.set_image(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.MENU))
        parameter_button.set_tooltip_text('Add User Defined Parameter to use in Package')
        parameter_button.set_always_show_image(True)

        package_button.connect('clicked', self.add_new_user_package)
        parameter_button.connect('clicked', self.add_decode_parameter)

        box1.pack_start(package_button, 0, 0, 0)
        box1.pack_start(parameter_button, 0, 0, 0)


        box2 = Gtk.HBox()

        decoder_name = Gtk.ComboBoxText.new_with_entry()
        decoder_name.set_tooltip_text('Label')
        decoder_name_entry = decoder_name.get_child()
        decoder_name_entry.set_placeholder_text('Label')
        decoder_name_entry.set_width_chars(5)

        decoder_name.set_model(self.create_decoder_model())

        bytepos = Gtk.Entry()
        bytepos.set_placeholder_text('Offset+{}'.format(TM_HEADER_LEN))
        bytepos.set_tooltip_text('Offset+{}'.format(TM_HEADER_LEN))
        bytepos.set_width_chars(5)

        bytelength = Gtk.Entry()
        bytelength.set_placeholder_text('Length')
        bytelength.set_tooltip_text('Length')
        bytelength.set_width_chars(5)

        add_button = Gtk.Button(label=' Decoder')
        add_button.set_image(Gtk.Image.new_from_icon_name('list-add', Gtk.IconSize.MENU))
        add_button.set_always_show_image(True)

        decode_udef_check = Gtk.CheckButton.new_with_label('UDEF')
        decode_udef_check.set_tooltip_text('Use User-defined Packets first for Decoding')

        decoder_name.connect('changed', self.fill_decoder_mask, bytepos, bytelength)
        add_button.connect('clicked', self.add_decoder, decoder_name, bytepos, bytelength)
        decode_udef_check.connect('toggled', self.set_decoding_order)


        box2.pack_start(decoder_name, 0, 0, 0)
        box2.pack_start(bytepos, 0, 0, 1)
        box2.pack_start(bytelength, 0, 0, 1)
        box2.pack_start(add_button, 0, 0, 0)
        box2.pack_start(decode_udef_check, 0, 0, 0)

        box.pack_start(box1, 0, 0, 0)
        box.pack_start(box2, 0, 0, 0)

        self.decoder_dict = {}
        self.UDEF = False

        return box

    def add_decode_parameter(self, widget):
        cfl.add_decode_parameter(parentwin=self)

    def add_new_user_package(self, widget):
        cfl.add_tm_decoder(parentwin=self)


    def set_decoding_order(self, widget):

        if widget.get_active():
            self.UDEF = True
        else:
            self.UDEF = False

        self.set_tm_data_view()

        return

    def create_decoder_model(self):
        model = Gtk.ListStore(str)

        # if self.cfg.has_section('user_decoders'):
        #    for decoder in self.cfg['user_decoders'].keys():
        #        model.append([decoder])

        for decoder in self.cfg['ccs-user_decoders'].keys():
            len = self.cfg['ccs-user_decoders'][decoder]
            if 'bytelen' in len:
                model.append([decoder])

        return model

    def fill_decoder_mask(self, widget, bytepos=None, bytelen=None):
        decoder = widget.get_active_text()

        # if not self.cfg.has_option('user_decoders',decoder):
        #    return

        if self.cfg.has_option('ccs-plot_parameters', decoder):
            data = json.loads(self.cfg['ccs-plot_parameters'][decoder])

            bytepos.set_text(str(data['bytepos']))
            bytelen.set_text(str(struct.calcsize(data['format'])))

    def add_decoder(self, widget, decoder_name, byteoffset, bytelength):
        try:
            label, bytepos, bytelen = decoder_name.get_active_text(), int(byteoffset.get_text()), int(
                bytelength.get_text())
        except:
            return

        if label in (None, ''):
            return

        self.decoder_dict[label] = {'bytepos': bytepos, 'bytelen': bytelen}

        self.cfg['ccs-user_decoders'][label] = json.dumps(self.decoder_dict[label])
        try:
            self.cfg.save_to_file(file_path=confignator.get_option('config-files', 'ccs'))
            #with open(self.cfg.source, 'w') as fdesc:
            #    self.cfg.write(fdesc)
        except AttributeError:
            self.logger.info('Could not save decoder to cfg')

        decoder_name.set_model(self.create_decoder_model())

        box = Gtk.HBox()

        name = Gtk.Label(decoder_name.get_active_text())
        name.set_tooltip_text('bytes {}-{}'.format(bytepos, bytepos + bytelen - 1))
        hexa = Gtk.Label()
        uint = Gtk.Label()
        bina = Gtk.Label()

        box.pack_start(name, 1, 1, 0)

        close_butt = Gtk.Button()
        close_butt.set_image(Gtk.Image.new_from_icon_name(Gtk.STOCK_CLOSE, Gtk.IconSize.MENU))
        close_butt.set_relief(Gtk.ReliefStyle.NONE)

        box.pack_end(close_butt, 0, 0, 0)
        box.pack_end(bina, 1, 0, 1)
        box.pack_end(uint, 1, 0, 1)
        box.pack_end(hexa, 1, 0, 1)

        decoder_box = widget.get_parent().get_parent()
        decoder_box.pack_start(box, 0, 0, 1)

        close_butt.connect('clicked', self.remove_decoder, box, decoder_box)
        self.show_all()

        return box

    def remove_decoder(self, widget, decoder, decoder_box):
        decoder_box.remove(decoder)
        self.show_all()

    def set_decoder_view(self, tm):
        decoders = self.decoder_box.get_children()[1:]

        for decoder in decoders:
            try:
                name, hexa, uint, bina, _ = decoder.get_children()
                bytepos = self.decoder_dict[name.get_label()]['bytepos']
                bytelen = self.decoder_dict[name.get_label()]['bytelen']
                byts = tm[bytepos:bytepos + bytelen]
                hexa.set_label(byts.hex().upper())
                uint.set_label(str(int.from_bytes(byts, 'big')))
                bina.set_label(bin(int.from_bytes(byts, 'big'))[2:])
            except:
                hexa.set_label('###')
                uint.set_label('###')
                bina.set_label('###')

    def set_hexview(self, widget=None, data=None):
        if self.rawswitch.get_active():
            model, treepath = widget.get_selected_rows()
            if treepath:
                value = model[treepath[0]][3]
                #print(list(model[treepath[0]]))
                #print(value)
                #print(type(value))
                self.hexview.set_text(value)

    @delayed(10)
    def set_tm_data_view(self, selection=None, event=None, change_columns=False):
        if not self.active_pool_info or not self.decoding_type == 'PUS':
            print('Can not decode parameters for RMAP or FEE data packets')
            buf = Gtk.TextBuffer(text='Parameter view not available for non-PUS packets')
            self.tm_header_view.set_buffer(buf)
            return

        if change_columns:
            self.tm_data_view.freeze_child_notify()
            self.create_tm_data_viewer_list(decode=self.rawswitch.get_active(), create=False)
            self.tm_data_view.thaw_child_notify()
        # print(time.time(), self.autoselect)
        # self.adj.set_upper(self.count_current_pool_rows())
        # textview = self.tm_data_viewer.get_child()
        datamodel = self.tm_data_view.get_model()

        if not isinstance(selection, Gtk.TreeSelection):
            toggle = True
            selection = self.treeview.get_selection()
        else:
            toggle = False

        # nrows = selection.count_selected_rows()
        nrows = len(self.currently_selected)
        if nrows > 1:
            self.tm_header_view.set_buffer(Gtk.TextBuffer(text='{} packets selected'.format(nrows)))
            datamodel.clear()
            return

        model, treepath = selection.get_selected_rows()

        if len(treepath) == 0:
            return
        else:
            rowidx = model[treepath][0]

        if rowidx == self.last_decoded_row and not toggle:
            return
        else:
            self.last_decoded_row = rowidx

        tm_index = model[treepath[0]][0]
        # tm_index = self.active_row
        new_session = self.session_factory_storage
        raw = new_session.query(
            Telemetry[self.decoding_type].raw
        ).join(
            DbTelemetryPool,
            DbTelemetryPool.iid == Telemetry[self.decoding_type].pool_id
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename,
            Telemetry[self.decoding_type].idx == tm_index
        ).first()
        if not raw:
            new_session.close()
            return
        tm = raw[0]
        # new_session.commit()
        new_session.close()
        self.set_decoder_view(tm)

        if self.rawswitch.get_active():
            self.tm_header_view.set_monospace(False)
            datamodel.clear()
            try:
                # buf = Gtk.TextBuffer(text=self.ccs.Tmformatted(tm, sort_by_name=self.sortswitch.get_active()))
                if self.UDEF:
                    data = cfl.Tmformatted(tm, textmode=False, UDEF=True)
                    buf = Gtk.TextBuffer(text=cfl.Tm_header_formatted(tm) + '\n{}\n'.format(data[1]))
                    self._feed_tm_data_view_model(datamodel, data[0])
                else:
                    data = cfl.Tmformatted(tm, textmode=False)
                    buf = Gtk.TextBuffer(text=cfl.Tm_header_formatted(tm) + '\n{}\n'.format(data[1]))
                    self._feed_tm_data_view_model(datamodel, data[0])

            except Exception as error:
                buf = Gtk.TextBuffer(text='Error in decoding packet data:\n{}\n'.format(error))
                # print(traceback.format_exc())

        else:
            self.tm_header_view.set_monospace(False)
            head = cfl.Tm_header_formatted(tm, detailed=True)
            headlen = TC_HEADER_LEN if (tm[0] >> 4 & 1) else TM_HEADER_LEN

            tmsource = tm[headlen:]
            byteview = [[str(n + headlen), '{:02X}'.format(i), str(i), ascii(chr(i)).strip("'")] for n, i in enumerate(tmsource[:-PEC_LEN])]
            self._feed_tm_data_view_model(datamodel, byteview)
            buf = Gtk.TextBuffer(text=head + '\n')

        self.tm_header_view.set_buffer(buf)

    def _feed_tm_data_view_model(self, model, data):
        try:
            if not isinstance(data[0], list):
                data = [data]
        except IndexError:
            model.clear()
            return
        self.tm_data_view.freeze_child_notify()
        model.clear()
        for row in data:
            if row:
                model.append(row)
        self.tm_data_view.thaw_child_notify()

    def save_pool(self, widget):
        dialog = SavePoolDialog(parent=self)

        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()

            modes = dialog.formatbox.get_children()
            if modes[0].get_active():
                mode = 'binary'
            elif modes[1].get_active():
                mode = 'hex'
            elif modes[2].get_active():
                mode = 'text'

            merge = dialog.merge_tables.get_active()

            if dialog.selectiononly.get_active():
                # selection = self.treeview.get_selection()
                # model, paths = selection.get_selected_rows()
                # indices = [model[path][0] for path in paths]
                indices = self.currently_selected
                # tmlist = self.ccs.get_packet_selection(indices, self.get_active_pool_name())
                tmlist = self.get_packets_from_indices(indices=indices, filtered=dialog.save_filtered.get_active())
            else:
                # tmlist = self.pool.datapool[self.get_active_pool_name()]['pckts'].values()
                indices = None
                tmlist = self.get_packets_from_indices(filtered=dialog.save_filtered.get_active(), merged_tables=merge)

            crc = dialog.crccheck.get_active()
            cfl.Tmdump(filename, tmlist, mode=mode, st_filter=None, crccheck=crc)
            self.logger.info(
                '{} packets from {} saved as {} in {} mode (CRC {})'.format(len(list(tmlist)),
                                                                            self.get_active_pool_name(),
                                                                            filename,
                                                                            mode.upper(), crc))
            if dialog.store_in_db.get_active():
                self.save_pool_in_db(filename, int(os.path.getmtime(filename)), indices)
        dialog.destroy()

    def save_pool_in_db(self, filename, timestamp, indices=None):
        new_session = self.session_factory_storage
        #new_session.execute(
        #    'delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid where tm_pool.pool_name="{}"'.format(
        #        filename))


        new_session.query(
            Telemetry[self.decoding_type]
        ).join(
            DbTelemetryPool,
            Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename
        ).delete()
        new_session.commit()


        new_session.query(
            DbTelemetryPool
        ).filter(
            DbTelemetryPool.pool_name == filename
        ).delete()
        new_session.commit()
        newPoolRow = DbTelemetryPool(
            pool_name=filename,
            modification_time=timestamp)
        new_session.add(newPoolRow)
        new_session.flush()
        rows = new_session.query(
            Telemetry[self.decoding_type]
        ).join(
            DbTelemetryPool,
            DbTelemetryPool.iid == Telemetry[self.decoding_type].pool_id
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename)
        if indices is not None:
            rows = rows.filter(Telemetry[self.decoding_type].idx.in_(indices))
        for idx, row in enumerate(rows, 1):
            new_session.add(Telemetry[self.decoding_type](pool_id=newPoolRow.iid,
                                        idx=idx,
                                        is_tm=row.is_tm,
                                        apid=row.apid,
                                        seq=row.seq,
                                        len_7=row.len_7,
                                        stc=row.stc,
                                        sst=row.sst,
                                        destID=row.destID,
                                        timestamp=row.timestamp,
                                        data=row.data,
                                        raw=row.raw))
        # new_session.flush()
        new_session.commit()
        new_session.close()
    '''
    # Poolmgr can call the LoadInfo Window via dbus, needed for the load_pool function
    def LoadInfo(self):
        loadinfo = LoadInfo(parent=self)
        return loadinfo
    '''
    def load_saved_pool(self, filename=None, protocol='PUS'):
        if filename is not None:
            self.load_pool(widget=None, filename=filename, protocol=protocol)
        else:
            print('Please give a Filename')
            return 'Please give a Filename'
        return

    # Whole function is now done in Poolmgr
    def load_pool(self, widget=None, filename=None, brute=False, force_db_import=False, protocol='PUS'):
        if cfl.is_open('poolmanager', cfl.communication['poolmanager']):
            poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        else:
            cfl.start_pmgr(True, '--nogui')
            #path_pm = os.path.join(confignator.get_option('paths', 'ccs'), 'pus_datapool.py')
            #subprocess.Popen(['python3', path_pm, '--nogui'])
            print('Poolmanager was started in the background')

            # Here we have a little bit of a tricky situation since when we start the Poolmanager it wants to tell the
            # Manager to which number it can talk to but it can only do this when PoolViewer is not busy...
            # Therefore it is first found out which number the new Poolmanager will get and it will be called by that
            our_con = []
            # Look for all connections starting with com.poolmanager.communication,
            # therefore only one loop over all connections is necessary
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['poolmanager']):
                    our_con.append(service)

            new_pmgr_nbr = 0
            if len(our_con) != 0:   # If an active PoolManager is found they have to belong to another prject
                for k in range(1, 10):  # Loop over all possible numbers
                    for j in our_con:   # Check every number with every PoolManager
                        if str(k) == str(j[-1]):    # If the number is not found set variable found to True
                            found = True
                        else:   # If number is found set variable found to False
                            found = False
                            break

                    if found:   # If number could not be found save the number and try connecting
                        new_pmgr_nbr = k
                        break

            else:
                new_pmgr_nbr = 1

            if new_pmgr_nbr == 0:
                print('The maximum amount of Poolviewers has been reached')
                return

            # Wait a maximum of 10 seconds to connect to the poolmanager
            i = 0
            while i < 100:
                if cfl.is_open('poolmanager', new_pmgr_nbr):
                    poolmgr = cfl.dbus_connection('poolmanager', new_pmgr_nbr)
                    break
                else:
                    i += 1
                    time.sleep(0.1)


        if filename is not None and filename:
            pool_name = filename.split('/')[-1]
            try:
                new_pool = cfl.Functions(poolmgr, 'load_pool_poolviewer', pool_name, filename, brute, force_db_import,
                                             self.count_current_pool_rows(), self.my_bus_name[-1], protocol)

            except:
                self.logger.warning('Pool could not be loaded, File: ' +str(filename) + 'does probably not exist')
                print('Pool could not be loaded, File' +str(filename)+ 'does probably not exist')
                return
        else:
            dialog = Gtk.FileChooserDialog(title="Load File to pool", parent=self, action=Gtk.FileChooserAction.OPEN)
            dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

            area = dialog.get_content_area()
            hbox, force_button, brute_extract, type_buttons = self.pool_loader_dialog_buttons()

            area.add(hbox)
            area.show_all()

            dialog.set_transient_for(self)

            response = dialog.run()

            if response == Gtk.ResponseType.OK:
                filename = dialog.get_filename()
                pool_name = filename.split('/')[-1]
                isbrute = brute_extract.get_active()
                force_db_import = force_button.get_active()
                for button in type_buttons:
                    if button.get_active():
                        package_type = button.get_label()
            else:
                dialog.destroy()
                return

            if package_type:
                if package_type not in ['PUS', 'PLMSIM']:
                    package_type == 'SPW'

            ## package_type defines which type was selected by the user, if any was selected
            new_pool = cfl.Functions(poolmgr, 'load_pool_poolviewer', pool_name, filename, isbrute, force_db_import,
                                         self.count_current_pool_rows(), self.my_bus_name[-1], package_type)

            dialog.destroy()


        if new_pool:
            self._set_pool_list_and_display(new_pool)

        # If a new Pool is loaded show it
        #if new_pool:

        #else: # If not just switch the page to the previously loaded pool
        #    #Check if pool is loaded in Poolviewer or if it is a loaded pool in the poolmanager which is not
        #    # live and therefore not loaded to the viewer in the booting process
        #    try:
        #        model = self.pool_selector.get_model()
        #        self.pool_selector.set_active([row[0] == self.active_pool_info.pool_name for row in model].index(True))
        #    except:
                # Pool is still importing do nothing
                #all_pmgr_pools = poolmgr.Functions('loaded_pools_export_func')
                #for pool in all_pmgr_pools:
                #    if pool[2] == pool_name:
                #        self._set_pool_list_and_display(pool)
                #        break
                #pass
        return

    def pool_loader_dialog_buttons(self):
        '''
        Small Function to set up the buttons for the Pool Loading Window
        @return: A Gtk.HBox
        '''
        hbox = Gtk.HBox()
        hbox.set_border_width(10)
        brute_extract = Gtk.CheckButton.new_with_label('Search valid packets')
        brute_extract.set_tooltip_text('Keep searching for valid packets if invalid ones are encountered')
        force_button = Gtk.CheckButton.new_with_label('Force DB Import')
        force_button.set_tooltip_text(
            'Do a fresh import of the packets in the dump, even if they are already in the DB')


        hbox.pack_end(brute_extract, 0, 0, 0)
        hbox.pack_end(force_button, 0, 0, 0)

        import_pool_win_buttons = []
        i = 1
        # for packet_type in self.column_labels:
        for packet_type in ['PUS', 'SPW']:
            if i == 1:
                button1 = Gtk.RadioButton(label=str(packet_type))
                button1.set_tooltip_text("Imported file has {} protocol".format(packet_type))
                button1.set_sensitive(True)
                import_pool_win_buttons.append(button1)
                hbox.pack_end(button1, 0, 0, 0)
            else:
                button = Gtk.RadioButton.new_from_widget(button1)
                button.set_label(str(packet_type))
                button.set_sensitive(True)
                button.set_tooltip_text("Imported file has {} protocol".format(packet_type))
                import_pool_win_buttons.append(button)
                hbox.pack_end(button, 0, 0, 0)
            i += 1

        # force_button.connect("toggled", self._on_force_button_changed, import_pool_win_buttons)
        # hbox.pack_end(force_button, 0, 0, 0)
        return hbox, force_button, brute_extract, import_pool_win_buttons

    def _on_force_button_changed(self, widget, buttons):
        if widget.get_active():
            for button in buttons:
                button.set_sensitive(True)
        else:
            for button in buttons:
                button.set_sensitive(False)


    # Glib.idle_add only does only do something when there is time, sometimes this is blocked until the main loop does
    # another iteration, this nonesense function start this and lets Glib.idle add do the funciton
    # Also used to set up the thread variable in resize scrollbar
    def small_refresh_function(self):
        return

    # Only to use Glib idle add and ignore_reply keyword at the same time
    def _set_list_and_display_Glib_idle_add(self, active_pool_info_mgr=None, instance=None):
        if active_pool_info_mgr != None:
            GLib.idle_add(self._set_pool_list_and_display(active_pool_info_mgr, instance))
        else:
            GLib.idle_add(self._set_pool_list_and_display(instance=instance))
        return

    def _set_pool_list_and_display(self, pool_info=None, instance=None):

        if pool_info is not None:
            self.Active_Pool_Info_append(pool_info)

        self.update_columns()

        # self.pool.create(pool_name)
        self.adj.set_upper(self.count_current_pool_rows())
        self.offset = 0
        self.limit = self.adj.get_page_size()
        self._on_scrollbar_changed(adj=self.adj, force=True)
        # self.pool.load_pckts(pool_name, filename)
        # pvqueue2 = self.pool.register_queue(pool_name)
        # self.set_queue(*pvqueue2)
        # Check the decoding type to show a pool
        if self.decoding_type == 'PUS':
            model = self.pool_selector.get_model()
            iter = model.append([self.active_pool_info.pool_name, self.live_signal[self.active_pool_info.live], self.decoding_type])
            self.pool_selector.set_active_iter(iter)
        else:
            # If not PUS open all other possible types but show RMAP
            for packet_type in Telemetry:
                if packet_type == 'PUS':
                    pass
                elif packet_type == 'RMAP':
                    model = self.pool_selector.get_model()
                    iter = model.append([self.active_pool_info.pool_name, self.live_signal[self.active_pool_info.live], packet_type])
                    self.pool_selector.set_active_iter(iter)   # Always show the RMAP pool when created
                else:
                    model = self.pool_selector.get_model()
                    iter = model.append([self.active_pool_info.pool_name, self.live_signal[self.active_pool_info.live], packet_type])
        #try:
        #    poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        #    poolmgr.Functions('loaded_pools_func', self.active_pool_info.pool_name, self.active_pool_info)
        #except:
        #    pass

        if self.active_pool_info.live:
            self.stop_butt.set_sensitive(True)
        else:
            self.stop_butt.set_sensitive(False)
        refresh_rate = 1


        GLib.timeout_add(refresh_rate * 1000, self.show_data_rate, refresh_rate, instance, priority=GLib.PRIORITY_DEFAULT)
        return True

    def collect_packet_data(self, widget):
        # selection = self.treeview.get_selection()
        # model, paths = selection.get_selected_rows()
        if not self.active_pool_info:
            print('No pool to extract packets from')
            return
            ###############
            # If this is ever changed to all packet standards and not only PUS, be aware that further down the database is asced of ST and SST... only possible for PUS
            ###############

        indices = self.currently_selected

        dialog = ExtractionDialog(parent=self, pkttype=self.decoding_type)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            try:
                st, sst = dialog.st.get_text(), dialog.sst.get_text()
                onlysource = dialog.sourcebox.get_active()

                new_session = self.session_factory_storage
                rows = new_session.query(
                    Telemetry[self.decoding_type]
                ).join(
                    DbTelemetryPool,
                    Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
                ).filter(
                    DbTelemetryPool.pool_name == self.active_pool_info.filename
                ).filter(
                    Telemetry[self.decoding_type].idx.in_(indices)
                )
            except AttributeError as error:
                self.logger.error(error)
                dialog.destroy()
                return

            if st != '':
                rows = rows.filter(DbTelemetry.stc == int(st))
            if sst != '':
                rows = rows.filter(DbTelemetry.sst == int(sst))

            packets = [row.raw for row in rows]
            new_session.close()
            if onlysource:
                packetdata = [tm[TM_HEADER_LEN:-PEC_LEN] for tm in packets]
            else:
                packetdata = packets
            self.selected_packet(packetdata)
        dialog.destroy()

    def selected_packet(self, packet=None):
        if packet is not None:
            self.stored_packet = packet
            return packet
        else:
            return str(self.stored_packet)

    def get_packets_from_indices(self, indices=[], filtered=False, merged_tables=False):
        new_session = self.session_factory_storage

        if not merged_tables:
            rows = new_session.query(
                Telemetry[self.decoding_type]
            ).join(
                DbTelemetryPool,
                Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
            ).filter(
                DbTelemetryPool.pool_name == self.active_pool_info.filename
            )

            if len(indices) != 0:
                rows = rows.filter(
                    Telemetry[self.decoding_type].idx.in_(indices)
                )

            if filtered and self.filter_rules_active:
                rows = self._filter_rows(rows)

            ret = (row.raw for row in rows)

        else:
            ret = self.get_raw_from_merged_tables(self.active_pool_info.filename)

        new_session.close()
        return ret

    def get_raw_from_merged_tables(self, pool_name, filtered=False):
        # db = self.session_factory_storage
        # q1 = db.query(RMapTelemetry.idx,RMapTelemetry.raw).join(DbTelemetryPool,RMapTelemetry.pool_id==DbTelemetryPool.iid).filter(DbTelemetryPool.pool_name==pool_name)
        # q2 = db.query(FEEDataTelemetry.idx,FEEDataTelemetry.raw).join(DbTelemetryPool,FEEDataTelemetry.pool_id==DbTelemetryPool.iid).filter(DbTelemetryPool.pool_name==pool_name)
        # rows = q1.union_all(q2).order_by(FEEDataTelemetry.idx)

        # if filtered and self.filter_rules_active:
        #     rows = self._filter_rows(rows)
        # return (p.raw for p in q.yield_per(1000))

        que = 'SELECT idx,raw FROM rmap_tm LEFT JOIN tm_pool ON pool_id=tm_pool.iid WHERE pool_name="{}"\
        UNION SELECT idx,raw FROM feedata_tm LEFT JOIN tm_pool ON pool_id=tm_pool.iid WHERE pool_name="{}"\
        ORDER BY idx'.format(pool_name, pool_name)

        # alternative fetch with stream
        # conn = self.session_factory_storage.connection()
        # res = conn.execution_options(stream_results=True).execute(que)
        # self.session_factory_storage.close()

        res = self.session_factory_storage.execute(que)
        return (row[1] for row in res)

    def plot_parameters(self, widget=None, parameters={}, start_live=False):
        #if self.active_pool_info is None:
        #    self.logger.warning('Cannot open plot window without pool!')
        #    print('Cannot open plot window without pool!')
        #    return

        cfl.start_plotter(False, str(self.active_pool_info.pool_name))

        # Delete the logger = self.logger part if the plotter is a standalone process
        #pv = PlotViewer(loaded_pool=self.active_pool_info, cfg=self.cfg, parameters=parameters,
        #                start_live=start_live)
        # pv.set_transient_for(self)
        #pv.set_title('Parameter Viewer')
        return

    def start_recording(self, widget=None):
        if cfl.is_open('poolmanager', cfl.communication['poolmanager']):
            poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        else:
            path_pm = os.path.join(confignator.get_option('paths', 'ccs'), 'pus_datapool.py')
            pmgr = subprocess.Popen(['python3', path_pm])
            #print('Poolmanager has been started and is running in the background')
            return

        if poolmgr.Variables('gui_running'):
            poolmgr.Functions('raise_window')
            return
        # Ignore_reply is no problem here since only the gui is started
        poolmgr.Functions('start_gui', ignore_reply = True)
        return

    def stop_recording(self, widget=None, pool_name=None):
        if not self.active_pool_info.live:
            return False

        if cfl.is_open('poolmanager', cfl.communication['poolmanager']):
            poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        else:
            poolmgr = None

        if pool_name is None:
            pool_name = self.active_pool_info.pool_name

        # Not necessary done in Poolmanager
        # Dictionarie in Dictionaries are not very well supported over dbus connection
        # Get dictonary connections, key pool_name, key 'recording' set to False, True to change
        #poolmgr.Dictionaries('connections', pool_name, 'recording', False, True)

        if self.active_pool_info.pool_name == pool_name:
            self.active_pool_info = ActivePoolInfo(pool_name, self.active_pool_info.modification_time, pool_name, False)
            if poolmgr:
                poolmgr.Functions('loaded_pools_func', pool_name, self.active_pool_info)

        else:
            # Check if the pool name does exist
            try:
                pinfo = poolmgr.Dictionaries('loaded_pools', pool_name)
            except:
                print('Please give correct pool name')
                self.logger.info('Stop Recording: Not existing PoolName was given')
                return

            pinfo_modification_time = int(pinfo[2])
            #poolmgr.Functions('loaded_pools_func', pool_name, ActivePoolInfo(pool_name, pinfo_modification_time, pool_name, False), ignore_reply=True)
            if poolmgr:
                poolmgr.Functions('loaded_pools_func', pool_name,
                                  ActivePoolInfo(pool_name, pinfo_modification_time, pool_name, False))


        # Update the Poolmanager GUI
        #poolmgr.Functions('disconnect', pool_name, ignore_reply = True)
        if poolmgr:
            poolmgr.Functions('disconnect', pool_name)

        iter = self.pool_selector.get_active_iter()
        mod = self.pool_selector.get_model()
        if mod is not None:
            mod[iter][1] = self.live_signal[self.active_pool_info.live]
            self.stop_butt.set_sensitive(False)

        return

    def stop_recording_info(self, pool_name=None):
        """
        Connection is closed by the Poolmanager, Informes the Pool Viewer to stop updating or
        Poolmanager is closed and therefore all Pools become static pools
        Functions is normally called by the poolmanager when it is closing or disconnecting any connections
        """

        # if no pool name was specified, Change all connections to static
        if not pool_name:
            mod = self.pool_selector.get_model()
            self.active_pool_info = ActivePoolInfo(self.active_pool_info.filename,
                                                   self.active_pool_info.modification_time,
                                                   self.active_pool_info.pool_name, False)
            #self.active_pool_info.live = False
            for row in mod:
                mod[row.iter][1] = self.live_signal[self.active_pool_info.live]
                self.stop_butt.set_sensitive(False)

        # If active pool is live change it to static
        elif self.active_pool_info.pool_name == pool_name:
            self.active_pool_info = ActivePoolInfo(self.active_pool_info.filename, self.active_pool_info.modification_time, self.active_pool_info.pool_name, False)

            iter = self.pool_selector.get_active_iter()
            mod = self.pool_selector.get_model()
            if mod is not None:
                mod[iter][1] = self.live_signal[self.active_pool_info.live]
                self.stop_butt.set_sensitive(False)

        # Specific Pool is no longer LIVe
        else:
            mod = self.pool_selector.get_model()
            for row in mod:
                if mod[row.iter][0] == pool_name:
                    mod[row.iter][1] = self.live_signal[self.active_pool_info.live]
                    self.stop_butt.set_sensitive(False)

        return

    def refresh_treeview(self, pool_name):
        # thread = threading.Thread(target=self.refresh_treeview_worker, args=[pool_name])
        # thread.daemon = True
        # thread.start()
        self.n_pool_rows = 0
        GLib.timeout_add(self.pool_refresh_rate * 1000, self.refresh_treeview_worker2,
                         pool_name)  # , priority=GLib.PRIORITY_HIGH)

    def refresh_treeview_worker(self, pool_name):
        poolmgr = cfl.dbus_connection('poolmanager', cfl.communication ['poolmanager'])
        # while not self.pool.recordingThread.stopRecording:
        # Get value of dict connections, with key self.active... and key recording, True to get
        pool_connection_recording = cfl.Dictionaries(poolmgr, 'connections', self.active_pool_info.pool_name, 'recording', True)
        type = self.decoding_type
        #while self.pool.connections[self.active_pool_info.pool_name]['recording']:
        while pool_connection_recording:
            GLib.idle_add(self.scroll_to_bottom)
            time.sleep(self.pool_refresh_rate)
            if pool_name != self.active_pool_info.pool_name or type != self.decoding_type:
                dbsession.close()
                return
        self.stop_recording()

    def refresh_treeview_worker2(self, pool_name):
        if pool_name != self.active_pool_info.pool_name:
            return False

        #if not self.active_pool_info.live:
        #    return False
        #if cfl.is_open('poolmanager', cfl.communication['poolmanager']):
        #    poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        #else:
        #    return False

        # Get value of dict connections, with key self.active... and key recording, True to get
        #pool_connection_recording = poolmgr.Dictionaries('connections', self.active_pool_info.pool_name, 'recording',
        #                                                 True)
        #pool_connection = poolmgr.Dictionaries('connections', self.active_pool_info.pool_name)
        if self.active_pool_info.live:
        #if self.pool.connections[self.active_pool_info.pool_name]['recording']:
            rows = self.get_current_pool_rows()
            if rows.first() is None:
                cnt = 0
            else:
                cnt = rows.order_by(Telemetry[self.decoding_type].idx.desc()).first().idx
            if cnt != self.n_pool_rows:
                # self.selection.disconnect_by_func(self.tree_selection_changed)
                self.scroll_to_bottom(n_pool_rows=cnt, rows=rows)
                # self.selection.connect('changed', self.tree_selection_changed)
                self.n_pool_rows = cnt
                return True
            else:
                return True
        else:
            #self.stop_recording()
            return False

    def dbtest(self, pool_name, sleep=0.1):
        dbcon = self.session_factory_storage
        while self.testing:
            rows = dbcon.query(
                Telemetry[self.decoding_type]
            ).join(
                DbTelemetryPool,
                Telemetry[self.decoding_type].pool_id == DbTelemetryPool.iid
            ).filter(
                DbTelemetryPool.pool_name == pool_name
            )
            # cnt = rows.count()
            cnt = rows.order_by(Telemetry[self.decoding_type].idx.desc()).first().idx
            # print(cnt)
            rows = rows.filter(Telemetry[self.decoding_type].idx > (cnt - 100)).offset(100 - 25
                                                                     ).limit(
                25
            ).all()
            # rr=[row for row in rows]
            print('fetched', rows[-1].idx, cnt, 'at', time.time())
            dbcon.close()
            time.sleep(sleep)
        print('TEST ABORTED')

    def starttest(self, pool_name, sleep=0.1):
        t = threading.Thread(target=self.dbtest, args=[pool_name, sleep])
        t.daemon = True
        t.start()

    def scroll_to_bottom(self, n_pool_rows=None, rows=None):
        if self.active_pool_info.live:
            if n_pool_rows is None:
                cnt = self.count_current_pool_rows()
            else:
                cnt = n_pool_rows
            self.adj.set_upper(cnt)
            if self.autoscroll:
                self._scroll_treeview(self.adj.get_upper(), rows=rows)
                self.reselect_rows()
        else:
            self._scroll_treeview(self.adj.get_upper(), rows=rows)

    def change_cursor(self, window, name='default'):
        window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), name))

    def show_data_rate(self, refresh_rate=1, instance=1):
        '''
    # while self.is_visible():
        if not self.is_visible():
            return False
        with self.pool.lock:
            data_rate = self.pool.databuflen*refresh_rate
            self.pool.databuflen = 0
            tc_data_rate = self.pool.tc_databuflen*refresh_rate
            self.pool.tc_databuflen = 0
            if self.active_pool_info is not None:
                try:
                    trashbytes = self.pool.trashbytes[self.active_pool_info.filename]
                except KeyError:
                    trashbytes = 0
            else:
                trashbytes = 0
        '''
        if not self.active_pool_info.live:
            return

        if not instance:
            instance = 1
        try:
            pmgr = cfl.dbus_connection('poolmanager', instance)
            trashbytes, tc_data_rate, data_rate = pmgr.Functions('calc_data_rate', self.active_pool_info.filename, refresh_rate)
            self.statusbar.push(0, 'Trash: {:d} B | TC: {:7.3f} KiB/s | TM: {:7.3f} KiB/s'.format(
                trashbytes, tc_data_rate/1024, data_rate/1024))
        except:
            pass
        return True
        # time.sleep(refresh_rate)

    def show_bigdata(self, *args):
        self.bigd = BigDataViewer(self)


class ExtractionDialog(Gtk.MessageDialog):
    def __init__(self, parent=None, pkttype='PUS'):
        super(ExtractionDialog, self).__init__(title="Extract packets", parent=parent, flags=0,
                                               buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK,
                                                        Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        self.set_transient_for(parent)

        box = self.get_content_area()
        self.set_markup('Select Service Type and Subtype to be extracted (PUS)')

        hbox = Gtk.HBox()

        self.st = Gtk.Entry()
        self.sst = Gtk.Entry()
        self.st.set_placeholder_text('Service Type')
        self.sst.set_placeholder_text('Service Subtype')

        hbox.pack_start(self.st, 0, 0, 0)
        hbox.pack_start(self.sst, 0, 0, 0)
        hbox.set_homogeneous(True)

        self.sourcebox = Gtk.CheckButton.new_with_label('Source data only')

        box.pack_end(self.sourcebox, 0, 0, 0)
        box.pack_end(hbox, 0, 0, 5)

        if pkttype != 'PUS':
            self.st.set_sensitive(False)
            self.sst.set_sensitive(False)
            self.sourcebox.set_sensitive(False)

        self.show_all()


class SavePoolDialog(Gtk.FileChooserDialog):
    def __init__(self, parent=None):
        super(SavePoolDialog, self).__init__(title="Save packets", parent=parent, action=Gtk.FileChooserAction.SAVE)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                      Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        # Gtk.FileChooserDialog.__init__(self, "Save packets", parent=parent, action=Gtk.FileChooserAction.SAVE, buttons=(
        #     Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK))

        # self.set_transient_for(parent)

        area = self.get_content_area()

        hbox = Gtk.HBox()
        hbox.set_border_width(10)

        self.formatbox = Gtk.HBox()

        binbut = Gtk.RadioButton.new_with_label_from_widget(None, 'binary')
        hexbut = Gtk.RadioButton.new_with_label_from_widget(binbut, 'hex')
        csvbut = Gtk.RadioButton.new_with_label_from_widget(binbut, 'csv (decoded)')

        self.formatbox.pack_start(binbut, 0, 0, 3)
        self.formatbox.pack_start(hexbut, 0, 0, 3)
        self.formatbox.pack_start(csvbut, 0, 0, 3)

        self.selectiononly = Gtk.CheckButton.new_with_label('Save only selected packets')
        self.crccheck = Gtk.CheckButton.new_with_label('CRC')
        self.crccheck.set_tooltip_text('Save only packets that pass CRC')
        self.store_in_db = Gtk.CheckButton.new_with_label('Store in DB')
        self.store_in_db.set_tooltip_text('Permanently store pool in DB - THIS MAY TAKE A WHILE FOR LARGE DATASETS!')
        self.save_filtered = Gtk.CheckButton.new_with_label('Apply packet filter')
        self.save_filtered.set_tooltip_text('Save only packets according to the currently active poolview filter')
        self.merge_tables = Gtk.CheckButton.new_with_label('Merge tables')
        self.merge_tables.set_tooltip_text('Merge and save all packet types from the same pool/connection')

        hbox.pack_start(self.formatbox, 0, 0, 0)
        hbox.pack_start(self.selectiononly, 0, 0, 0)
        hbox.pack_start(self.crccheck, 0, 0, 0)
        hbox.pack_start(self.store_in_db, 0, 0, 0)
        hbox.pack_start(self.save_filtered, 0, 0, 0)
        hbox.pack_start(self.merge_tables, 0, 0, 0)

        hbox.set_homogeneous(True)

        area.add(hbox)  # ,0,0,10)

        self.show_all()


# TODO
class LoadPoolDialog(Gtk.FileChooserDialog):
    def __init__(self, parent=None):
        super(LoadPoolDialog, self).__init__(title="Save packets", parent=parent, action=Gtk.FileChooserAction.SAVE,
                                             buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                      Gtk.STOCK_SAVE, Gtk.ResponseType.OK))

        dialog = Gtk.FileChooserDialog(title="Load File to pool", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        area = dialog.get_content_area()
        hbox, force_button, brute_extract, type_buttons = self.pool_loader_dialog_buttons()

        area.add(hbox)
        area.show_all()

        self.show_all()


class NavigationToolbarX(NavigationToolbar):

    # override this function to avoid call to Gtk.main_iteration,
    # which causes crash when multiple PlotViewer instances are running
    def set_cursor(self, cursor):
        self.canvas.get_property("window").set_cursor(cursord[cursor])

    def release_zoom(self, event):
        """the release mouse button callback in zoom to rect mode"""
        for zoom_id in self._ids_zoom:
            self.canvas.mpl_disconnect(zoom_id)
        self._ids_zoom = []

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
'''
class LoadInfo(Gtk.Window):
    def __init__(self, parent=None, title=None):
        Gtk.Window.__init__(self)

        if title is None:
            self.set_title('Loading data to pool...')
        else:
            self.set_title(title)

        grid = Gtk.VBox()
        logo = Gtk.Image.new_from_file('pixmap/cheops-logo-with-additional3.png')

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.log = Gtk.Label()
        self.ok_button = Gtk.Button.new_with_label('OK')
        self.ok_button.connect('clicked', self.destroy_window, self)

        grid.pack_start(logo, 1, 1, 0)
        grid.pack_start(self.spinner, 1, 1, 0)
        grid.pack_start(self.log, 1, 1, 0)
        grid.pack_start(self.ok_button, 1, 1, 0)
        grid.set_spacing(2)

        self.add(grid)

        self.show_all()

    def destroy_window(self, widget, window):
        window.destroy()

'''
class RecordingDialog(Gtk.MessageDialog):
    def __init__(self, parent=None):
        Gtk.Dialog.__init__(self, "Record to pool", parent, 0,
                            buttons=(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        # self.set_transient_for(parent)
        ok_butt = self.get_action_area().get_children()[0]
        ok_butt.set_always_show_image(True)
        ok_butt.set_image(Gtk.Image.new_from_icon_name('gtk-media-record', Gtk.IconSize.BUTTON))
        ok_butt.set_label('Connect')
        ok_butt.set_sensitive(True)

        box = self.get_content_area()
        self.set_markup('Start recording from socket:')

        vbox = Gtk.VBox()
        vbox.set_spacing(2)

        self.host = Gtk.Entry(text="127.0.0.1")
        self.host.connect('changed', self.check_entry, ok_butt)
        self.port = Gtk.Entry(text="5570")
        self.port.connect('changed', self.check_entry, ok_butt)
        self.pool_name = Gtk.Entry(text="LIVE")
        self.pool_name.connect('changed', self.check_entry, ok_butt)
        self.host.set_placeholder_text('Host')
        self.port.set_placeholder_text('Port')
        self.pool_name.set_placeholder_text('Pool name')

        vbox.pack_start(self.host, 0, 0, 0)
        vbox.pack_start(self.port, 0, 0, 0)
        vbox.pack_start(self.pool_name, 0, 0, 0)
        vbox.set_homogeneous(True)

        box.pack_end(vbox, 0, 0, 0)
        self.set_focus(self.get_action_area().get_children()[1])
        self.show_all()

    def check_entry(self, widget, button):
        fields = self.get_content_area().get_children()[1].get_children()
        if not all([len(field.get_text()) for field in fields]):
            button.set_sensitive(False)
            return
        try:
            int(self.port.get_text())
            button.set_sensitive(True)
        except ValueError:
            button.set_sensitive(False)


class BigDataViewer(Gtk.Window):
    def __init__(self, pv):
        super(BigDataViewer, self).__init__()
        self.pv = pv
        self.interval = 0.05
        self.connect('delete-event', self.stop_thread)

        self.hscale = 1
        self.maxhscale = 8
        self.minhscale = 0.125

        self.init_ui()
        self.start_cycle()

    def init_ui(self):
        self.darea = Gtk.DrawingArea()
        self.darea.connect("draw", self.on_draw)
        self.darea.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.darea.add_events(Gdk.EventMask.SCROLL_MASK)
        self.darea.connect("button-press-event", self.on_button_press)
        self.darea.connect("scroll-event", self.set_hscale)
        self.add(self.darea)

        self.set_title("Big Data")
        self.resize(500, 800)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.show_all()

    def on_draw(self, widget, cr):
        poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        #res = poolmgr.Functions('_return_colour_list')
        #print(res)
        #print(type(res))
        check = poolmgr.Functions('_return_colour_list', 'try')
        if check is False:
            return

        n = int(self.darea.get_allocated_height() / self.hscale)
        w = self.darea.get_allocated_width()
        length = poolmgr.Functions('_return_colour_list', 'length')
        for i in range(min(n, length)):
        #for i in range(min(n, len(self.pv.pool.colour_list))):
            #rgb, pcktlen = self.pv.pool.colour_list[-i - 1]
            rgb, pcktlen = poolmgr.Functions('_return_colour_list', i)
            cr.rectangle(0, self.hscale * (n - i), (pcktlen + 7) / 1024 * w, self.hscale)
            cr.set_source_rgb(*rgb)
            cr.fill()

        # cr.translate(220, 180)
        # cr.scale(1, 0.7)
        # cr.fill()

    def on_button_press(self, w, e):

        if e.type == Gdk.EventType.BUTTON_PRESS and e.button == 1:
            self.start_cycle()
            # self.palette = [np.random.random(3) for i in range(1000)]
            # self.darea.queue_draw()

        if e.type == Gdk.EventType.BUTTON_PRESS and e.button == 3:
            self.darea.queue_draw()
            self.cycle_on = False

    def start_cycle(self):
        self.cycle_on = True
        if 'BigDataViewer' in [x.name for x in threading.enumerate()]:
            # self.interval /= 2.
            return
        t = threading.Thread(target=self.cycle_worker)
        t.setName('BigDataViewer')
        t.setDaemon(True)
        t.start()

    def cycle_worker(self):
        while self.cycle_on:
            GLib.idle_add(self.darea.queue_draw)
            time.sleep(self.interval)

    def stop_thread(self, widget=None, data=None):
        self.cycle_on = False

    def set_hscale(self, widget, event):
        if event.direction.value_name == 'GDK_SCROLL_SMOOTH':
            scale = 2 ** (-event.delta_y)
        # needed for remote desktop
        elif event.direction.value_name == 'GDK_SCROLL_UP':
            scale = 2
        elif event.direction.value_name == 'GDK_SCROLL_DOWN':
            scale = 0.5
        else:
            return
        self.hscale = max(min(self.hscale * scale, self.maxhscale), self.minhscale)


class UnsavedBufferDialog(Gtk.MessageDialog):
    def __init__(self, parent=None, msg=None):
        Gtk.MessageDialog.__init__(self, title="Close Poolmanager?", parent=parent, flags=0,
                                   buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                   Gtk.STOCK_NO, Gtk.ResponseType.NO,
                                    Gtk.STOCK_YES, Gtk.ResponseType.YES,))
        head, message = self.get_message_area().get_children()
        if msg is None:
            head.set_text('Response NO will keep the Poolmanager running in the Background')
        else:
            head.set_text(msg)

        self.show_all()


def run(pool_name):
    bus_name = cfg.get('ccs-dbus_names', 'poolviewer')

    DBusGMainLoop(set_as_default=True)

    pv = TMPoolView(pool_name=pool_name)

    DBus_Basic.MessageListener(pv, bus_name, *sys.argv)

    Gtk.main()


if __name__ == "__main__":
    given_cfg = None
    for i in sys.argv:
        if i.endswith('.cfg'):
            given_cfg = i
    if given_cfg:
        cfg = confignator.get_config(file_path=given_cfg)
    else:
        cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))

    poolname = None
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if not arg.startswith('-'):
                poolname = arg

    run(pool_name=poolname)


