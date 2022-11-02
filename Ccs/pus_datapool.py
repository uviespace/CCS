import io
import sys
import time
import os
import datetime
import socket
import crcmod
import struct
import DBus_Basic
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import confignator
import gi

gi.require_version('Gdk', '3.0')
gi.require_version('Notify', '0.7')
gi.require_version('Gtk', '3.0')
from gi.repository import Notify, Gtk, GLib, Gdk, GdkPixbuf
from gi.repository.Gdk import RGBA

import ccs_function_lib as cfl

# from log_server import Logging
# PersonalLogging = Logging()

import threading
import json
from typing import NamedTuple
from collections import deque
from database.tm_db import DbTelemetryPool, DbTelemetry, scoped_session_maker, FEEDataTelemetry, RMapTelemetry
import importlib


cfg = confignator.get_config(check_interpolation=False)
project = 'packet_config_{}'.format(cfg.get('ccs-database', 'project'))

packet_config = importlib.import_module(project)

TMHeader, TCHeader, PHeader, TM_HEADER_LEN, TC_HEADER_LEN, P_HEADER_LEN, PEC_LEN, MAX_PKT_LEN, timepack, timecal = \
    [packet_config.TMHeader, packet_config.TCHeader, packet_config.PHeader, packet_config.TM_HEADER_LEN,
     packet_config.TC_HEADER_LEN, packet_config.P_HEADER_LEN, packet_config.PEC_LEN, packet_config.MAX_PKT_LEN,
     packet_config.timepack, packet_config.timecal]

# RMAP and FEE protocols are only supported in SMILE
if project.endswith('SMILE'):
    RMapCommandHeader, RMapReplyWriteHeader, RMapReplyReadHeader = packet_config.RMapCommandHeader, \
                                                                   packet_config.RMapReplyWriteHeader, \
                                                                   packet_config.RMapReplyReadHeader

    RMAP_COMMAND_HEADER_LEN, RMAP_REPLY_WRITE_HEADER_LEN, RMAP_REPLY_READ_HEADER_LEN, RMAP_PEC_LEN = \
        packet_config.RMAP_COMMAND_HEADER_LEN, packet_config.RMAP_REPLY_WRITE_HEADER_LEN, \
        packet_config.RMAP_REPLY_READ_HEADER_LEN, packet_config.RMAP_PEC_LEN

PLM_PKT_PREFIX_TM = packet_config.PLM_PKT_PREFIX_TM
PLM_PKT_PREFIX_TC = packet_config.PLM_PKT_PREFIX_TC
PLM_PKT_PREFIX_TC_SEND = packet_config.PLM_PKT_PREFIX_TC_SEND
PLM_PKT_SUFFIX = packet_config.PLM_PKT_SUFFIX

communication = {}
for name in cfg['ccs-dbus_names']:
    communication[name] = 0

ActivePoolInfo = NamedTuple(
    'ActivePoolInfo', [
        ('filename', str),
        ('modification_time', int),
        ('pool_name', str),
        ('live', bool)])


def get_scoped_session_factory():
    return scoped_session_maker()


class DatapoolManager:
    # pecmodes = ['ignore', 'warn', 'discard']

    # defaults
    pecmode = 'warn'

    # crcfunc = packet_config.puscrc
    # crcfunc_rmap = packet_config.rmapcrc

    pckt_size_max = MAX_PKT_LEN
    RMAP_MAX_PKT_LEN = packet_config.RMAP_MAX_PKT_LEN
    pc = packet_config

    # SpW variables
    TLA = packet_config.SPW_DPU_LOGICAL_ADDRESS  # SpW logical address of the DPU
    PROTOCOL_IDS = {packet_config.SPW_PROTOCOL_IDS[key]: key for key in packet_config.SPW_PROTOCOL_IDS}
    # MAX_PKT_LEN = packet_config.RMAP_MAX_PKT_LEN

    tmtc = {0: 'TM', 1: 'TC'}
    tsync_flag = {0: 'U', 1: 'S', 5: 'S'}

    lock = threading.Lock()
    own_gui = None
    gui_running = False
    main_instance = None
    windowname = ' .Pool Manager'

    def __init__(self, given_cfg=None, cfilters='default', max_colour_rows=8000):

        # initiate SpWDatapoolManager methods
        # super(DatapoolManager, self).__init__()

        Notify.init('poolmgr')

        self.cfg = confignator.get_config()

        self.commit_interval = float(self.cfg['ccs-database']['commit_interval'])

        # Set up the logger
        self.logger = cfl.start_logging('PoolManager')

        # SQL Session handlers
        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        self.storage = {'PUS': DbTelemetry,
                        'FEE': FEEDataTelemetry,
                        'RMAP': RMapTelemetry}

        self.connections = {}
        self.tc_connections = {}

        self.loaded_pools = {}
        self.pool_rows = {}  # entries in MySQL "tm_pool" table
        self.databuflen = 0
        self.tc_databuflen = 0
        self.trashbytes = {None: 0}
        self.state = {}
        self.filtered_pckts = {}
        self.my_bus_name = None
        self.tc_sock = None
        self.tc_name = 'pool_name'

        self.colour_filters = {}
        self.colour_list = deque(maxlen=max_colour_rows)
        if self.cfg.has_section('ccs-pool_colour_filters') and (cfilters is not None):
            for cfilter in json.loads(self.cfg['ccs-pool_colour_filters'][cfilters]):
                seq = len(self.colour_filters.keys())
                rgba = RGBA()
                rgba.parse(cfilter['colour'])
                cfilter['colour'] = rgba
                self.colour_filters.update({seq: cfilter})

    def checking(self, argument, arg = True, some=10):
        return

    def get_connections(self):
        self.logger.info('get_connections: {}'.format(self.connections))

    def new_db_query(self, pool_name):
        new_session = self.session_factory_storage
        rows = new_session.query(
            DbTelemetry
        ).join(
            DbTelemetryPool,
            DbTelemetry.pool_id == DbTelemetryPool.iid
        ).filter(
            DbTelemetryPool.pool_name == self.loaded_pools[pool_name].filename)
        return rows

    def recover_from_db(self, pool_name=None, iid=None, dump=False):
        """
        Recover TMTC packets not stored on disk from DB
        @param pool_name:
        @param iid:
        @param dump:
        @return:
        """
        new_session = self.session_factory_storage
        if pool_name:
            rows = new_session.query(
                DbTelemetry).join(
                DbTelemetryPool, DbTelemetry.pool_id == DbTelemetryPool.iid).filter(
                DbTelemetryPool.pool_name == pool_name)
        elif iid:
            rows = new_session.query(
                DbTelemetry).join(
                DbTelemetryPool, DbTelemetry.pool_id == DbTelemetryPool.iid).filter(
                DbTelemetryPool.iid == iid)
        else:
            self.logger.error('Must give pool_name or iid')
            return None

        if dump:
            with open(dump, 'wb') as fdesc:
                fdesc.write(b''.join([row.raw for row in rows]))
        new_session.close()
        return rows

    # This function is used to fill loaded pools dictionay with a Named Tuple since it can not be passed as a NamedTuple
    # Via DBus but only as a structure
    def loaded_pools_func(self, key, pool_info):
        value = ActivePoolInfo(str(pool_info[0]), int(pool_info[1]), str(pool_info[2]),
                               bool(pool_info[3]))
        self.loaded_pools[key] = value
        return

    # This function is used to export the loaded pool dictionary via D-Bus, This is done that if it is empty dbus gets
    # into problems and prints an error message. This is prevented here
    def loaded_pools_export_func(self):
        active_pool = list(self.loaded_pools.values())
        if active_pool:
            return active_pool
        else:
            return False

    def clear_from_db(self, pool_name, answer=''):
        """
        Remove pool pool_name from DB
        @param pool_name:
        @param answer:
        @return:
        """
        # answer = ''
        while answer.lower() not in ['yes', 'no']:
            answer = input("Clear pool\n >{}<\nfrom DB? (yes/no)\n".format(pool_name))
        if answer.lower() == 'yes':
            new_session = self.session_factory_storage
            indb = new_session.execute('select * from tm_pool where pool_name="{}"'.format(pool_name))
            if len(indb.fetchall()) == 0:
                self.logger.error('POOL\n >{}<\nNOT IN DB!'.format(pool_name))
                return
            new_session.execute(
                'delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid where tm_pool.pool_name="{}"'.format(
                    pool_name))
            new_session.execute('delete tm_pool from tm_pool where tm_pool.pool_name="{}"'.format(pool_name))
            # new_session.flush()
            new_session.commit()
            new_session.close()
            self.lo('DELETED POOL\n >{}<\nFROM DB'.format(pool_name))
        return

    def _clear_db(self):
        """
        Delete all pools from DB
        @return:
        """
        answer = ''
        while answer.lower() not in ['yes', 'no']:
            answer = input(" > > > Clear all TMTC data from DB? < < < (yes/no)\n".upper())
        if answer.lower() == 'yes':
            new_session = self.session_factory_storage
            new_session.execute('delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid')
            new_session.execute('delete tm_pool from tm_pool')
            # new_session.flush()
            new_session.commit()
            new_session.close()
            self.logger.info('>>> DELETED ALL POOLS FROM DB <<<')
        return

    def _purge_db_logs(self, date=None):
        """
        Purge binary MySQL logs before _date_
        @param date: ISO formatted date string; defaults to now, if None
        """
        if date is None:
            now = datetime.datetime.now()
            date = datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')
        new_session = self.session_factory_storage
        new_session.execute('PURGE BINARY LOGS BEFORE "{:s}"'.format(date))
        new_session.close()

    def delete_abandoned_rows(self, timestamp=None):
        new_session = self.session_factory_storage
        try:
            if timestamp is None:
                new_session.execute(
                    'DELETE tm FROM tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
                new_session.execute(
                    'DELETE rmap_tm FROM rmap_tm INNER JOIN tm_pool ON rmap_tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
                new_session.execute(
                    'DELETE feedata_tm FROM feedata_tm INNER JOIN tm_pool ON feedata_tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
                new_session.execute('DELETE tm_pool FROM tm_pool WHERE tm_pool.pool_name LIKE "---TO-BE-DELETED%"')
            else:
                new_session.execute(
                    'DELETE tm FROM tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE \
                    tm_pool.pool_name="---TO-BE-DELETED{}"'.format(timestamp))
                new_session.execute('DELETE tm_pool FROM tm_pool WHERE tm_pool.pool_name="---TO-BE-DELETED{}"'.format(
                    timestamp))

            new_session.commit()
        except Exception as err:
            self.logger.error("Error trying to delete old DB rows: {}".format(err))
            new_session.rollback()
        finally:
            new_session.close()

    def _clear_pool(self, pool_name):

        if pool_name not in self.connections:
            self.logger.warning('Cannot clear static pool "{}".'.format(pool_name))
            return

        new_session = self.session_factory_storage
        if self.connections[pool_name]['socket'].fileno() < 0:  # if true, socket is closed, just "delete" pool
            n_del_pools, = new_session.execute(
                'SELECT COUNT(*) FROM tm_pool WHERE pool_name LIKE "---TO-BE-DELETED%"').fetchall()[0]
            new_session.execute(
                'UPDATE tm_pool SET pool_name="---TO-BE-DELETED-{:03d}---" WHERE tm_pool.pool_name="{}"'.format(
                    n_del_pools, pool_name))
            new_session.commit()
            new_session.close()
            self.logger.info('Content of pool "{}" deleted!'.format(pool_name))
            return

        self.connections[pool_name]['paused'] = True
        while self.connections[pool_name]['recv-thread'].is_alive():
            time.sleep(0.1)
        sockfd = self.connections[pool_name]['socket']
        protocol = self.connections[pool_name]['protocol']

        if protocol == 'SPW':
            self.spw_recv_start(sockfd, pool_name, try_delete=False, force_clean=True)
        elif protocol in ['PUS', 'PLMSIM']:
            self.tm_recv_start(sockfd, pool_name, protocol=protocol, try_delete=False, force_clean=True)
        else:
            self.logger.warning('"{}" is not a supported protocol, aborting.'.format(protocol))
            return

        # self.tm_recv_start(sockfd, pool_name, try_delete=False)

        self.logger.info('Content of pool "{}" deleted!'.format(pool_name))

        while True:
            dbrow = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()
            if dbrow is None:
                new_session.close()
                time.sleep(0.1)
                continue
            else:
                timestamp = dbrow.modification_time
                new_session.close()
                break

        self.loaded_pools[pool_name] = ActivePoolInfo(pool_name, timestamp, pool_name, True)
        self.logger.info('Resuming recording from {}:{}'.format(*sockfd.getpeername()))

    def connect(self, pool_name, host, port, protocol='PUS', is_server=False, timeout=10, delete_abandoned=False,
                try_delete=True, pckt_filter=None, options='', drop_rx=False, drop_tx=False, return_socket=False,
                override_with_options=False):

        # override variables that are set in the options string
        if bool(override_with_options):
            self.logger.debug('Overriding kwargs with values from options string.')
            override = eval(options)
            protocol = override.get('protocol', protocol)
            is_server = override.get('is_server', is_server)
            timeout = override.get('timeout', timeout)
            delete_abandoned = override.get('delete_abandoned', delete_abandoned)
            try_delete = override.get('try_delete', try_delete)
            pckt_filter = override.get('pckt_filter', pckt_filter)
            drop_rx = override.get('drop_rx', drop_rx)
            drop_tx = override.get('drop_tx', drop_tx)
            return_socket = override.get('return_socket', return_socket)
            # options = override.get('options', options)

        protocol = protocol.upper()

        # check if recording connection with pool_name already exists and return if it does
        if pool_name in self.connections:
            self.logger.info(self.connections[pool_name])
            if self.connections[pool_name]['recording']:
                self.logger.warning('Pool "{}" already exists and is recording!'.format(pool_name))
                return

        # To allow multiple access (the UI is reading from the table!)
        # we need a new DB session anyway.
        self.tm_name = pool_name
        if is_server:
            socketserver = socket.socket()
            socketserver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            socketserver.settimeout(timeout)
            socketserver.bind((host, port))
            socketserver.listen()
            try:
                sockfd, addr = socketserver.accept()
            except socket.timeout:
                socketserver.close()
                self.logger.error("Connection timeout, no client has connected to {}:{}".format(host, port))
                return
            self.tc_connections[pool_name] = {'socket': sockfd, 'protocol': protocol}
        else:
            sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockfd.settimeout(timeout)
            try:
                sockfd.connect((host, port))
            except ConnectionRefusedError:
                self.logger.error("Connection to {}:{} refused".format(host, port))
                return
        self.connections[pool_name] = {'socket': sockfd, 'recording': True, 'protocol': protocol}

        # choose transmission protocol
        if protocol == 'SPW':
            self.spw_recv_start(sockfd, pool_name, delete_abandoned=delete_abandoned, try_delete=try_delete,
                                drop_rx=drop_rx)
        elif protocol in ['PUS', 'PLMSIM']:
            self.tm_recv_start(sockfd, pool_name, protocol=protocol, delete_abandoned=delete_abandoned, try_delete=try_delete,
                               pckt_filter=pckt_filter, drop_rx=drop_rx, drop_tx=drop_tx)
        else:
            self.logger.warning('"{}" is not a supported protocol, aborting.'.format(protocol))
            return

        self.logger.info('Recording from new connection {}:{} to pool "{}" using {} protocol.'.format(host, port, protocol, pool_name))
        new_session = self.session_factory_storage
        while True:
            dbrow = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()
            if dbrow is None:
                new_session.close()
                time.sleep(0.1)
                continue
            else:
                timestamp = dbrow.modification_time
                new_session.close()
                break

        self.loaded_pools[pool_name] = ActivePoolInfo(pool_name, timestamp, pool_name, True)

        # Update the Gui if it exists
        if self.own_gui and sockfd is not None:
            # self.own_gui.statusbar.push(0, 'Connected to {}:{}'.format(host, port))
            self.own_gui.model_in.append(
                ['{} [{}:{}] | {} | {}'.format(pool_name, host, port, 'TM', options), (timestamp, sockfd)])
        if return_socket is True:
            return timestamp, sockfd
        else:
            return timestamp

    # Function will only disconnect TM connections with given name, or all TM connections if no name is given
    def disconnect_tm(self, pool_name=None):
        if pool_name is None:
            for tm in self.connections:
                self.connections[tm]['recording'] = False
                # if pool_name in self.tc_connections:
                #    del self.tc_connections[pool_name]
        else:
            self.connections[pool_name]['recording'] = False

        if not pool_name in self.tc_connections:
            self.loaded_pools[pool_name] = ActivePoolInfo(pool_name, self.loaded_pools[pool_name].modification_time,
                                                          pool_name, False)

        if self.own_gui:
            self.own_gui.disconnect_incoming_via_code(param=[pool_name, None, 'TM'])  # Updates the gui

        # Tell the Poolviewer to stop updating
        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            cfl.Functions(pv, 'stop_recording_info', str(pool_name))

        return

    def connect_tc(self, pool_name, host, port, protocol='PUS', drop_rx=True, timeout=10, is_server=False, options='',
                   override_with_options=False, use_socket=None):

        # override variables that are set in the options string
        if bool(override_with_options):
            self.logger.debug('Overriding kwargs with values from options string.')
            override = eval(options)
            protocol = override.get('protocol', protocol)
            drop_rx = override.get('drop_rx', drop_rx)
            timeout = override.get('timeout', timeout)
            is_server = override.get('is_server', is_server)
            use_socket = override.get('use_socket', use_socket)
            # options = override.get('options', options)

        if use_socket is not None:
            if isinstance(use_socket, socket.socket):
                sockfd = use_socket
            elif isinstance(use_socket, str):
                try:
                    sockfd = self.connections[use_socket]['socket']
                except KeyError:
                    self.logger.error('No existing socket found for "{}"'.format(use_socket))
                    raise KeyError('No existing socket found for "{}"'.format(use_socket))
            else:
                self.logger.error('use_socket must be of type str or socket')
                raise TypeError('use_socket must be of type str or socket')
        else:
            if is_server:
                socketserver = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                socketserver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                socketserver.settimeout(timeout)
                socketserver.bind((host, port))
                socketserver.listen()
                try:
                    sockfd, addr = socketserver.accept()
                except socket.timeout:
                    socketserver.close()
                    self.logger.error("Connection timeout, no client has connected to {}:{}".format(host, port))
                    return
            else:
                sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sockfd.settimeout(timeout)

                if pool_name in self.tc_connections:
                    self.logger.warning('Pool "{}" already has TC connection to {}!'.format(pool_name, self.tc_connections[pool_name]['socket'].getpeername()))
                    return
                try:
                    sockfd.connect((host, port))
                except ConnectionRefusedError:
                    self.logger.error("Connection to {}:{} refused".format(host, port))
                    return

        self.tc_sock = sockfd
        self.tc_name = pool_name
        self.tc_connections[pool_name] = {'socket': sockfd, 'protocol': protocol}

        self.logger.info('Established TC connection to {}, using {} protocol.'.format(sockfd.getpeername(), protocol))

        if pool_name not in self.loaded_pools:
            self.loaded_pools[pool_name] = ActivePoolInfo(pool_name, 0, pool_name, True)

            # If this is a new connection and the pool already exists in the database delete all entries
            new_session = self.session_factory_storage
            pool_row = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()
            if pool_row:
                new_session.execute(
                    'DELETE tm FROM tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE tm_pool.pool_name="{}"'.format(
                        pool_name))
                new_session.commit()

        # read data received on TC socket to prevent buffer overflow
        if drop_rx:
            tc_recv = threading.Thread(target=self.tc_receiver, kwargs={'sockfd': sockfd, 'protocol': protocol})
            # tc_recv.setDaemon(True)
            tc_recv.daemon = True
            tc_recv.name = 'TC-drop_rx-{}'.format(pool_name)
            tc_recv.start()

        if self.own_gui and self.tc_name is not None:
            # self.own_gui.statusbar.push(0, 'Connected to {}:{}'.format(host, port))
            self.own_gui.model_in.append(
                ['{} [{}:{}] | {} | {}'.format(pool_name, host, port, 'TC', options), self.tc_name])

        return self.tc_name

    # Function will only disconnect TC connections with given name, or all TC connections if no name is given
    def disconnect_tc(self, pool_name=None):
        if pool_name is None:
            for tc in self.tc_connections:
                self.tc_connections[tc]['socket'].close()
                del self.tc_connections[tc]
        else:
            self.tc_connections[pool_name]['socket'].close()
            del self.tc_connections[pool_name]

        # If it was only a TC live connection change it to not live
        if not pool_name in self.connections:
            self.loaded_pools[pool_name] = ActivePoolInfo('pool_name', self.loaded_pools[pool_name].modification_time,
                                                          'pool_name', False)

        self.tc_sock = None
        if self.own_gui:
            self.own_gui.disconnect_incoming_via_code(param=[pool_name, None, 'TC'])  # Updates the gui

        #Tell the Poolviewer to stop updating
        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            cfl.Functions(pv, 'stop_recording_info', str(pool_name))

        return

    def _is_tc_connection_active(self, pool_name):
        """
        Utility function to check whether a pool has an active TC connection to report back via DBus
        """
        if pool_name in self.tc_connections and not self.tc_connections[pool_name]['socket'].fileno() < 0:
            return True
        else:
            return False

    # Function will disconnect both TC/TM connection if they have the same name
    def disconnect(self, pool_name):

        if pool_name in self.loaded_pools:
            self.loaded_pools[pool_name] = ActivePoolInfo(pool_name, self.loaded_pools[pool_name].modification_time,
                                                          pool_name, False)

        if pool_name in self.connections:
            self.connections[pool_name]['recording'] = False
        if pool_name in self.tc_connections:
            self.tc_connections[pool_name]['socket'].close()
            del self.tc_connections[pool_name]

        if self.own_gui:
            self.own_gui.disconnect_incoming_via_code(param=[pool_name, None, None])  # Updates the gui

        # Tell the Poolviewer to stop updating
        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            cfl.Functions(pv, 'stop_recording_info', str(pool_name))
        return

    # Is used from the GUI to tell the Poolmanager which connections have been disconnected
    def disconnect_gui(self, pool_name=None, tmtc=None):
        if tmtc == 'TM':
            self.connections[pool_name]['recording'] = False
        elif tmtc == 'TC':
            self.tc_connections[pool_name]['socket'].close()
            del self.tc_connections[pool_name]
        else:
            if pool_name in self.connections:
                self.connections[pool_name]['recording'] = False
            if pool_name in self.tc_connections:
                self.tc_connections[pool_name]['socket'].close()
                del self.tc_connections[pool_name]

        # Tell the Poolviewer to stop updating
        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            cfl.Functions(pv, 'stop_recording_info', str(pool_name))

        return

    def get_time(self):
        return datetime.datetime.utcnow().strftime("%Y-%m-%d %T UTC: ")

    def tm_recv_start(self, sockfd, pool_name, protocol='PUS', drop_rx=False, drop_tx=False,
                      delete_abandoned=False, try_delete=True, pckt_filter=None, force_clean=False):

        if pool_name in self.loaded_pools and self.loaded_pools[pool_name].live and not force_clean and pool_name in self.state:
            self.logger.info('Pool "{}" is live. Skipping deletion of previous data.')
            start_new = False
        else:
            self.tm_receiver_del_old_pool(pool_name, delete_abandoned=delete_abandoned, try_delete=try_delete)
            start_new = True

        self.connections[pool_name]['paused'] = False

        thread = threading.Thread(target=self.tm_recv_worker,
                                  kwargs={
                                      'sockfd': sockfd,
                                      'pool_name': pool_name,
                                      'protocol': protocol,
                                      'drop_rx': drop_rx,
                                      'drop_tx': drop_tx,
                                      'pckt_filter': pckt_filter,
                                      'start_new': start_new})

        thread.daemon = True
        thread.name = '{}-tm_recv_worker'.format(pool_name)
        # thread.stopRecording = False
        # self.recordingThread = thread
        self.connections[pool_name]['recv-thread'] = thread
        thread.start()
        return thread

    def tm_recv_worker(self, sockfd, pool_name, protocol='PUS', drop_rx=False, drop_tx=False, pckt_filter=None, start_new=True):
        host, port = sockfd.getpeername()

        # Check if a Pool has already been started with only TC
        # start_new = True
        # if pool_name in self.loaded_pools:
        #     if self.loaded_pools[pool_name].live:
        #         start_new = False
        # if not pool_name in self.state:
        #     start_new = True

        new_session = self.session_factory_storage

        # If no TC Pool has been started start new one
        if start_new:
            pool_row = DbTelemetryPool(
                pool_name=pool_name,
                modification_time=time.time(),
                protocol=protocol)
            new_session.add(pool_row)
            # new_session.flush()
            new_session.commit()
            self.trashbytes[pool_name] = 0
            self.state[pool_name] = 1
            self.last_commit_time = time.time()

        else:
            pool_row = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()

        if pckt_filter is not None:
            self.filtered_pckts[pool_name] = deque()

        def process_tm(tmd, tm_raw):
            tm = tmd[0]

            # truncate if data exceeds max packet length
            if len(tm_raw) > MAX_PKT_LEN:
                self.logger.warning("Packet [{},{}] exceeds MAX_PKT_LEN of {} ({}). Truncating data!".format(
                    tm.APID, tm.PKT_SEQ_CNT, MAX_PKT_LEN, len(tm_raw)))
                tm_raw = tm_raw[:MAX_PKT_LEN]
                tmd = list(tmd)
                tmd[1] = tmd[1][:MAX_PKT_LEN]

            newTmRow = DbTelemetry(
                pool_id=pool_row.iid,
                idx=self.state[pool_row.pool_name],
                is_tm=tm.PKT_TYPE,
                apid=tm.APID,
                seq=tm.PKT_SEQ_CNT,
                len_7=tm.PKT_LEN,
                stc=tm.SERV_TYPE,
                sst=tm.SERV_SUB_TYPE,
                destID=tm.DEST_ID if tm.PKT_TYPE == 0 else tm.SOURCE_ID,
                timestamp=self.cuc_time_str(tm),
                data=tmd[1],
                raw=tm_raw)
            self._add_to_colour_list({'TM/TC': self.tmtc[tm.PKT_TYPE], 'ST': tm.SERV_TYPE, 'SST': tm.SERV_SUB_TYPE,
                                      'APID': tm.APID, 'LEN': tm.PKT_LEN})
            new_session.add(newTmRow)
            self.state[pool_row.pool_name] += 1
            now = time.time()
            if (now - self.last_commit_time) > self.commit_interval:
                # new_session.bulk_save_objects(self.rows_to_add)
                new_session.commit()
                self.last_commit_time = now

        # set short timeout to commit last packet, in case no further one is received
        sockfd.settimeout(1.)

        pkt_size_stream = b''
        while self.connections[pool_name]['recording']:
            if sockfd.fileno() < 0:
                break
            try:
                if self.connections[pool_name]['paused']:
                    new_session.commit()
                    new_session.close()
                    self.logger.info('Paused recording from ' + str(host) + ':' + str(port))
                    return

                # Handle protocol used by HVS SXI PLM
                if protocol.upper() == "PLMSIM":
                    msg = sockfd.recv(4096).decode()
                    while not msg.endswith('\r\n'):
                        msg += sockfd.recv(4096).decode()
                    pkts = msg.split('\r\n')
                    pkts.remove('')
                    buf = b''
                    for pkt in pkts:
                        try:
                            if pkt.startswith(PLM_PKT_PREFIX_TM.decode()):
                                tm = bytes.fromhex(pkt.split(' ')[-3])
                            elif drop_tx is False and pkt.startswith(PLM_PKT_PREFIX_TC.decode()):
                                tm = bytes.fromhex(pkt.split(' ')[-3])
                            else:
                                self.logger.warning("Not a PUS packet: " + pkt)
                                continue
                            if self.crc_check(tm):
                                self.logger.warning("Invalid CRC: " + pkt)
                                self.trashbytes[pool_name] += len(tm)
                                continue
                            buf += tm
                        except Exception as err:
                            self.logger.warning('Error trying to interpret "{}" as byte string. {}'.format(pkt, err))

                    if not buf:
                        continue

                # pure PUS datastream
                elif protocol.upper() == "PUS":
                    while len(pkt_size_stream) < 6:
                        data = sockfd.recv(6 - len(pkt_size_stream))
                        if not data:
                            break
                        pkt_size_stream += data
                    pkt_len = struct.unpack('>4xH', pkt_size_stream[:6])[0] + 7  # PUS len+7
                    while pkt_len > MAX_PKT_LEN:
                        pkt_size_stream = pkt_size_stream[1:]
                        self.trashbytes[pool_name] += 1
                        if len(pkt_size_stream) < 6:
                            pkt_size_stream += sockfd.recv(1)
                        pkt_len = struct.unpack('>4xH', pkt_size_stream[:6])[0] + 7
                    if len(pkt_size_stream) < pkt_len:
                        buf = pkt_size_stream + sockfd.recv(pkt_len - len(pkt_size_stream))
                        tail = b''
                    else:
                        buf = pkt_size_stream[:pkt_len]
                        tail = pkt_size_stream[pkt_len:]
                    while len(buf) < pkt_len:
                        d = sockfd.recv(pkt_len - len(buf))
                        if not d:
                            break
                        buf += d

                    while self.crc_check(buf):
                        buf = buf[1:] + tail
                        self.trashbytes[pool_name] += 1
                        while len(buf) < 6:
                            buf += sockfd.recv(6 - len(buf))
                        pkt_len = struct.unpack('>4xH', buf[:6])[0] + 7
                        if pkt_len > MAX_PKT_LEN:
                            tail = b''
                            continue
                        while pkt_len > len(buf):
                            buf += sockfd.recv(pkt_len - len(buf))
                        if pkt_len < len(buf):
                            tail = buf[pkt_len:]
                            buf = buf[:pkt_len]
                        else:
                            tail = b''
                    pkt_size_stream = tail

                # buf = sockfd.recv(self.pckt_size_max)
                if not buf:
                    break
                with self.lock:
                    self.databuflen += len(buf)
                if not drop_rx:
                    if pckt_filter:
                        for pkt in self.extract_pus(buf):
                            tm = self.unpack_pus(pkt)
                            if tm[0].SERV_TYPE in pckt_filter:
                                self.filtered_pckts[pool_name].append(buf)
                            else:
                                self.decode_tmdump_and_process_packets_internal(pkt, process_tm, pckt_decoded=tm,
                                                                                checkcrc=False)
                    else:
                        self.decode_tmdump_and_process_packets_internal(buf, process_tm, checkcrc=False)
            except socket.timeout as e:
                self.logger.info('Socket timeout ({}:{})'.format(host, port))
                new_session.commit()
                continue
            except socket.error as e:
                self.logger.error('Socket error ({}:{})'.format(host, port))
                self.logger.exception(e)
                # self.logger.error('ERROR: socket error')
                self.connections[pool_name]['recording'] = False
                break
            except struct.error as e:
                self.logger.error('Lost connection to {}:{}'.format(host, port))
                self.logger.exception(e)
                self.connections[pool_name]['recording'] = False
                break
        # if self.state[pool_row.pool_name] % 10 != 0:
        new_session.commit()
        new_session.close()
        self.logger.warning('Disconnected from ' + str(host) + ':' + str(port))
        sockfd.close()

    def tm_receiver_del_old_pool(self, pool_name, delete_abandoned=False, try_delete=True, force=False):
        new_session = self.session_factory_storage
        pool_row = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()
        if pool_row:

            rows_in_pool = new_session.query(DbTelemetry).join(
                DbTelemetryPool, DbTelemetryPool.iid == DbTelemetry.pool_id).filter(
                DbTelemetryPool.pool_name == pool_name).count()

            # If pool has 0 Rows do the delete
            if rows_in_pool == 0:
                if pool_name in self.state:
                    del self.state[pool_name]

            # If the pool is started by TC do not delete  //MM: this is taken care of outside this function
            # elif pool_name in self.loaded_pools:
            #     if self.loaded_pools[pool_name].live:
            #         return

            if rows_in_pool < 1000 and try_delete:
                new_session.execute(
                    'DELETE tm FROM tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE tm_pool.pool_name="{}"'.format(
                        pool_name))
                # SQlite compatible alternative?:
                # 'DELETE FROM tm where iid in (SELECT iid from tm INNER JOIN tm_pool ON tm.pool_id=tm_pool.iid WHERE tm_pool.pool_name="{}")'
                new_session.execute('DELETE tm_pool FROM tm_pool WHERE tm_pool.pool_name="{}"'.format(pool_name))
                new_session.commit()
            else:
                n_del_pools, = new_session.execute(
                    'SELECT COUNT(*) FROM tm_pool WHERE pool_name LIKE "---TO-BE-DELETED%"').fetchall()[0]
                new_session.execute(
                    'UPDATE tm_pool SET pool_name="---TO-BE-DELETED-{:03d}---" WHERE tm_pool.pool_name="{}"'.format(
                        n_del_pools, pool_name))
                new_session.commit()
                if delete_abandoned:
                    delete_thread = threading.Thread(target=self.delete_abandoned_rows, name='DELETE_ABANDONED')
                    delete_thread.start()

        new_session.close()

    def receive_from_socket(self, sockfd, pool_name=None, pkt_size_stream=b''):
        while len(pkt_size_stream) < 6:
            data = sockfd.recv(6 - len(pkt_size_stream))
            if not data:
                break
            pkt_size_stream += data
        pkt_len = struct.unpack('>4xH', pkt_size_stream[:6])[0] + 7  # PUS len+7
        while pkt_len > MAX_PKT_LEN:
            pkt_size_stream = pkt_size_stream[1:]
            if pool_name is not None:
                self.trashbytes[pool_name] += 1
            if len(pkt_size_stream) < 6:
                pkt_size_stream += sockfd.recv(1)
            pkt_len = struct.unpack('>4xH', pkt_size_stream[:6])[0] + 7
        if len(pkt_size_stream) < pkt_len:
            buf = pkt_size_stream + sockfd.recv(pkt_len - len(pkt_size_stream))
            tail = b''
        else:
            buf = pkt_size_stream[:pkt_len]
            tail = pkt_size_stream[pkt_len:]
        while len(buf) < pkt_len:
            d = sockfd.recv(pkt_len - len(buf))
            if not d:
                break
            buf += d

        while self.crc_check(buf):
            buf = buf[1:] + tail
            if pool_name is not None:
                self.trashbytes[pool_name] += 1
            while len(buf) < 6:
                buf += sockfd.recv(6 - len(buf))
            pkt_len = struct.unpack('>4xH', buf[:6])[0] + 7
            if pkt_len > MAX_PKT_LEN:
                tail = b''
                continue
            while pkt_len > len(buf):
                buf += sockfd.recv(pkt_len - len(buf))
            if pkt_len < len(buf):
                tail = buf[pkt_len:]
                buf = buf[:pkt_len]
            else:
                tail = b''
        return buf, tail

    def tc_receiver(self, sockfd, protocol='PUS'):
        host, port = sockfd.getpeername()

        while True:
            if sockfd.fileno() < 0:
                break
            try:
                # Handle ACKs sent by HVS SXI PLM
                if protocol.lower() == "plmsim":
                    ack = sockfd.recv(1024)
                    if not ack:
                        break
                    while not ack.endswith(b'> '):
                        ack += sockfd.recv(1024)
                    self.logger.info('PLMSIM: {}'.format(ack.decode()))
                    buf = ack

                # PUS, just read packets and discard them
                elif protocol.lower() == 'pus':
                    pkt_size_stream = sockfd.recv(6)
                    while len(pkt_size_stream) < 6:
                        data = sockfd.recv(1)
                        if not data:
                            break
                        pkt_size_stream += data
                    tmp_pkt_size = len(pkt_size_stream)
                    pkt_len = struct.unpack('>4xH', pkt_size_stream[:6])[0] + 7  # PUS len+7
                    buf = pkt_size_stream + sockfd.recv(pkt_len - tmp_pkt_size)
                    while len(buf) < pkt_len:
                        d = sockfd.recv(1)
                        if not d:
                            break
                        buf += d

                # any other protocol, just read from socket and discard
                else:
                    buf = sockfd.recv(1024)

                with self.lock:
                    self.databuflen += len(buf)
            except socket.timeout:
                self.logger.info('Socket timeout {}:{} [TC RX]'.format(host, port))
                continue
            except socket.error:
                self.logger.error('Socket error')
                break
            except struct.error:
                self.logger.error('Lost connection...')
                break
        self.logger.warning('Disconnected TC RX: ' + str(host) + ':' + str(port))
        sockfd.close()

    # def set_commit_interval(self, pool_name, commit_interval):
    #     with self.lock:
    #         if commit_interval is None:
    #             self.connections[pool_name]['sqlsession'].commit()
    #         else:
    #             self.commit_interval = commit_interval
    #             self.connections[pool_name]['sqlsession'].commit()

    def tc_send(self, pool_name, buf):

        if pool_name not in self.tc_connections:
            self.logger.error('"{}" is not connected to any TC socket!'.format(pool_name))
            return

        # check protocol of TC socket to append headers and stuff, this has to happen here, not in Tcsend_DB
        if self.tc_connections[pool_name]['protocol'].upper() == 'PLMSIM':
            buf_to_send = PLM_PKT_PREFIX_TC_SEND + buf.hex().upper().encode() + PLM_PKT_SUFFIX
        else:
            buf_to_send = buf

        self.logger.debug('tc_send: pool_name = {}'.format(pool_name))
        self.logger.debug('tc_send: buf = {}'.format(buf_to_send))

        if pool_name not in self.loaded_pools:
            self.logger.warning("Cannot add TC to {}. Pool not loaded.".format(pool_name))
            return
        # self.logger.debug('tc_send: tc_connections = {}'.format(self.tc_connections))

        try:
            self.tc_connections[pool_name]['socket'].send(buf_to_send)
        except Exception as err:
            self.logger.error('Failed to send packet of length {} to {} [{}].'.format(
                len(buf_to_send), pool_name, self.tc_connections[pool_name]['socket'].getpeername()))
            return

        with self.lock:
            self.tc_databuflen += len(buf_to_send)

        new_session = self.session_factory_storage

        pool_row = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()

        # TC normally just take the information which pool it is from the first Row, But if a Pool is given with only
        # TCs there is no first row therefore get the information from the database
        if not pool_row:
            pool_row = DbTelemetryPool(
                pool_name=pool_name,
                modification_time=time.time(),
                protocol='UNKNOWN')
            new_session.add(pool_row)
            # new_session.flush()
            new_session.commit()

            self.trashbytes[pool_name] = 0
            self.state[pool_name] = 1
            self.last_commit_time = time.time()

        # If the pool name already exists but witout any entries just start from row 1 and delete all other entries
        elif not self.state[pool_name]:

            self.trashbytes[pool_name] = 0
            self.state[pool_name] = 1
            self.last_commit_time = time.time()

        def process_tm(tmd, tm_raw):
            tm = tmd[0]

            # truncate if data exceeds max packet length
            if len(tm_raw) > MAX_PKT_LEN:
                self.logger.warning("Packet [{},{}] exceeds MAX_PKT_LEN of {} ({}). Truncating data!".format(
                    tm.APID, tm.PKT_SEQ_CNT, MAX_PKT_LEN, len(tm_raw)))
                tm_raw = tm_raw[:MAX_PKT_LEN]
                tmd = list(tmd)
                tmd[1] = tmd[1][:MAX_PKT_LEN]

            newTmRow = DbTelemetry(
                pool_id=pool_row.iid,
                idx=self.state[pool_row.pool_name],
                is_tm=tm.PKT_TYPE,
                apid=tm.APID,
                seq=tm.PKT_SEQ_CNT,
                len_7=tm.PKT_LEN,
                stc=tm.SERV_TYPE,
                sst=tm.SERV_SUB_TYPE,
                destID=tm.DEST_ID if tm.PKT_TYPE == 0 else tm.SOURCE_ID,
                timestamp=self.cuc_time_str(tm),
                data=tmd[1],
                raw=tm_raw)
            new_session.add(newTmRow)
            # self.logger.debug("Recorded %d rows in %s..." % (self.state[0], pool_name))
            self.state[pool_row.pool_name] += 1
            new_session.commit()

        self.decode_tmdump_and_process_packets_internal(buf, process_tm)
        new_session.close()
        return

    def crc_check(self, pckt):
        # return bool(self.crcfunc(pckt))
        return bool(packet_config.puscrc(pckt))

    def read_pus(self, data):
        """
        Read single PUS packet from buffer

        @param data: has to be seekable
        @return: single PUS packet as byte string or _None_
        """
        pus_size = data.peek(10)

        if len(pus_size) >= 6:
            pus_size = pus_size[4:6]
        elif 0 < len(pus_size) < 6:
            start_pos = data.tell()
            pus_size = data.read(6)[4:6]
            data.seek(start_pos)
        elif len(pus_size) == 0:
            return

        # packet size is header size (6) + pus size field + 1
        pckt_size = int.from_bytes(pus_size, 'big') + 7
        return data.read(pckt_size)

    def extract_pus(self, data):
        """

        @param data:
        @return:
        """
        pckts = []
        if isinstance(data, bytes):
            data = io.BufferedReader(io.BytesIO(data))

        while True:
            pckt = self.read_pus(data)
            if pckt is not None:
                pckts.append(pckt)
            else:
                break
        return pckts

    def extract_pus_brute_search(self, data, filename=None):
        """

        @param data:
        @param filename:
        @return:
        """

        pckts = []
        if isinstance(data, bytes):
            data = io.BufferedReader(io.BytesIO(data))
        elif isinstance(data, io.BufferedReader):
            pass
        else:
            raise TypeError('Cannot handle input of type {}'.format(type(data)))

        while True:
            pos = data.tell()
            pckt = self.read_pus(data)
            if pckt is not None:
                if not self.crc_check(pckt):
                    pckts.append(pckt)
                else:
                    data.seek(pos + 1)
                    if filename is not None:
                        self.trashbytes[filename] += 1
            else:
                break

        return pckts

    # @staticmethod
    def unpack_pus(self, pckt):
        """
        Decode PUS and return header parameters and data field
        :param pckt:
        :return:
        """
        try:
            tmtc = pckt[0] >> 4 & 1
            dhead = pckt[0] >> 3 & 1

            if tmtc == 0 and dhead == 1 and (len(pckt) >= TM_HEADER_LEN):
                header = TMHeader()
                header.bin[:] = pckt[:TM_HEADER_LEN]
                data = pckt[TM_HEADER_LEN:-PEC_LEN]
                crc = pckt[-PEC_LEN:]

            elif tmtc == 1 and dhead == 1 and (len(pckt) >= TC_HEADER_LEN):
                header = TCHeader()
                header.bin[:] = pckt[:TC_HEADER_LEN]
                data = pckt[TC_HEADER_LEN:-PEC_LEN]
                crc = pckt[-PEC_LEN:]

            else:
                header = PHeader()
                header.bin[:P_HEADER_LEN] = pckt[:P_HEADER_LEN]
                data = pckt[P_HEADER_LEN:]
                crc = None

            head_pars = header.bits

        except Exception as err:
            self.logger.warning('Error unpacking PUS packet: {}\n{}'.format(pckt, err))
            head_pars = None
            data = None
            crc = None

        finally:
            return head_pars, data, crc

    def cuc_time_str(self, head):
        try:
            if head.PKT_TYPE == 0 and head.SEC_HEAD_FLAG == 1:
                return '{:.6f}{}'.format(head.CTIME + head.FTIME / timepack[2], self.tsync_flag[head.TIMESYNC])
            else:
                return ''
        except Exception as err:
            self.logger.info(err)
            return ''

    def decode_tmdump_and_process_packets(self, filename, processor, brute=False):
        buf = open(filename, 'rb').read()
        self.trashbytes[filename] = 0
        self.decode_tmdump_and_process_packets_internal(buf, processor, brute=brute, filename=filename)

    def decode_tmdump_and_process_packets_internal(self, buf, processor, brute=False, checkcrc=True, filename=None,
                                                   pckt_decoded=None):
        if pckt_decoded is not None:
            processor(pckt_decoded, buf)
            return

        decode = self.unpack_pus

        if brute:
            pckts = self.extract_pus_brute_search(buf, filename=filename)
            checkcrc = False  # CRC already performed during brute_search
        else:
            pckts = self.extract_pus(buf)

        for pckt in pckts:
            if checkcrc:
                if self.crc_check(pckt):
                    if self.pecmode == 'warn':
                        if len(pckt) > 7:
                            self.logger.info(
                                'decode_tmdump_and_process_packets_internal: [CRC error]: packet with seq nr ' + str(
                                    int(pckt[5:7].hex(), 16)) + '\n')
                        else:
                            self.logger.info('INVALID packet -- too short' + '\n')
                    elif self.pecmode == 'discard':
                        if len(pckt) > 7:
                            self.logger.info(
                                '[CRC error]: packet with seq nr ' + str(int(pckt[5:7].hex(), 16)) + ' (discarded)\n')
                        else:
                            self.logger.info('INVALID packet -- too short' + '\n')
                        continue

            pckt_decoded = decode(pckt)
            if pckt_decoded == (None, None, None):
                self.logger.warning('Could not interpret bytestream: {}. DISCARDING DATA'.format(pckt.hex()))
                continue
            elif isinstance(pckt_decoded[0]._b_base_, PHeader):
                self.logger.info('Non-PUS packet received: {}'.format(pckt))
                continue

            processor(pckt_decoded, pckt)

    def db_bulk_insert(self, filename, processor, bulk_insert_size=1000, brute=False, checkcrc=True, protocol='PUS'):
        buf = open(filename, 'rb')
        self.trashbytes[filename] = 0

        pcktcount = 0

        new_session = self.session_factory_storage
        new_session.execute('set unique_checks=0,foreign_key_checks=0')

        if protocol == 'PUS':
            buf = buf.read()
            decode = self.unpack_pus
            if brute:
                pckts = self.extract_pus_brute_search(buf, filename=filename)
                checkcrc = False  # CRC already performed during brute_search

            else:
                pckts = self.extract_pus(buf)

            pcktdicts = []
            for pckt in pckts:
                if checkcrc:
                    if self.crc_check(pckt):
                        if self.pecmode == 'warn':
                            if len(pckt) > 7:
                                self.logger.info('db_bulk_insert: [CRC error]: packet with seq nr ' + str(
                                    int(pckt[5:7].hex(), 16)) + '\n')
                            else:
                                self.logger.info('INVALID packet -- too short' + '\n')
                        elif self.pecmode == 'discard':
                            if len(pckt) > 7:
                                self.logger.info(
                                    '[CRC error]: packet with seq nr ' + str(
                                        int(pckt[5:7].hex(), 16)) + ' (discarded)\n')
                            else:
                                self.logger.info('INVALID packet -- too short' + '\n')
                            continue

                pcktdicts.append(processor(decode(pckt), pckt))
                pcktcount += 1
                if pcktcount % bulk_insert_size == 0:
                    new_session.execute(DbTelemetry.__table__.insert(), pcktdicts)
                    # new_session.bulk_insert_mappings(DbTelemetry, pcktdicts)
                    pcktdicts = []

            new_session.execute(DbTelemetry.__table__.insert(), pcktdicts)

        elif protocol == 'SPW':
            headers, pckts, remainder = self.extract_spw(buf)

            pcktdicts_rmap = []
            pcktdicts_feedata = []

            for head, pckt in zip(headers, pckts):

                if self.PROTOCOL_IDS[head.bits.PROTOCOL_ID] == 'RMAP':
                    pcktdicts_rmap.append(processor(head, pckt))
                elif self.PROTOCOL_IDS[head.bits.PROTOCOL_ID] == 'FEEDATA':
                    pcktdicts_feedata.append(processor(head, pckt))

                pcktcount += 1
                if pcktcount % bulk_insert_size == 0:
                    if len(pcktdicts_rmap) > 0:
                        new_session.execute(RMapTelemetry.__table__.insert(), pcktdicts_rmap)
                        pcktdicts_rmap = []
                    if len(pcktdicts_feedata) > 0:
                        new_session.execute(FEEDataTelemetry.__table__.insert(), pcktdicts_feedata)
                        pcktdicts_feedata = []

            if len(pcktdicts_rmap) > 0:
                new_session.execute(RMapTelemetry.__table__.insert(), pcktdicts_rmap)
            if len(pcktdicts_feedata) > 0:
                new_session.execute(FEEDataTelemetry.__table__.insert(), pcktdicts_feedata)

        new_session.execute('set unique_checks=1, foreign_key_checks=1')
        new_session.commit()
        new_session.close()

    def _add_to_colour_list(self, row):
        # d = {'TM/TC': self.tmtc[row.is_tm], 'ST': row.stc, 'SST': row.sst, 'APID': row.apid}

        for f in self.colour_filters:
            cf = self.colour_filters[f].copy()
            colour = cf.pop('colour')

            if cf.items() <= row.items():
                self.colour_list.append(((colour.red, colour.green, colour.blue), row['LEN']))
                return
            else:
                continue
        self.colour_list.append(((0., 0., 0.), row['LEN']))
        return

    def _return_colour_list(self, i):
        if i == 'try':
            if self.colour_list is None:
                return False
            else:
                return True

        if i == 'length':
            return len(self.colour_list)

        rgb, pcktlen = self.colour_list[-i - 1]
        return rgb, pcktlen

    # Load a pool for the poolviewer
    def load_pool_poolviewer(self, pool_name, filename, brute=False, force_db_import=False, pool_rows=False,
                             instance=1, protocol='PUS'):
        # pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
        brute = bool(brute)  # Just be sure about the datatypes after dbus connection
        force_db_import = bool(force_db_import)

        self.active_pool_info = ActivePoolInfo(
            filename,
            int(os.path.getmtime(filename)),
            pool_name,
            False)
        new_session = self.session_factory_storage
        # new_session = scoped_session_maker('storage')
        pool_exists_in_db_already = new_session.query(
            DbTelemetryPool
        ).filter(
            DbTelemetryPool.pool_name == self.active_pool_info.filename,
            DbTelemetryPool.modification_time == self.active_pool_info.modification_time
        ).count() > 0
        # new_session.close()
        if (not pool_exists_in_db_already) or force_db_import:
            if force_db_import:
                # new_session = self.session_factory_storage
                # new_session.execute(
                #     'delete tm from tm inner join tm_pool on tm.pool_id=tm_pool.iid where tm_pool.pool_name="{}"'.format(
                #         filename))
                # new_session.execute('delete tm_pool from tm_pool where tm_pool.pool_name="{}"'.format(filename))
                del_time = time.strftime('%s')
                new_session.execute(
                    'UPDATE tm_pool SET pool_name="---TO-BE-DELETED{}" WHERE tm_pool.pool_name="{}"'.format(
                        del_time, filename))
                # new_session.flush()
                new_session.commit()
                new_session.close()
                # delete obsolete rows
                del_thread = threading.Thread(target=self.delete_abandoned_rows, args=[del_time],
                                              name='delete_abandoned')
                del_thread.setDaemon(True)
                del_thread.start()

            self.logger.info("Data not in DB - must import...")
            # loadinfo = pv.Functions('LoadInfo')
            loadinfo = LoadInfo(parent=self)
            # loadinfo.spinner.start()
            # loadinfo.show_all()
            self._loader_thread = threading.Thread(target=self.import_dump_in_db,
                                                   args=[self.active_pool_info, loadinfo, brute, instance, protocol])
            self._loader_thread.setDaemon(True)
            self._loader_thread.start()
            # while t.isAlive():
            #     time.sleep(0.1)
            # self.import_dump_in_db(self.active_pool_info, loadinfo)
            # loadinfo.spinner.stop()
            # loadinfo.destroy()

            self.logger.info('Loaded Pool:' + str(pool_name))
            return dbus.Struct(self.active_pool_info, signature='sisb')

        else:
            new_session.close()
            if self.active_pool_info.pool_name in self.loaded_pools:
                pool_info = self.loaded_pools[self.active_pool_info.pool_name]
                with self.lock:
                    self.trashbytes[pool_info.filename] = 0
                if pool_info.filename == self.active_pool_info.filename \
                        and pool_info.modification_time == self.active_pool_info.modification_time:
                    # model = self.pool_selector.get_model()
                    # self.pool_selector.set_active([row[0] == pool_info.pool_name for row in model].index(True))
                    return

            # loadinfo = LoadInfo(parent=self)
            if pool_rows:
                # count_current_rows = pv.Functions('count_current_pool_rows',self.active_pool_info)
                self.logger.info("Data already exist in the DB (%d rows)" % pool_rows)
            # loadinfo.log.set_text("Data already exist in the DB (%d rows)" % self.count_current_pool_rows())
            # loadinfo.show_all()
            # self._set_pool_list_and_display()

            # pv.Functions('_set_pool_list_and_display', self.active_pool_info, ignore_reply=True)
            # pv.Functions('_set_pool_list_and_display', self.active_pool_info)
            # pv.Functions('Active_Pool_Info_append')
            self.loaded_pools_func(self.active_pool_info.pool_name, self.active_pool_info)

        self.logger.info('Loaded Pool:' + str(pool_name))
        return dbus.Struct(self.active_pool_info, signature='sisb')

    def timeout(self, sec):
        self.logger.debug('timeout {} sec'.format(sec))
        time.sleep(sec)
        return

    # From Poolviewer
    def import_dump_in_db(self, pool_info, loadinfo, brute=False, instance=1, protocol='PUS'):
        loadinfo.ok_button.set_sensitive(False)
        new_session = self.session_factory_storage
        new_session.query(
            DbTelemetryPool
        ).filter(
            DbTelemetryPool.pool_name == pool_info.filename
        ).delete()
        new_session.flush()
        newPoolRow = DbTelemetryPool(
            pool_name=pool_info.filename,
            modification_time=pool_info.modification_time,
            protocol=protocol)
        new_session.add(newPoolRow)
        new_session.flush()  # DB assigns auto-increment field (primary key iid) used below
        cuctime = self.cuc_time_str

        bulk_insert_size = 1000  # number of rows to transfer in one transaction
        state = [1]
        protocol_ids = self.PROTOCOL_IDS
        
        def mkdict_spw(head, tm_raw):
            pkt = head.bits

            if protocol_ids[pkt.PROTOCOL_ID] == 'RMAP':
                pcktdict = dict(pool_id=newPoolRow.iid,
                                idx=state[0],
                                cmd=pkt.PKT_TYPE,
                                write=pkt.WRITE,
                                verify=pkt.VERIFY,
                                reply=pkt.REPLY,
                                increment=pkt.INCREMENT,
                                keystat=pkt.KEY if pkt.PKT_TYPE == 1 else pkt.STATUS,
                                taid=pkt.TRANSACTION_ID,
                                addr=pkt.ADDR if pkt.PKT_TYPE == 1 else None,
                                datalen=pkt.DATA_LEN if hasattr(pkt, 'DATA_LEN') else 0,
                                raw=tm_raw)

            elif protocol_ids[pkt.PROTOCOL_ID] == 'FEEDATA':
                pcktdict = dict(pool_id=newPoolRow.iid,
                                idx=state[0],
                                pktlen=pkt.DATA_LEN,
                                type=head.comptype,
                                framecnt=pkt.FRAME_CNT,
                                seqcnt=pkt.SEQ_CNT,
                                raw=tm_raw)

            else:
                return

            state[0] += 1
            if state[0] % bulk_insert_size == 0:
                GLib.idle_add(loadinfo.log.set_text, "Loaded {:d} rows.".format(state[0], ))
            return pcktdict

        def mkdict_pus(tmd, tm_raw, truncate=True):
            tm = tmd[0]

            # truncate packets that exceed maximum allowed packet length
            # if truncate and len(tm_raw) > MAX_PKT_LEN:
            #     tmd[1] = tmd[1][:MAX_PKT_LEN]
            #     tm_raw = tm_raw[:MAX_PKT_LEN]

            pcktdict = dict(pool_id=newPoolRow.iid,
                            idx=state[0],
                            is_tm=tm.PKT_TYPE,
                            apid=tm.APID,
                            seq=tm.PKT_SEQ_CNT,
                            len_7=tm.PKT_LEN,
                            stc=tm.SERV_TYPE,
                            sst=tm.SERV_SUB_TYPE,
                            destID=tm.DEST_ID if tm.PKT_TYPE == 0 else tm.SOURCE_ID,
                            timestamp=self.cuc_time_str(tm),
                            data=tmd[1][:MAX_PKT_LEN],
                            raw=tm_raw[:MAX_PKT_LEN])

            state[0] += 1
            if state[0] % bulk_insert_size == 0:
                GLib.idle_add(loadinfo.log.set_text, "Loaded {:d} rows.".format(state[0], ))
            return pcktdict

        if protocol == 'PUS':
            mkdict = mkdict_pus
        elif protocol == 'SPW':
            mkdict = mkdict_spw
        else:
            new_session.rollback()
            new_session.close()
            self.logger.info("Protocol '{}' not supported".format(protocol))
            loadinfo.log.set_text("Protocol '{}' not supported".format(protocol))
            loadinfo.spinner.stop()
            loadinfo.ok_button.set_sensitive(True)
            return

        loadinfo.log.set_text("Parsing file...")
        self.db_bulk_insert(pool_info.filename, mkdict, bulk_insert_size=bulk_insert_size, brute=brute, protocol=protocol)

        # self.pool.decode_tmdump_and_process_packets(pool_info.filename, process_tm, brute=brute)
        pv = cfl.dbus_connection('poolviewer', instance)
        # pv.Functions('justsomefunction')
        new_session.commit()
        self.logger.info("Loaded %d rows." % (state[0] - 1))
        loadinfo.log.set_text("Loaded %d rows." % (state[0] - 1))
        loadinfo.spinner.stop()
        loadinfo.ok_button.set_sensitive(True)
        # Ignore Reply is allowed here, since the instance is passed along
        pv.Functions('_set_list_and_display_Glib_idle_add', self.active_pool_info, int(self.my_bus_name[-1]),
                     ignore_reply=True)
        self.loaded_pools_func(self.active_pool_info.pool_name, self.active_pool_info)
        # pv.Functions('_set_list_and_display_Glib_idle_add', ignore_reply=True)
        # GLib.idle_add(self._set_pool_list_and_display)
        new_session.close()

    def socket_send_packed_data(self, packdata, poolname):
        cncsocket = self.tc_connections[poolname]['socket']
        cncsocket.send(packdata)
        received = None
        try:
            received = cncsocket.recv(MAX_PKT_LEN)
            # self.logger.info.write(logtf(self.tnow()) + ' ' + recv[6:].decode() + ' [CnC]\n')
            self.logger.info(received.decode(errors='replace') + ' [CnC]')
            # logfile.flush()
            # s.close()
            # self.counters[1804] += 1
        except socket.timeout:
            self.logger.error('Got a timeout')
            self.logger.exception(socket.timeout)

        # Dbus does not like original data type
        if received is not None:
            received = dbus.ByteArray(received)

        return received

    def calc_data_rate(self, filename, refresh_rate=1):

        with self.lock:
            data_rate = self.databuflen * refresh_rate
            self.databuflen = 0
            tc_data_rate = self.tc_databuflen * refresh_rate
            self.tc_databuflen = 0
            if filename is not None:
                try:
                    trashbytes = self.trashbytes[filename]
                except KeyError:
                    trashbytes = 0
            else:
                trashbytes = 0
            return [trashbytes, tc_data_rate, data_rate]

    def spw_receiver_del_old_pool(self, pool_name, try_delete=True, delete_abandoned=True):
        new_session = self.session_factory_storage
        pool_row = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()
        if pool_row:
            rows_in_pool = new_session.query(RMapTelemetry).join(
                DbTelemetryPool, DbTelemetryPool.iid == RMapTelemetry.pool_id).filter(
                DbTelemetryPool.pool_name == pool_name).count()
            if rows_in_pool < 1000 and try_delete:
                new_session.execute(
                    'DELETE rmap_tm FROM rmap_tm INNER JOIN tm_pool ON rmap_tm.pool_id=tm_pool.iid WHERE tm_pool.pool_name="{}"'.format(
                        pool_name))
                new_session.execute(
                    'DELETE feedata_tm FROM feedata_tm INNER JOIN tm_pool ON feedata_tm.pool_id=tm_pool.iid WHERE tm_pool.pool_name="{}"'.format(
                        pool_name))
                new_session.commit()
                new_session.execute(
                    'DELETE tm_pool FROM tm_pool WHERE tm_pool.pool_name="{}"'.format(pool_name))
                new_session.commit()
            else:
                n_del_pools, = new_session.execute(
                    'SELECT COUNT(*) FROM tm_pool WHERE pool_name LIKE "---TO-BE-DELETED%"').fetchall()[0]
                new_session.execute(
                    'UPDATE tm_pool SET pool_name="---TO-BE-DELETED-{:03d}---" WHERE tm_pool.pool_name="{}"'.format(
                        n_del_pools, pool_name))
                new_session.commit()
                if delete_abandoned:
                    delete_thread = threading.Thread(target=self.delete_abandoned_rows, name='DELETE_ABANDONED')
                    delete_thread.start()
        new_session.close()

    def spw_recv_start(self, sockfd, pool_name, drop_rx=False, delete_abandoned=False, try_delete=True, force_clean=False):

        # delete existing pool rows
        self.spw_receiver_del_old_pool(pool_name, delete_abandoned=delete_abandoned, try_delete=try_delete)

        self.connections[pool_name]['paused'] = False

        thread = threading.Thread(target=self.spw_recv_worker,
                                  kwargs={
                                      'sockfd': sockfd,
                                      'pool_name': pool_name,
                                      'drop_rx': drop_rx})
        thread.daemon = True
        thread.name = '{}-spw_recv_worker'.format(pool_name)
        # thread.stopRecording = False
        # self.recordingThread = thread
        self.connections[pool_name]['recv-thread'] = thread
        thread.start()
        return thread

    def spw_recv_worker(self, sockfd, pool_name, drop_rx=False):
        host, port = sockfd.getpeername()
        new_session = self.session_factory_storage

        self.pool_rows[pool_name] = DbTelemetryPool(
            pool_name=pool_name,
            protocol='SPW',
            modification_time=time.time())
        new_session.add(self.pool_rows[pool_name])
        new_session.commit()
        self.trashbytes[pool_name] = 0
        self.state[pool_name] = 1
        self.last_commit_time = time.time()

        pkt_size_stream = b''
        while True:
            if sockfd.fileno() < 0:
                break
            try:
                if self.connections[pool_name]['paused']:
                    new_session.commit()
                    new_session.close()
                    self.logger.info('Paused recording from ' + str(host) + ':' + str(port))
                    return

                pid, header, buf, pkt_size_stream = self.read_spw_from_socket(sockfd, pkt_size_stream)

                if buf is None and pkt_size_stream is not None:
                    self.trashbytes[pool_name] += 1
                    continue

                # CRC for RMAP packets
                if self.PROTOCOL_IDS[pid] == "RMAP" and self.crc_check_rmap(buf):
                    self.trashbytes[pool_name] += 2
                    pkt_size_stream = buf + pkt_size_stream
                    continue

                with self.lock:
                    self.databuflen += len(buf)
                if not drop_rx:
                    if self.PROTOCOL_IDS[pid] == "RMAP":
                        self.process_rmap(header, buf, pool_name)
                    elif self.PROTOCOL_IDS[pid] == "FEEDATA":
                        self.process_feedata(header, buf, pool_name)

            except socket.timeout as e:
                self.logger.info('Socket timeout')
                new_session.commit()
                continue
            except socket.error as e:
                self.logger.error('Socket error: ' + str(e))
                self.logger.exception(e)
                self.connections[pool_name]['recording'] = False
                break
            except struct.error as e:
                self.logger.exception(e)
                self.logger.error('Lost connection...')
                self.connections[pool_name]['recording'] = False
                break
        self.session_factory_storage.commit()

    def read_spw_from_socket(self, sockfd, pkt_size_stream):
        while len(pkt_size_stream) < 2:
            data = sockfd.recv(2 - len(pkt_size_stream))
            if not data:
                raise socket.error
            pkt_size_stream += data
        tla, pid = pkt_size_stream[:2]

        if (tla == self.TLA) and (pid in self.PROTOCOL_IDS):
            buf = pkt_size_stream
        else:
            return pid, None, None, pkt_size_stream[1:]

        if self.PROTOCOL_IDS[pid] == "FEEDATA":
            header = self.pc.FeeDataTransferHeader()
        elif self.PROTOCOL_IDS[pid] == "RMAP":
            while len(buf) < 3:
                instruction = sockfd.recv(1)
                if not instruction:
                    raise socket.error
                buf += instruction

            instruction = buf[2]

            if (instruction >> 6) & 1:
                header = self.pc.RMapCommandHeader()
            elif (instruction >> 5) & 0b11 == 0b01:
                header = self.pc.RMapReplyWriteHeader()
            elif (instruction >> 5) & 0b11 == 0b00:
                header = self.pc.RMapReplyReadHeader()

        hsize = type(header).bits.size

        while len(buf) < hsize:
            buf += sockfd.recv(hsize - len(buf))

        header.bin[:] = buf[:hsize]

        if self.PROTOCOL_IDS[pid] == "FEEDATA":
            pktsize = header.bits.DATA_LEN
        elif (header.bits.PKT_TYPE == 1 and header.bits.WRITE == 0) or (
                header.bits.PKT_TYPE == 0 and header.bits.WRITE == 1):
            pktsize = hsize
        else:
            pktsize = hsize + header.bits.DATA_LEN + RMAP_PEC_LEN

        while len(buf) < pktsize:
            d = sockfd.recv(pktsize - len(buf))
            if not d:
                raise socket.error
            buf += d

        buf = buf[:pktsize]
        pkt_size_stream = buf[pktsize:]

        return pid, header, buf, pkt_size_stream

    def process_rmap(self, header, raw, pool_name, db_insert=True):
        pkt = header.bits
        newdbrow = RMapTelemetry(
            pool_id=self.pool_rows[pool_name].iid,
            idx=self.state[pool_name],
            cmd=pkt.PKT_TYPE,
            write=pkt.WRITE,
            verify=pkt.VERIFY,
            reply=pkt.REPLY,
            increment=pkt.INCREMENT,
            keystat=pkt.KEY if pkt.PKT_TYPE == 1 else pkt.STATUS,
            taid=pkt.TRANSACTION_ID,
            addr=pkt.ADDR if pkt.PKT_TYPE == 1 else None,
            datalen=pkt.DATA_LEN if hasattr(pkt, 'DATA_LEN') else 0,
            raw=raw)

        if not db_insert:
            self.state[pool_name] += 1
            return newdbrow

        self.session_factory_storage.add(newdbrow)
        self.state[pool_name] += 1
        now = time.time()
        if (now - self.last_commit_time) > self.commit_interval:
            self.session_factory_storage.commit()
            self.last_commit_time = now

    def process_feedata(self, header, raw, pool_name):
        pkt = header.bits
        newdbrow = FEEDataTelemetry(
            pool_id=self.pool_rows[pool_name].iid,
            idx=self.state[pool_name],
            pktlen=pkt.DATA_LEN,
            type=header.comptype,
            framecnt=pkt.FRAME_CNT,
            seqcnt=pkt.SEQ_CNT,
            raw=raw)

        self.session_factory_storage.add(newdbrow)
        self.state[pool_name] += 1
        now = time.time()
        if (now - self.last_commit_time) > self.commit_interval:
            self.session_factory_storage.commit()
            self.last_commit_time = now

    def crc_check_rmap(self, pckt):
        # if isinstance(pckt, (BitArray, BitStream, Bits, ConstBitStream)):
        #     pckt = pckt.bytes

        return bool(packet_config.rmapcrc(pckt))

    def extract_spw(self, stream):
        pkt_size_stream = b''
        pckts = []
        headers = []

        while True:
            pkt_size_stream += stream.read(2)
            if len(pkt_size_stream) < 2:
                break
            tla, pid = pkt_size_stream[:2]

            if (tla == self.TLA) and (pid in self.PROTOCOL_IDS):
                buf = pkt_size_stream
            else:
                pkt_size_stream = pkt_size_stream[1:]
                continue

            if self.PROTOCOL_IDS[pid] == "FEEDATA":
                header = self.pc.FeeDataTransferHeader()
            elif self.PROTOCOL_IDS[pid] == "RMAP":
                while len(buf) < 3:
                    instruction = stream.read(1)
                    if not instruction:
                        return pckts, buf
                    buf += instruction

                instruction = buf[2]

                if (instruction >> 6) & 1:
                    header = self.pc.RMapCommandHeader()
                elif (instruction >> 5) & 0b11 == 0b01:
                    header = self.pc.RMapReplyWriteHeader()
                elif (instruction >> 5) & 0b11 == 0b00:
                    header = self.pc.RMapReplyReadHeader()

            hsize = header.__class__.bits.size

            while len(buf) < hsize:
                buf += stream.read(hsize - len(buf))

            header.bin[:] = buf[:hsize]

            if self.PROTOCOL_IDS[pid] == "FEEDATA":
                pktsize = header.bits.DATA_LEN
            elif (header.bits.PKT_TYPE == 1 and header.bits.WRITE == 0) or (
                    header.bits.PKT_TYPE == 0 and header.bits.WRITE == 1):
                pktsize = hsize
            else:
                pktsize = hsize + header.bits.DATA_LEN + RMAP_PEC_LEN

            while len(buf) < pktsize:
                data = stream.read(pktsize - len(buf))
                if not data:
                    return pckts, pkt_size_stream
                buf += data

            buf = buf[:pktsize]
            pkt_size_stream = buf[pktsize:]

            pckts.append(buf)
            headers.append(header)

        return headers, pckts, pkt_size_stream

    def start_gui(self):
        self.gui =PUSDatapoolManagerGUI(pm=self)
        return

    # This functions raises the GUI to the foreground
    def raise_window(self):
        self.own_gui.present()

    def change_communication(self, application, instance=1, check=True):
        # If it is checked that both run in the same project it is not necessary to do it again
        if check:
            conn = cfl.dbus_connection(application, instance)
            # Both are not in the same project do not change

            if not conn.Variables('main_instance') == self.main_instance:
                # print('Both are not running in the same project, no change possible')
                self.logger.info('Application {} is not in the same project as {}: Can not communicate'.format(
                    self.my_bus_name, self.cfg['ccs-dbus_names'][application] + str(instance)))
                return False

        cfl.communication[application] = int(instance)
        return True

    def get_communication(self):
        return cfl.communication

    def on_univie_button(self, widget=None):
        self.gui.on_univie_button(False)

    def quit_func_pv(self):
        time.sleep(1)
        self.quit_func()

    def quit_func(self):
        for service in dbus.SessionBus().list_names():
            if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                editor = cfl.dbus_connection(service[0:-1].split('.')[1], service[-1])
                if self.main_instance == editor.Variables('main_instance'):
                    nr = self.my_bus_name[-1]
                    if nr == str(1):
                        nr = ''
                    editor.Functions('_to_console_via_socket', 'del(pmgr' + str(nr) + ')')

        # Tell the Poolviewer that all Pools are now static
        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            cfl.Functions(pv, 'stop_recording_info')  # Tell poolviewer that pool is no longer live
            #time.sleep(1)
        #for pool in self.loaded_pools.keys():
        #    self.disconnect(self.loaded_pools[pool].pool_name)

        #if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
        #    self.small_refresh_function()

        try:
            self.update_all_connections_quit()
        except:
            self.logger.warning('Communication Variable could not be changed for all running applicaitons')
        finally:
            Gtk.main_quit()
        return True

    def small_refresh_function(self):
        return

    def update_all_connections_quit(self):
        '''
        Tells all running applications that it is not longer availabe and suggests another main communicatior if one is
        available
        :return:
        '''
        our_con = []  # All connections to running applications without communications from the same applications as this
        my_con = []  # All connections to same applications as this
        for service in dbus.SessionBus().list_names():
            if service.split('.')[1] in self.cfg['ccs-dbus_names']:  # Check if connection belongs to CCS
                if service == self.my_bus_name:  # If own allplication do nothing
                    continue
                #self.logger.debug(type(service))
                conn = cfl.dbus_connection(service.split('.')[1], service[-1])
                if cfl.Variables(conn,'main_instance') == self.main_instance:  # Check if running in same project
                    if service.startswith(self.my_bus_name[:-1]):  # Check if it is same application type
                        my_con.append(service)
                    else:
                        our_con.append(service)

        instance = my_con[0][-1] if my_con else 0  # Select new main application if possible, is randomly selected
        our_con = our_con + my_con  # Add the instances of same application to change the main communication as well
        for service in our_con:  # Change the main communication for all applications+
            conn = cfl.dbus_connection(service.split('.')[1], service[-1])
            comm = cfl.Functions(conn, 'get_communication')
            # Check if this application is the main applications otherwise do nothing
            if str(comm[self.my_bus_name.split('.')[1]]) == self.my_bus_name[-1]:
                cfl.Functions(conn, 'change_communication', self.my_bus_name.split('.')[1], instance, False)
        return

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
                        conn.Functions('change_communication', self.my_bus_name.split('.')[1], self.my_bus_name[-1],
                                       False)

        if not cfl.communication[self.my_bus_name.split('.')[1]]:
            cfl.communication[self.my_bus_name.split('.')[1]] = int(self.my_bus_name[-1])

        # Connect to the terminals
        # cfl.communication[self.my_Bus_name.split('.')[1]] = int(self.my_Bus_name[-1])
        if Count == 1:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "pmgr = dbus.SessionBus().get_object('" +
                                     str(My_Bus_Name) + "', '/MessageListener')")
        else:
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.cfg['ccs-dbus_names']['editor']):
                    editor = cfl.dbus_connection('editor', service[-1])
                    editor.Functions('_to_console_via_socket', "pmgr" + str(Count) +
                                     " = dbus.SessionBus().get_object('" + str(My_Bus_Name) + "', '/MessageListener')")

        return


class LoadInfo(Gtk.Window):
    def __init__(self, parent=None, title=None):
        Gtk.Window.__init__(self)

        if title is None:
            self.set_title('Loading data to pool...')
        else:
            self.set_title(title)

        self.pmgr = parent

        grid = Gtk.VBox()
        # pixbuf = Gtk.gdk.pixbuf_new_from_file('pixmap/Icon_Space_weiß_en.png')
        # pixbuf = pixbuf.scale_simple(100, 100, Gtk.gdk.INTERP_BILINEAR)
        # logo = Gtk.image_new_from_pixbuf(pixbuf)
        logo = Gtk.Image.new_from_file('pixmap/ccs_logo_2.svg')

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        self.spinner.start()
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
        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):
            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            pv.Functions('small_refresh_function')
        try:
            window.destroy()
        except:
            pass



class UnsavedBufferDialog(Gtk.MessageDialog):
    def __init__(self, parent=None, msg=None):
        Gtk.MessageDialog.__init__(self, title="Quit Pool Manager?", parent=parent, flags=0.,)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                            Gtk.STOCK_NO, Gtk.ResponseType.NO,
                                            Gtk.STOCK_YES, Gtk.ResponseType.YES,)
        head, message = self.get_message_area().get_children()
        if msg == None:
            head.set_text('Response NO will keep the Pool Manager running in the background and only the GUI is closed')
        else:
            head.set_text(msg)

        self.show_all()


class PUSDatapoolManagerGUI(Gtk.ApplicationWindow):

    def __init__(self, pm=None, *args, **kwargs):
        super(PUSDatapoolManagerGUI, self).__init__(*args, **kwargs)

        if pm is not None:
            self.pm = pm
        else:
            self.pm = DatapoolManager()

        self.my_bus_name = self.pm.my_bus_name
        self.main_instance = self.pm.main_instance
        self.cfg = self.pm.cfg

        # PUSDatapoolManager.gui_running = True
        self.pm.gui_running = True
        box = self._create_gui()

        # self.set_default_size(480, 320)
        self.set_default_size(480, 380)
        self.set_border_width(3)
        self.set_title(self.pm.windowname.split('@')[-2] + 'Pool Manager' + self.pm.windowname.split('@')[-1])
        # self.set_title('Pool Manager')

        self.add(box)
        self.connect('delete-event', self.quit_func_gui)
        self.show_all()

        self.pm.own_gui = self
        self._populate_connection_view()

    def _create_gui(self):

        box = Gtk.VBox()
        box.set_spacing(4)

        box1 = Gtk.HBox()
        labelbox = Gtk.Entry()
        labelbox.set_tooltip_text('NAME')
        labelbox.set_placeholder_text('NAME')
        box1.pack_start(labelbox, 1, 1, 0)

        tmbut = Gtk.RadioButton.new_with_label_from_widget(None, 'TM')
        tmbut.set_tooltip_text('Unidirectional receiving connection')
        tcbut = Gtk.RadioButton.new_with_label_from_widget(tmbut, 'TC')
        tcbut.set_tooltip_text('Bidirectional connection')
        box1.pack_start(tmbut, 0, 0, 3)
        box1.pack_start(tcbut, 0, 0, 3)

        univie_button = self.create_univie_button()
        box1.pack_start(univie_button, 0, 0, 3)

        box.pack_start(box1, 0, 0, 0)

        box2 = Gtk.HBox()
        box2.set_spacing(2)
        hostbox = Gtk.Entry()
        hostbox.set_tooltip_text('HOST')
        hostbox.set_placeholder_text('HOST')
        box2.pack_start(hostbox, 1, 1, 0)

        portbox = Gtk.Entry()
        portbox.set_tooltip_text('PORT')
        portbox.set_placeholder_text('PORT')
        box2.pack_start(portbox, 1, 1, 0)

        box.pack_start(box2, 0, 0, 0)

        optionbox = Gtk.Entry()
        optionbox.set_tooltip_text('OPTIONS [drop_rx, is_server, timeout, pckt_filter]')
        optionbox.set_placeholder_text('OPTIONS [drop_rx, is_server, timeout, pckt_filter]')
        box.pack_start(optionbox, 0, 0, 0)

        buttonbox = Gtk.HBox()
        connect_in = Gtk.Button.new_with_label('Connect')
        buttonbox.pack_start(connect_in, 1, 1, 0)
        disconnect_in = Gtk.Button.new_with_label('Disconnect')
        buttonbox.pack_start(disconnect_in, 1, 1, 0)
        display_pool = Gtk.Button.new_with_label('Display')
        buttonbox.pack_start(display_pool, 1, 1, 0)
        # display_pool.tooltip_text('Select TM connection and display it in the Poolviewer')
        box.pack_start(buttonbox, 0, 0, 0)

        scrolled_view = Gtk.ScrolledWindow()
        tree_in = Gtk.TreeView()
        self.treeview = tree_in
        scrolled_view.add(tree_in)
        render = Gtk.CellRendererText(xalign=0)
        render.set_property('font', 'Monospace')
        column = Gtk.TreeViewColumn('Connections', render, text=0)
        tree_in.append_column(column)

        self.model_in = Gtk.ListStore(str, object)
        tree_in.set_model(self.model_in)
        box.pack_start(scrolled_view, 1, 1, 0)

        connect_in.connect('clicked', self.connect_incoming, labelbox, tmbut, hostbox, portbox, optionbox)
        disconnect_in.connect('clicked', self.disconnect_incoming, tree_in)
        display_pool.set_tooltip_text('Select TM connection to display in the Poolviewer')
        display_pool.connect('clicked', self.display_pool)

        self.statusbar = Gtk.Statusbar()
        self.statusbar.set_halign(Gtk.Align.END)
        box.pack_start(self.statusbar, 0, 0, 0)

        return box

    def create_univie_button(self):
        """
        Creates the Univie Button which can be found in every application, Used to Start all parts of the CCS and
        manage communication
        :return:
        """
        # univie_box = Gtk.HBox()
        univie_button = Gtk.ToolButton()
        # button_run_nextline.set_icon_name("media-playback-start-symbolic")
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            self.cfg.get('paths', 'ccs') + '/pixmap/Icon_Space_blau_en.png', 24, 24)
        icon = Gtk.Image.new_from_pixbuf(pixbuf)
        univie_button.set_icon_widget(icon)
        univie_button.set_tooltip_text('Applications and About')
        univie_button.connect("clicked", self.on_univie_button)
        # univie_box.add(univie_button)

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

        return univie_button

    def on_univie_button(self, action):
        """
        Adds the Popover menu to the UNIVIE Button
        :param action: Simply the button
        :return:
        """
        self.popover.show_all()
        self.popover.popup()

    def on_communication_dialog(self, button):
        cfl.change_communication_func(main_instance=self.pm.main_instance, parentwin=self)

    def _on_select_about_dialog(self, action):
        cfl.about_dialog(self)
        return

    def get_active_pool_name(self):
        return self.pool_selector.get_active_text()

    def connect_incoming(self, widget, labelbox, tmbut, hostbox, portbox, optionbox):
        try:
            tmcon = tmbut.get_active()
            if tmcon is True:
                tmcon = 'TM'
            elif tmcon is False:
                tmcon = 'TC'
            label = labelbox.get_text()
            if label.count('['):
                self.statusbar.push(0, 'Illegal character in label')
                return
            host = hostbox.get_text()
            port = int(portbox.get_text())
            options = optionbox.get_text()
            if options != '':
                try:
                    opts = {i.split('=')[0].strip(): eval(i.split('=')[1]) for i in options.split(',')}
                except IndexError:
                    self.pm.logger.error('Unable to parse option string')
                    self.statusbar.push(0, 'Unable to parse option string')
                    opts = {}
            else:
                opts = {}
        except ValueError:
            self.pm.logger.error('Invalid host/port')
            self.statusbar.push(0, 'Invalid host/port')
            return
        self.connect_to(label, host, port, tmcon, options=opts)

        return

    def connect_to(self, label, host, port, kind, options={}):
        try:
            if kind == 'TM':
                sockfd = self.pm.connect(label, host, int(port), return_socket=True, **options)[1]
                tmtc = 'TM'
            elif kind == 'TC':
                sockfd = self.pm.connect_tc(label, host, int(port), **options)
                tmtc = 'TC'
            else:
                sockfd = None
                self.pm.logger.erro('"kind" was not provided, nor the radio button to decide which kind of PUS it is (TM or TC)')
        except Exception as err:
            self.pm.logger.error(err)
            self.statusbar.push(0, 'Failed to connect to {}:{} | {}'.format(host, port, err))
            return
        if sockfd is not None:
            self.statusbar.push(0, 'Connected to {}:{}'.format(host, port))
            # Is now done in the self.pm.connect function for all incomming connections
            # self.model_in.append(['{} [{}:{}] | {} | {}'.format(label, host, port, tmtc, options), sockfd])
        else:
            self.statusbar.push(0, 'Failed to connect to {}:{}'.format(host, port))
        return

    def disconnect_incoming(self, widget=None, treeview=None):
        model, treepath = treeview.get_selection().get_selected_rows()
        if len(treepath) == 0:
            return
        # sockfd = model[treepath][1]
        label = model[treepath][0].split('[')[0].strip()
        val = model[treepath][0].split()
        tmtc = val[3]
        self.pm.disconnect_gui(label, tmtc=tmtc)
        model.remove(model.get_iter(treepath))
        return

    def disconnect_incoming_via_code(self, param=[]):  # parma[label,port,tmtc]
        model = self.treeview.get_model()
        if len(model) == 0:
            return
        # It will check all entries in the List and delete the correct connection
        count = 0
        found = False
        while count < len(model):
            value = model.get_value(model.get_iter(count), 0)  # Get the values of all Columns
            val = value.split()  # Split to get the wanted values
            label, tmtc = val[0], val[3]
            port = val[1].split(':')[1][:-1]  # Reads out the port of the function
            if label == param[0]:  # If the wanted connection is found delete the column
                if param[2]:
                    if param[2] == tmtc:
                        model.remove(model.get_iter(count))
                        found = True
                else:
                    model.remove(model.get_iter(count))
                    found = True
                # break #All connections with same label are disconnected
            count += 1
        if not found:
            self.statusbar.push(0, 'Could not find the connection in the list')
            self.pm.logger.info(
                'GUI: The asked connection ({}, {}) could not be found in the GUI-connection list'.format(label, port))
        return

    # Opens Poolviewer and Displays the selected Pool
    def display_pool(self, widget):
        model, treepath = self.treeview.get_selection().get_selected_rows()

        value = model.get_value(model.get_iter(treepath), 0)  # Get the value of selected column
        val = value.split()  # Split to get the wanted values
        label, tmtc = val[0], val[3]

        if cfl.is_open('poolviewer', cfl.communication['poolviewer']):

            pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
            # print(self.pm.loaded_pools_export_func())

            # Ignore Reply is ok here, it is actually needed, for some not understandable reason dbus got a problem
            # with line "self.pool_selector.set_active_iter(iter)" in function "_set_pool_list_and_display",
            # its working wiht the ignore_reply flag and the number is passed along that a return function can be called
            pv.Functions('update_pool_view', label, self.pm.loaded_pools_export_func(),
                         cfl.communication['poolmanager'], ignore_reply=True)
            # new_pool = pv.Functions('dbus_share_active_pool_info')
            # a = pv.ConnectionCheck()

            # if new_pool:
            #    self.pm.loaded_pools_func(new_pool[2], new_pool)
            #    print(new_pool)

        else:
            cfl.start_pv()

            # Could be that this part is senseless since the Viewer checks for pool when started, Solved not possible
            # If this is done strange behaviour from the Pool Viewer is happening, probably problem when Viewer and
            # Manager try to communicate
            # Here we have a little bit of a tricky situation since when we start the Poolviewer it wants to tell the
            # Manager to which number it can talk to but it can only do this when poolmanager is not busy...
            # Therefore it is first found out which number the new poolviewer will get and it will be called by that
            our_con = []
            # Look for all connections starting with com.poolviewer.communication,
            # therefore only one loop over all connections is necessary
            for service in dbus.SessionBus().list_names():
                if service.startswith(self.pm.cfg['ccs-dbus_names']['poolviewer']):
                    our_con.append(service)

            new_pv_nbr = 0
            if len(our_con) != 0:  # If an active poolviewer is found they have to belong to another prject
                for k in range(1, 10):  # Loop over all posible numbers
                    for j in our_con:  # Check every number with every poolviewer
                        if str(k) == str(j[-1]):  # If the number is not found set variable found to True
                            found = True
                        else:  # If number is found set variable found to False
                            found = False
                            break

                    if found:  # If number could not be found save the number and try connecting
                        new_pv_nbr = k
                        break

            else:
                new_pv_nbr = 1

            if new_pv_nbr == 0:
                self.pm.logger.warning('The maximum amount of Poolviewers has been reached')
                return

            # Wait a maximum of 10 seconds to connect to the poolviewer
            i = 0
            while i < 100:
                if cfl.is_open('poolviewer', new_pv_nbr):
                    # pv = cfl.dbus_connection('poolviewer', cfl.communication['poolviewer'])
                    pv = cfl.dbus_connection('poolviewer', new_pv_nbr)
                    break
                else:
                    i += 1
                    time.sleep(0.1)

            # pv.Functions('update_pool_view', label, ignore_reply=True)
            # Not needed as the Viewer opens all pools when newly started
            # Ignore Reply is ok here, it is actually needed, for some not understandable reason dbus got a problem
            # with line "self.pool_selector.set_active_iter(iter)" in function "_set_pool_list_and_display",
            # its working wiht the ignore_reply flag and the instance number is passed along to be called back
            # and update tge self.loaded_pool dict
            pv.Functions('update_pool_view', label, self.pm.loaded_pools_export_func(),
                         cfl.communication['poolmanager'], ignore_reply=True)


        return

    # Checks at the start of the GUI if connections are available
    def _populate_connection_view(self):
        for tm_conn in self.pm.connections:
            if self.pm.connections[tm_conn]['recording'] == True:
                # self.model_in.append(['{}:{}'.format(*sockfd.getpeername()), sockfd])
                # print(self.pm.connections[tm_conn]['socket'].getsockname()[2])
                self.model_in.append(['{} [{}:{}] | {} | {}'.format(tm_conn, self.pm.connections[tm_conn][
                    'socket'].getpeername()[0], self.pm.connections[tm_conn]['socket'].getpeername()[1], 'TM', ''),
                                      self.pm.connections[tm_conn]['socket']])

        for tc_conn in self.pm.tc_connections:
            if self.pm.tc_connections[tc_conn]['socket']:
                self.model_in.append(['{} [{}:{}] | {} | {}'.format(tc_conn,
                                                                    self.pm.tc_connections[tc_conn]['socket'].getpeername()[0],
                                                                    self.pm.tc_connections[tc_conn]['socket'].getpeername()[1],
                                                                    'TC', ''), tc_conn])

    def quit_func_gui(self, *args):

        # Ask if Poolmanager should be cloosed completly or
        ask = UnsavedBufferDialog(parent=self)
        response = ask.run()

        if response == Gtk.ResponseType.NO:
            Notify.Notification.new('Poolmanager is still running without a GUI').show()
            self.pm.gui_running = False
            self.pm.own_gui = None
            ask.destroy()
            self.destroy()
            return True

        elif response == Gtk.ResponseType.CANCEL:
            ask.destroy()
            return True

        else:
            # pmgr.Functions('quit_func', ignore_reply = True)
            ask.destroy()

        # Has to be in Class PusDataPoolManager otherwise can not be accessed via dbus
        self.pm.quit_func()
        return False


class CommonDatapoolManager(object):
    # defaults
    pecmode = 'warn'

    pckt_size_max = MAX_PKT_LEN
    tmtc = {0: 'TM', 1: 'TC'}
    tsync_flag = {0: 'U', 1: 'S'}

    connections = {}
    tc_connections = {}
    lock = threading.Lock()
    own_gui = None
    gui_running = False

    def __init__(self, cfilters='default', max_colour_rows=8000):

        self.cfg = confignator.get_config()

        self.commit_interval = float(self.cfg['database']['commit_interval'])

        # Set up the logger
        self.logger = cfl.start_logging('PoolManager')

        self.tc_sock = None
        self.crcfunc = crcmod.predefined.mkCrcFun(self.crctype)
        Notify.init('poolmgr')

        self.session_factory_idb = scoped_session_maker('idb')
        self.session_factory_storage = scoped_session_maker('storage')

        self.loaded_pools = {}
        self.databuflen = 0
        self.tc_databuflen = 0
        self.trashbytes = {None: 0}
        self.state = {}
        self.filtered_pckts = {}
        self.my_Bus_name = None
        # self.dbcon = self.session_factory()
        # self.dbcon_tc = connect_to_db()
        self.tc_name = 'pool_name'

        self.colour_filters = {}
        self.colour_list = deque(maxlen=max_colour_rows)
        if self.cfg.has_section('pool_colour_filters') and (cfilters is not None):
            for cfilter in json.loads(self.cfg['pool_colour_filters'][cfilters]):
                seq = len(self.colour_filters.keys())
                rgba = RGBA()
                rgba.parse(cfilter['colour'])
                cfilter['colour'] = rgba
                self.colour_filters.update({seq: cfilter})

    def connect(self, pool_name, host, port, protocol, tc=False, drop_rx=False, is_server=False, timeout=10,
                delete_abandoned=False, try_delete=True, pckt_filter=None, return_socket=False, options=''):

        if pool_name in self.connections:
            self.logger.info(self.connections[pool_name])
            if self.connections[pool_name]['recording']:
                self.logger.warning('Pool "{}" already exists and is recording!'.format(pool_name))
                return

        # To allow multiple access (the UI is reading from the table!)
        # we need a new DB session anyway.
        self.tm_name = pool_name
        if is_server:
            ss = socket.socket()
            ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            ss.settimeout(timeout)
            ss.bind((host, port))
            ss.listen()
            s, a = ss.accept()
            self.tc_connections[pool_name] = s
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
        self.connections[pool_name] = {'socket': s, 'recording': True}
        # if self.datapool.get(pool_name):
        #     self.datapool[pool_name]['socket'] = s
        # else:
        #     self.datapool.update(self._add_pool(pool_name, s))
        self.tm_recv_start(s, pool_name, protocol=False, delete_abandoned=delete_abandoned, try_delete=try_delete,
                           pckt_filter=pckt_filter)
        self.logger.info('Recording from new connection to ' + host + ':' + str(port) + '\n')
        new_session = self.session_factory_storage
        while True:
            dbrow = new_session.query(DbTelemetryPool).filter(DbTelemetryPool.pool_name == pool_name).first()
            if dbrow is None:
                new_session.close()
                time.sleep(0.1)
                continue
            else:
                timestamp = dbrow.modification_time
                new_session.close()
                break
        self.loaded_pools[pool_name] = ActivePoolInfo(pool_name, timestamp, pool_name, True)
        # Update the Gui if it exists
        if self.own_gui and s is not None:
            # self.own_gui.statusbar.push(0, 'Connected to {}:{}'.format(host, port))
            self.own_gui.model_in.append(
                ['{} [{}:{}] | {} | {}'.format(pool_name, host, port, 'TM', options), (timestamp, s)])
        if return_socket is True:
            return timestamp, s
        else:
            return timestamp

    def disconnect(self, poolname):
        return


def run():
    pm = DatapoolManager()
    Bus_Name = cfg.get('ccs-dbus_names', 'poolmanager')
    # DBusGMainLoop(set_as_default=True)
    DBus_Basic.MessageListener(pm, Bus_Name, *sys.argv)
    if '--nogui' not in sys.argv:
        pm.start_gui()

    Gtk.main()


if __name__ == "__main__":

    # Important to tell Dbus that Gtk loop can be used before the first dbus command
    DBusGMainLoop(set_as_default=True)

    # Define Variables
    startnew = True
    instance = False
    managers = []
    running = False
    # Check all dbus connections to find all running poolmanagers
    for service in dbus.SessionBus().list_names():
        if service.startswith(cfg['ccs-dbus_names']['poolmanager']):
            managers.append(service)
            break

    # Filter the instance name from the given arguments
    for arg in sys.argv:
        if arg.startswith('-') and arg.endswith('-'):
            instance = arg[1:-1]
    # no instance is given
    if not instance:
        for man in managers:
            pmgr = cfl.dbus_connection(man.split('.')[1], man[-1])
            # Check if poolmanagers is the same instance as the one taken from cfg
            if cfg['ccs-database']['project'] == pmgr.Variables('main_instance'):
                if pmgr.Variables('gui_running'):
                    run()
                    startnew = False
                else:
                    if '--nogui' not in sys.argv:  # Check if argument for nogui is given
                        pmgr.Functions('start_gui')  # Only start the gui
                    startnew = False

        # Start new
        if startnew:
            run()

    # Instance is given
    else:
        for man in managers:  # Do everything for all found poolmanagers
            pmgr = cfl.dbus_connection(man.split('.')[1], man[-1])
            # Check if poolmanagers is the same instance as the given one
            if not instance == pmgr.Variables('main_instance'):
                continue
            else:
                # If instance is the same check if gui is running
                if not pmgr.Variables('gui_running'):  # Gui is not running
                    if not '--nogui' in sys.argv:  # Check if argument for nogui is given
                        pmgr.Functions('start_gui')  # Only start the gui
                    startnew = False
                    break
                else:  # GUi is running
                    # Start new Poolmanager
                    startnew = False
                    run()
                    break
        # If no poolmanager with given instance name is found start a new poolmanager
        if startnew:
            run()

'''
    # Check if Poolmanager is already running
    if cfl.is_open('poolmanager', cfl.communication['poolmanager']):
        pmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        gui = pmgr.Variables('gui_running')
        running = True
    else:
        running = False
    #try:
    #    dbus_type = dbus.SessionBus()
    #    Bus_Name = cfg.get('ccs-dbus_names', 'poolmanager')
    #    dbus_type.get_object(Bus_Name, '/MessageListener')
    #    running = True
    #except:
    #    running = False

    # If argument --gui is given and if poolmanager is not running start manager with GUI
    if not '--nogui' in sys.argv and not running:
        #sys.argv.remove('--gui')
        pm = PUSDatapoolManager()

        # pm.connect_to(label='new tm', host='127.0.0.1', port=5570, kind='TM')
        # pm.connect_to(label='new tc', host='127.0.0.1', port=5571, kind='TC')
        #signal.signal(signal.SIGINT, signal.SIG_DFL)

        Bus_Name = cfg.get('ccs-dbus_names', 'poolmanager')
        #DBusGMainLoop(set_as_default=True)
        DBus_Basic.MessageListener(pm, Bus_Name, *sys.argv)

        pm.start_gui()

        Gtk.main()

    # If Manager is not running start it without a GUI
    elif not running:
        Bus_Name = cfg.get('ccs-dbus_names', 'poolmanager')
        #DBusGMainLoop(set_as_default=True)
        pv = PUSDatapoolManager()
        DBus_Basic.MessageListener(pv, Bus_Name, *sys.argv)

        Gtk.main()

    # If Manager is running and argument --background is given do nothing and keep Poolmanager running without a GUI
    # Do the same if a GUI is already running (prevents 2 GUIs)
    elif running and gui:
        #sys.argv.remove('--gui')
        pm = PUSDatapoolManager()

        # pm.connect_to(label='new tm', host='127.0.0.1', port=5570, kind='TM')
        # pm.connect_to(label='new tc', host='127.0.0.1', port=5571, kind='TC')
        #signal.signal(signal.SIGINT, signal.SIG_DFL)

        Bus_Name = cfg.get('ccs-dbus_names', 'poolmanager')
        #DBusGMainLoop(set_as_default=True)
        DBus_Basic.MessageListener(pm, Bus_Name, *sys.argv)

        pm.start_gui()

        Gtk.main()

    # If Manager is Running and nothing else is given open the GUI
    else:
        pmgr = cfl.dbus_connection('poolmanager', cfl.communication['poolmanager'])
        pmgr.Functions('start_gui')
'''
