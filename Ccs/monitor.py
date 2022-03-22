import json
import threading
import time
import sys
import DBus_Basic
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gi
import confignator
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from database.tm_db import DbTelemetryPool, DbTelemetry, scoped_session_maker
from sqlalchemy.sql.expression import func
import ccs_function_lib as cfl

INTERVAL = 1.
MAX_AGE = 20.


class ParameterMonitor(Gtk.Window):
    limit_colors = {0: "green", 1: "orange", 2: "red"}
    alarm_colors = {'red': Gdk.RGBA(1, 0, 0, 1), 'orange': Gdk.RGBA(1, 0.647059, 0, 1),
                    'green': Gdk.RGBA(0.913725, 0.913725, 0.913725, 1.)}
    parameter_types = {"S": "s", "N": ".3G"}

    def __init__(self, given_cfg=None, pool_name=None, parameter_set=None, interval=INTERVAL, max_age=MAX_AGE, user_limits=None):

        Gtk.Window.__init__(self, title="Parameter Monitor (Pool: {:})".format(pool_name))
        self.set_border_width(10)
        self.set_resizable(True)

        self.pdescr = {}

        self.interval = interval
        self.max_age = max_age

        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        if isinstance(given_cfg, str):
            self.cfg = confignator.get_config(file_path=given_cfg)
        else:
            self.cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))

        # Set up the logger
        self.logger = cfl.start_logging('ParameterMonitor')

        if user_limits is None:
            self.user_limits = {}
        else:
            self.user_limits = user_limits
        self.presented = False

        self.events = {'Error LOW': [(5, 2), 0], 'Error MEDIUM': [(5, 3), 0], 'Error HIGH': [(5, 4), 0]}
        self.evt_reset_values = {'Error LOW': 0, 'Error MEDIUM': 0, 'Error HIGH': 0}
        # self.box = Gtk.VBox()
        # self.menubar = Gtk.MenuBar()

        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(False)

        hbox = Gtk.HBox()
        self.add(hbox)

        self.evt_cnt = self.create_event_counter()
        self.evt_check_enabled = True
        self.evt_check_tocnt = 0

        self.parameter_set = parameter_set
        self.parameters = {}
        self.monitored_pkts = None

        # Is now done in the __name__ == __main__ part
        #if parameter_set is not None:
        #    self.set_parameter_view(parameter_set)

        hbox.pack_start(self.evt_cnt, 0, 0, 0)
        hbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), 0, 1, 0)
        hbox.pack_start(self.grid, 1, 1, 0)

        # Add Univie Button
        univie_box = self.create_univie_box()
        hbox.pack_start(univie_box, 0, 1, 0)

        hbox.set_spacing(20)

        # Is now done in the __name__ == __main__ part
        #if pool_name is not None:
        #    self.set_pool(pool_name)
        #self.update_parameter_view(interval=interval, max_age=max_age)

        self.connect('destroy', self.destroy_monitor)

        self.show_all()

    def destroy_monitor(self, widget=None):
        self.updating = False
        self.reset_evt_cnt()
        return

    def check_for_pools(self):
        try:
            poolmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
            pools = poolmgr.Functions('loaded_pools_export_func')
            if len(pools) == 1:
                pool_name = pools[0][0]
                if '/' in pools[0][0]:
                    pool_name = pools[0][0].split('/')[-1]
                self.set_pool(pool_name)
            else:
                print('Could not determine which pool should be used')
                self.logger.info('To many pools running in manager, could not determine which one to use')
        except:
            return

    def set_pool(self, pool_name):
        self.pool_name = pool_name
        self.set_title("Parameter Monitor (Pool: {:})".format(pool_name))
        self.update_parameter_view(interval=self.interval, max_age=self.max_age)
        # self.tmlist = self.ccs.get_pool_pckts_list(self.poolmgr.loaded_pools[self.pool_name], dbcon=self.dbcon)

    def create_event_counter(self):
        evt_cnt = Gtk.VBox()
        # evt_cnt.set_homogeneous(True)

        for evt in self.events:
            box = Gtk.HBox()
            pname, pvalue = Gtk.Label(), Gtk.TextView()
            pname.set_markup('<span size="large" weight="bold">{}</span>'.format(evt))
            pname.set_xalign(0)
            pname.set_tooltip_text('# of TM{} packets in pool'.format(','.join(map(str, self.events[evt][0]))))

            buf = Gtk.TextBuffer()
            buf.insert_markup(buf.get_start_iter(),
                              '<span size="large" foreground="black" weight="bold">{}</span>'.format(0), -1)
            pvalue.set_buffer(buf)
            pvalue.set_editable(False)
            pvalue.set_cursor_visible(False)
            pvalue.set_justification(Gtk.Justification.RIGHT)
            pvalue.set_monospace(True)

            box.pack_start(pname, 1, 1, 0)
            box.pack_start(pvalue, 0, 1, 0)
            box.set_spacing(10)

            evt_cnt.pack_start(box, 0, 0, 0)

        reset_button = Gtk.Button(label='Reset')
        reset_button.connect('clicked', self.reset_evt_cnt)

        set_button = Gtk.Button(label='Set Parameter')
        set_button.connect('clicked', self.add_evt_cnt)

        evt_cnt.pack_start(reset_button, 0, 0, 0)
        evt_cnt.pack_start(set_button, 0, 0, 0)
        evt_cnt.set_spacing(7)

        return evt_cnt

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
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for name in self.cfg['ccs-dbus_names']:
            start_button = Gtk.Button.new_with_label("Start " + name.capitalize() + '   ')
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

    def set_parameter_view(self, parameter_set):
        # update user_limit dict
        dbcon = self.session_factory_idb
        dbres = dbcon.execute(
            'SELECT pcf_name, pcf_descr from pcf where pcf_descr in ("{}")'.format('","'.join(self.user_limits.keys())))
        descrs = dbres.fetchall()
        dbcon.close()
        self.pdescr = {x[0]: x[1] for x in descrs}
        if self.cfg.has_option('ccs-monitor_parameter_sets', parameter_set):
            parameters = json.loads(self.cfg['ccs-monitor_parameter_sets'][parameter_set])
            self.setup_grid(parameters)
        else:
            self.logger.warning('Parameter Set "{}" does not exist'.format(parameter_set))
        return

    def setup_grid(self, parameters):
        [self.grid.remove(cell) for cell in self.grid.get_children()]
        dbcon = self.session_factory_idb
        for ncol, col in enumerate(parameters):
            for nrow, parameter in enumerate(col):
                box = Gtk.HBox()
                parameter, *pktid = eval(parameter)
                box.pktid = tuple(pktid)
                dbres = dbcon.execute('SELECT pcf.pcf_name,pcf.pcf_descr,pcf.pcf_categ,pcf.pcf_unit,ocf.ocf_nbool,\
                                    ocp.ocp_lvalu,ocp.ocp_hvalu from pcf left join ocf on pcf.pcf_name=ocf.ocf_name\
                                    left join ocp on ocf_name=ocp_name where pcf.pcf_name="{}"'.format(parameter))

                boxdata = dbres.fetchall()
                try:
                    nlims = boxdata[0][-3]
                    if nlims in (1, None):
                        box.param_id, plabel, box.format, unit, _, lolim, hilim = boxdata[0]
                        hardlim = (lolim, hilim)
                        softlim = (None, None)
                    else:
                        box.param_id, plabel, box.format, unit = boxdata[0][:4]
                        softlim, hardlim = [(x[-2], x[-1]) for x in boxdata]
                except IndexError:
                    self.logger.error('Parameter {} does not exist - cannot add!'.format(parameter))
                    continue
                # override with user defined limits
                if self.pdescr.get(parameter) in self.user_limits:
                    try:
                        softlim = self.user_limits[self.pdescr[parameter]]['soft']
                    except KeyError:
                        softlim = (None, None)
                    hardlim = self.user_limits[self.pdescr[parameter]]['hard']

                box.limits = (softlim, hardlim)

                pname, pvalue = Gtk.Label(), Gtk.TextView()
                pname.set_markup('<span size="large" weight="bold">{} [{}]</span>'.format(plabel, unit))
                pname.set_xalign(0)
                pname.set_tooltip_text(box.param_id)

                buf = Gtk.TextBuffer()
                buf.insert_markup(buf.get_start_iter(),
                                  '<span size="large" foreground="grey" weight="bold">{}</span>'.format('--'), -1)

                pvalue.set_buffer(buf)
                pvalue.set_editable(False)
                pvalue.set_cursor_visible(False)
                pvalue.set_justification(Gtk.Justification.RIGHT)
                pvalue.set_monospace(True)
                pvalue.set_tooltip_markup('<b>Limits:\n<span foreground="orange">{} &lt; x &lt; {}</span>\n<span\
                foreground="red">{} &lt; x &lt; {}</span></b>'.format(*softlim, *hardlim))

                box.pack_start(pname, 1, 1, 0)
                box.pack_start(pvalue, 1, 1, 0)

                box.set_spacing(5)
                box.set_homogeneous(True)
                self.grid.attach(box, ncol, nrow, 1, 1)

        dbcon.close()

        self.grid.set_row_spacing(6)
        self.grid.set_column_spacing(30)

        parameter_grid = self.grid.get_children()

        for parameter in parameter_grid:
            self.parameters[parameter.param_id] = {'field': parameter.get_children()[1], 'value': None,
                                                   'format': parameter.format, 'alarm': None, 'pktid': parameter.pktid}

        self.monitored_pkts = {self.parameters[k]['pktid']: {'pkttime': 0, 'reftime': time.time(), 'data': None} for k in self.parameters}

        self.grid.show_all()
        return

    def update_parameter_view(self, interval=INTERVAL, max_age=MAX_AGE):
        self.interval = interval
        self.max_age = max_age
        self.updating = True

        thread = threading.Thread(target=self.update_parameters, name='monitor')
        thread.daemon = True
        thread.start()

    def update_parameters(self):
        while not self.parameters:
            time.sleep(self.interval)

        while self.updating:
            start = time.time()
            self.update_parameters_worker()
            dt = time.time() - start
            # print(dt)
            time.sleep(self.interval - min(self.interval, dt))

    def update_parameters_worker(self):
        rows = cfl.get_pool_rows(self.pool_name)

        if self.evt_check_enabled:
            ctime = time.time()
            self.check_evts(rows)
            cdt = time.time() - ctime
            # disable check_evts if it causes too much delay
            if cdt > 0.7 * self.interval:
                self.evt_check_tocnt += 1
                if self.evt_check_tocnt > 5:
                    self.disable_evt_cnt()

        for pktid in self.monitored_pkts:
            pktinfo = self.get_last_pkt_with_id(rows, pktid)

            if pktinfo is None:
                continue

            pkttime, pkt = pktinfo
            if pkttime != self.monitored_pkts[pktid]['pkttime']:
                self.monitored_pkts[pktid]['reftime'] = time.time()
                self.monitored_pkts[pktid]['pkttime'] = pkttime

                tm = cfl.Tmdata(pkt)[0]
                self.monitored_pkts[pktid]['data'] = {par[4][1][0]: par[0] for par in tm}

        checktime = time.time()
        for pname in self.parameters:

            pktid = self.parameters[pname]['pktid']

            if self.monitored_pkts[pktid]['data'] is None:
                self.parameters[pname]['value'] = None
                self.parameters[pname]['alarm'] = "blue"
                continue
            else:
                try:
                    value = self.monitored_pkts[pktid]['data'][pname]
                except Exception as err:
                    self.logger.warning('Could not update value of {} [{}]!'.format(pname, str(err)))
                    continue

            if checktime - self.monitored_pkts[pktid]['reftime'] > self.max_age:
                limit_color = 'grey'
            else:
                if self.pdescr.get(pname) in self.user_limits:
                    user_limit = self.user_limits[self.pdescr[pname]]
                else:
                    user_limit = None
                limit_color = self.limit_colors[cfl.Tm_limits_check(pname, value, user_limit)]

            self.parameters[pname]['value'] = value
            self.parameters[pname]['alarm'] = limit_color

        def updt_buf():
            for par in self.parameters:
                buf = self.parameters[par]['field'].get_buffer()
                buf.delete(*buf.get_bounds())
                if self.parameters[par]['value'] is None:
                    buf.insert_markup(buf.get_start_iter(),
                                      '<span size="large" foreground="{}" weight="bold">{}</span>'.format(
                                          self.parameters[par]['alarm'], '--'), -1)
                else:
                    buf.insert_markup(buf.get_start_iter(),
                                      '<span size="large" foreground="{}" weight="bold">{:{fstr}}</span>'.format(
                                          self.parameters[par]['alarm'], self.parameters[par]['value'],
                                          fstr=self.parameter_types[self.parameters[par]['format']]), -1)

        GLib.idle_add(updt_buf)

        # def updt_bg_color():
        #     alarms = [self.parameters[x]['alarm'] for x in self.parameters.keys()]
        #     if alarms.count('red'):
        #         self.override_background_color(Gtk.StateType.NORMAL, self.alarm_colors['red'])
        #         if not self.presented:
        #             self.present()
        #             self.presented = True
        #     elif alarms.count('orange'):
        #         self.override_background_color(Gtk.StateType.NORMAL, self.alarm_colors['orange'])
        #         if not self.presented:
        #             self.present()
        #             self.presented = True
        #     else:
        #         self.override_background_color(Gtk.StateType.NORMAL, self.alarm_colors['green'])
        #         self.presented = False

        # GLib.idle_add(updt_bg_color)
        # return

    def get_last_pkt_with_id(self, rows, pktid):
        spid, st, sst, apid, pi1, pi1off, pi1wid = pktid
        if pi1off != -1:
            rows = rows.filter(DbTelemetry.stc == st, DbTelemetry.sst == sst, DbTelemetry.apid == apid,
                               func.mid(DbTelemetry.data, pi1off - cfl.TM_HEADER_LEN + 1, pi1wid // 8) == pi1.to_bytes(
                                pi1wid // 8, 'big')).order_by(DbTelemetry.idx.desc()).first()
        else:
            rows = rows.filter(DbTelemetry.stc == st, DbTelemetry.sst == sst, DbTelemetry.apid == apid).order_by(DbTelemetry.idx.desc()).first()

        if rows is None:
            return

        return float(rows.timestamp[:-1]), rows.raw

    def pckt_counter(self, rows, st, sst):
        npckts = rows.filter(DbTelemetry.stc == st, DbTelemetry.sst == sst).count()
        return npckts

    def check_evts(self, rows):
        def updt_buf(buf, evt):
            buf.delete(*buf.get_bounds())
            buf.insert_markup(buf.get_start_iter(),
                              '<span size="large" foreground="{}" weight="bold">{}</span>'.format(
                                  'red' if self.events[evt][1] > self.evt_reset_values[evt] else 'black',
                                  self.events[evt][1]), -1)

        for event in self.evt_cnt.get_children()[:-2]:
            evt = event.get_children()[0].get_text()

            self.events[evt][1] = self.pckt_counter(rows, *self.events[evt][0])

            buf = event.get_children()[1].get_buffer()

            GLib.idle_add(updt_buf, buf, evt)

        def updt_bg_color():
            if self.events['Error HIGH'][1] > self.evt_reset_values['Error HIGH']:
                self.override_background_color(Gtk.StateType.NORMAL, self.alarm_colors['red'])
                self.present()
            elif self.events['Error MEDIUM'][1] > self.evt_reset_values['Error MEDIUM']:
                self.override_background_color(Gtk.StateType.NORMAL, self.alarm_colors['orange'])

        # GLib.idle_add(updt_bg_color)

    def reset_evt_cnt(self, widget=None):
        panels = [x.get_children() for x in self.evt_cnt.get_children()[:-2]]
        for panel in panels:
            buf = panel[1].get_buffer()
            value = int(buf.get_text(*buf.get_bounds(), True))
            # reset alarm treshold for evts
            self.evt_reset_values[panel[0].get_text()] = value
        return

    def disable_evt_cnt(self, widget=None):
        self.evt_check_enabled = False

        def updt_buf(cbuf, cevt):
            cbuf.delete(*cbuf.get_bounds())
            cbuf.insert_markup(cbuf.get_start_iter(), '<span size="large" foreground="{}" weight="bold">{}</span>'.format(
                'grey', self.events[cevt][1]), -1)

        for evt in self.evt_cnt.get_children()[:-2]:
            evt.set_sensitive(False)
            buf = evt.get_children()[1]

            GLib.idle_add(updt_buf, buf.get_buffer(), evt.get_children()[0].get_text())

        rbutton = self.evt_cnt.get_children()[-2]
        rbutton.set_label('Count EVTs')
        rbutton.set_tooltip_text('Event counting has been disabled because of heavy load, probably because of a too large pool.\nClick to force count update.')
        self.logger.warning('Counting events takes too long - disabling.')

    def add_evt_cnt(self, widget=None):
        self.monitor_setup()

    def set_update_interval(self, widget=None, interval=1.0):
        self.interval = interval
        return

    def set_max_age(self, widget=None, max_age=20):
        self.max_age = max_age
        return

    def monitor_setup(self, parameter_set=None, nslots=3):
        if parameter_set is not None:
            parameters = json.loads(self.cfg['ccs-monitor_parameter_sets'][parameter_set])
            self.setup_grid(parameters)

            return

        dialog = MonitorSetupDialog(logger=self.logger, nslots=nslots, parameter_set=parameter_set, parent=self)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:

            slots = dialog.get_content_area().get_children()[0].get_children()[1].get_children()
            parameters = []
            for slot in slots:
                model = slot.get_children()[1].get_child().get_model()
                # parameters.append([self.descr_to_name(par[0]) for par in model])
                parameters.append([par[1] for par in model])

            parameter_set = dialog.label.get_active_text()
            self.cfg['ccs-monitor_parameter_sets'][parameter_set] = json.dumps(parameters)

            self.cfg.save_to_file()
            self.setup_grid(parameters)
            # self.set_pool(self.pool_name)
            dialog.destroy()

        else:
            dialog.destroy()

        return

    def descr_to_name(self, descr):
        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pcf_name from pcf where pcf_descr="{}"'.format(descr))
        name = dbres.fetchall()
        dbcon.close()
        if len(name) != 0:
            return name[0][0]
        else:
            return descr

    def set_user_limits(self, user_limits: dict):
        self.user_limits = user_limits
        self.set_parameter_view(self.parameter_set)
        return

    def add_user_limit(self, user_limit: dict):
        # check for hard limit
        if 'hard' not in user_limit[list(user_limit.keys())[0]]:
            raise KeyError('HARD LIMIT IS REQUIRED!')
        self.user_limits.update(user_limit)
        self.set_parameter_view(self.parameter_set)
        return

    def change_communication(self, application, instance=1, check=True):
        # If it is checked that both run in the same project it is not necessary to do it again
        if check:
            conn = cfl.dbus_connection(application, instance)
            # Both are not in the same project do not change

            if not conn.Variables('main_instance') == self.main_instance:
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
                        conn.Functions('change_communication', self.my_bus_name.split('.')[1], self.my_bus_name[-1], False)

        if not cfl.communication[self.my_bus_name.split('.')[1]]:
            cfl.communication[self.my_bus_name.split('.')[1]] = int(self.my_bus_name[-1])

        # Connect to all terminals
        if Count == 1:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "monitor = dbus.SessionBus().get_object('" +
                                     str(My_Bus_Name) + "', '/MessageListener')")

        else:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "monitor" +str(Count)+
                                     " = dbus.SessionBus().get_object('" + str(My_Bus_Name)+
                                     "', '/MessageListener')")

        return

    #Tell all terminals that app is closing
    def quit_func(self, *args):
        for service in dbus.SessionBus().list_names():
            if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                editor = cfl.dbus_connection(service[0:-1].split('.')[1], service[-1])
                if self.main_instance == editor.Variables('main_instance'):
                    nr = self.my_bus_name[-1]
                    if nr == str(1):
                        nr = ''
                    editor.Functions('_to_console_via_socket', 'del(monitor'+str(nr)+')')

        self.update_all_connections_quit()
        Gtk.main_quit()
        return

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
class MonitorSetupDialog(Gtk.Dialog):
    def __init__(self, logger, nslots=3, parameter_set=None, parent=None):
        Gtk.Dialog.__init__(self, "Monitoring Setup", parent, 0)
        self.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK, Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)

        self.monitor = parent

        # self.set_default_size(780,560)
        self.set_border_width(5)
        self.set_resizable(True)

        self.logger = logger

        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        box = self.get_content_area()

        slots = self.create_view(nslots=nslots, parameter_set=parameter_set)
        box.pack_start(slots, 1, 1, 0)

        self.ok_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        self.ok_button.set_sensitive(False)

        self.show_all()

    def create_view(self, nslots=3, parameter_set=None):
        parameter_view = self.create_param_view()

        slotbox = Gtk.HBox()
        slotbox.set_homogeneous(True)
        slotbox.set_spacing(50)

        self.slots = []

        if parameter_set is not None:
            if self.monitor.cfg.has_option('ccs-monitor_parameter_sets', parameter_set):
                parameter_set = json.loads(self.monitor.cfg['ccs-monitor_parameter_sets'][parameter_set])
                for i in range(parameter_set.count([])):  # remove empty slots
                    parameter_set.remove([])
                for group in parameter_set:
                    slot, sw, tv, pl = self.create_slot(group)
                    slotbox.pack_start(slot, 1, 1, 0)
                    self.slots.append([slot, sw, tv, pl])
                if len(parameter_set) < nslots:
                    for i in range(nslots - len(parameter_set)):
                        slot, sw, tv, pl = self.create_slot()
                        slotbox.pack_start(slot, 1, 1, 0)
                        self.slots.append([slot, sw, tv, pl])
            else:
                self.logger.warning('Parameter Set "{}" does not exist'.format(parameter_set))
                for n in range(nslots):
                    slot, sw, tv, pl = self.create_slot()
                    slotbox.pack_start(slot, 1, 1, 0)
                    self.slots.append([slot, sw, tv, pl])
        else:
            for n in range(nslots):
                slot, sw, tv, pl = self.create_slot()
                slotbox.pack_start(slot, 1, 1, 0)
                self.slots.append([slot, sw, tv, pl])

        self.label = Gtk.ComboBoxText.new_with_entry()
        #self.label.set_tooltip_text('Label')
        self.label_entry = self.label.get_child()
        self.label_entry.set_placeholder_text('Label for the current configuration')
        self.label_entry.set_width_chars(5)

        self.label.set_model(self.create_label_model())
        self.label.connect('changed', self.check_label)

        self.load_button = Gtk.Button(label='Load')
        self.load_button.set_tooltip_text('Load Parameter Set')
        self.load_button.connect('clicked', self.load_set)

        label_box = Gtk.HBox()
        label_box.pack_start(self.label, True, True, 0)
        label_box.pack_start(self.load_button, 0, 0, 0)

        #self.label = Gtk.Entry()
        #self.label.set_placeholder_text('Label for the current configuration')
        #self.label.connect('changed', self.check_label)

        box = Gtk.VBox()
        box.pack_start(parameter_view, 1, 1, 5)
        box.pack_start(slotbox, 1, 1, 2)
        box.pack_start(label_box, 0, 0, 3)

        return box

    def create_label_model(self):
        model = Gtk.ListStore(str)

        for decoder in self.monitor.cfg['ccs-monitor_parameter_sets'].keys():
            model.append([decoder])
        return model


    def create_param_view(self):
        self.treeview = Gtk.TreeView(model=self.create_parameter_model())

        self.treeview.append_column(Gtk.TreeViewColumn("Parameters", Gtk.CellRendererText(), text=0))
        hidden_column = Gtk.TreeViewColumn("ID", Gtk.CellRendererText(), text=1)
        hidden_column.set_visible(False)
        self.treeview.append_column(hidden_column)

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(200, 200)
        # workaround for allocation warning GTK bug
        # grid = Gtk.Grid()
        # grid.attach(self.treeview, 0, 0, 1, 1)
        # sw.add(grid)
        sw.add(self.treeview)

        return sw

    def create_slot(self, group=None):
        parameter_list = Gtk.ListStore(str, str)
        treeview = Gtk.TreeView(model=parameter_list)

        treeview.append_column(Gtk.TreeViewColumn("Parameters", Gtk.CellRendererText(), text=0))
        hidden_column = Gtk.TreeViewColumn("ID", Gtk.CellRendererText(), text=1)
        hidden_column.set_visible(False)
        treeview.append_column(hidden_column)
        treeview.set_headers_visible(False)

        # add parameters if modifying existing configuration
        if group is not None:
            for item in group:
                pname, *param_id = eval(item)
                descr, name = self.name_to_descr(pname)
                if descr is not None:
                    parameter_list.append([descr, item])

        sw = Gtk.ScrolledWindow()
        sw.set_size_request(100, 200)
        sw.add(treeview)

        bbox = Gtk.HBox()
        bbox.set_homogeneous(True)
        add_button = Gtk.Button(label='Add')
        add_button.connect('clicked', self.add_parameter, parameter_list)
        rm_button = Gtk.Button(label='Remove')
        rm_button.connect('clicked', self.remove_parameter, treeview)

        bbox.pack_start(add_button, 1, 1, 0)
        bbox.pack_start(rm_button, 1, 1, 0)

        vbox = Gtk.VBox()
        vbox.pack_start(bbox, 0, 0, 3)
        vbox.pack_start(sw, 1, 1, 0)

        return vbox, sw, treeview, parameter_list

    def name_to_descr(self, name):
        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pcf_descr, pcf_name FROM pcf WHERE pcf_name="{}"'.format(name))
        name = dbres.fetchall()
        dbcon.close()
        if len(name) != 0:
            return name[0]
        else:
            return None, None

    def create_parameter_model(self):
        parameter_model = Gtk.TreeStore(str, str)

        dbcon = self.session_factory_idb
        dbres = dbcon.execute('SELECT pid_descr,pid_spid,pid_type from pid order by pid_type,pid_stype,pid_pi1_val')
        hks = dbres.fetchall()

        topleveliters = {}
        for hk in hks:

            if not hk[2] in topleveliters:
                serv = parameter_model.append(None, ['Service ' + str(hk[2]), None])
                topleveliters[hk[2]] = serv

            it = parameter_model.append(topleveliters[hk[2]], [hk[0], None])

            dbres = dbcon.execute('SELECT pcf.pcf_descr, pcf.pcf_name, pid.pid_spid, pid.pid_type, pid.pid_stype, \
             pid.pid_apid, pid.pid_pi1_val, pic.pic_pi1_off, pic.pic_pi1_wid from pcf left join plf on\
             pcf.pcf_name=plf.plf_name left join pid on plf.plf_spid=pid.pid_spid left join pic\
             on pid.pid_type=pic.pic_type and pid.pid_stype=pic.pic_stype\
             and pid.pid_apid=pic.pic_apid where pid.pid_spid={}'.format(hk[1]))

            params = dbres.fetchall()

            [parameter_model.append(it, [par[0], str(par[1:])]) for par in params]

        dbcon.close()

        self.useriter = parameter_model.append(None, ['User defined', None])
        for userpar in self.monitor.cfg['ccs-plot_parameters']:
            parameter_model.append(self.useriter, [userpar, None])

        return parameter_model

    def add_parameter(self, widget, listmodel):
        par_model, par_iter = self.treeview.get_selection().get_selected()

        if par_model[par_iter].parent is None:
            return

        param = par_model[par_iter]

        if param[1] is None:
            return

        listmodel.append([*param])

    def remove_parameter(self, widget, listview):
        model, modeliter = listview.get_selection().get_selected()

        if modeliter is None:
            return

        model.remove(modeliter)

    def check_label(self, widget):
        if widget.get_active_text():
            self.ok_button.set_sensitive(True)
        else:
            self.ok_button.set_sensitive(False)

    def load_set(self, widget):
        entry = self.label.get_active_text()
        if entry in self.monitor.cfg['ccs-monitor_parameter_sets'].keys():
            for slot in self.slots:
                slot[3].clear()

            param_set = json.loads(self.monitor.cfg['ccs-monitor_parameter_sets'][entry])

            dbcon = self.session_factory_idb
            i = -1
            for slots in param_set:
                i += 1
                pnames = {eval(par)[0]: par for par in slots}
                if len(pnames) > 1:
                    dbres = dbcon.execute('SELECT pcf.pcf_descr, pcf.pcf_name FROM pcf where pcf.pcf_name in {}'.format(tuple(pnames)))
                    params = dbres.fetchall()

                elif len(pnames) == 1:
                    dbres = dbcon.execute('SELECT pcf.pcf_descr, pcf.pcf_name FROM pcf where pcf.pcf_name="{}"'.format(pnames[0]))
                    params = dbres.fetchall()
                else:
                    continue

                for par in params:
                    self.slots[i][3].append([par[0], pnames[par[1]]])
            dbcon.close()

        else:
            self.logger.info('Given Set name could not be found in config File')


if __name__ == "__main__":
    given_cfg = None
    for i in sys.argv:
        if i.endswith('.cfg'):
            given_cfg = i
    if given_cfg:
        cfg = confignator.get_config(file_path=given_cfg)
    else:
        cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))

    win = ParameterMonitor()

    # Important to tell Dbus that Gtk loop can be used before the first dbus command
    DBusGMainLoop(set_as_default=True)
    Bus_Name = cfg.get('ccs-dbus_names', 'monitor')
    DBus_Basic.MessageListener(win, Bus_Name, *sys.argv)

    for arg in sys.argv:
        if arg.startswith('-'):
            sys.argv.remove(arg)

    if len(sys.argv) == 2:
        win.pool_name = sys.argv[1]
        win.set_pool(sys.argv[1])

    elif len(sys.argv) == 3:
        win.pool_name = sys.argv[1]
        win.parameter_set = sys.argv[2]
        win.set_parameter_view(sys.argv[2])
        win.set_pool(sys.argv[1])
    else:
        win.check_for_pools()

    win.connect("delete-event", win.quit_func)
    win.show_all()
    Gtk.main()
