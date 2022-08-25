#!/usr/bin/env python3

import configparser
import queue
import socket
import signal
import sys
import threading
import time

import pus_datapool as pus

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class PortSplitter:

    def __init__(self, interactive=False):
        self.poolmgr = pus.DatapoolManager()

        self.sock_timeout_in = 10
        self.sock_timeout_out = 10
        self.incoming_connections = []
        self.outgoing_connections = {}
        self.tm_pool = queue.Queue()
        self.lost_pckts = 0

        self._startup(interactive)
        self.start_packet_forward()

    def _startup(self, interactive):
        if len(sys.argv) < 2:
            if interactive:
                self.cfg = None
                return
            else:
                print('USAGE: <CONFIG_FILE>\nOptions:\n\t--gui\t'
                      'GUI mode with interactively configurable in/out connections')
                sys.exit()
        else:
            self.cfg = configparser.ConfigParser()
            self.cfg.read(sys.argv[1])

        self.sock_timeout_in = float(self.cfg['misc']['sock_timeout_in'])
        self.sock_timeout_out = float(self.cfg['misc']['sock_timeout_out'])

        self.setup_ports()
        self.start_incoming()

    def setup_ports(self):
        print('Setting up ports:')
        for stsst, addr in self.cfg['outgoing'].items():
            try:
                if not stsst.count(','):
                    stsst += ','
                st, sst = stsst.split(',')
                if st != 'default':
                    st = int(st)
                if sst not in ['', 'x']:
                    sst = int(sst)
                else:
                    sst = 'x'
            except ValueError:
                print('Invalid ST, SST value')
                continue

            # check for multiple ports for same ST/SST
            addrlist = addr.split(',')

            for address in addrlist:
                try:
                    host, port = address.split(':')
                    port = int(port)
                except ValueError:
                    print('Invalid address format')
                    continue
                self.setup_outgoing(st, sst, host, port)

    def setup_outgoing(self, st, sst, host, port):
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockfd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sockfd.bind((host, port))
        sockfd.settimeout(self.sock_timeout_out)
        sockfd.listen()
        print('Waiting for connection on {}:{}...'.format(*sockfd.getsockname()))
        try:
            r, addr = sockfd.accept()
            print('...connected.')
        except socket.timeout:
            print('...timed out.')
            return
        except OSError as error:
            print(error)
            return
        if st in self.outgoing_connections:
            if sst in self.outgoing_connections[st]:
                self.outgoing_connections[st][sst].append(r)
            else:
                self.outgoing_connections[st][sst] = [r]
        else:
            self.outgoing_connections[st] = {sst: [r]}
        return r

    def start_incoming(self):
        for addr in self.cfg['incoming'].values():
            try:
                host, port = addr.split(':')
            except ValueError:
                print('Invalid address format')
                continue
            self.connect_incoming(host, port)

    def connect_incoming(self, host=None, port=None):
        sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockfd.settimeout(self.sock_timeout_in)
        print('Trying to connect to {}:{}...'.format(host, port))
        tstart = time.time()
        while time.time() - tstart < self.sock_timeout_in:
            try:
                sockfd.connect((host, int(port)))
                print('...connection established.')
                self.incoming_connections.append(sockfd)
                t = threading.Thread(target=self._receive_data_worker, args=[sockfd],
                                     name='{}:{}-receiver'.format(host, port))
                t.setDaemon(True)
                t.start()
                return sockfd
            except socket.error:
                time.sleep(0.2)
        print('...could not establish connection.')

    def start_packet_forward(self):
        fw = threading.Thread(target=self._packet_forward_worker)
        fw.setDaemon(True)
        fw.name = 'forward-worker'
        fw.start()

    def _receive_data_worker(self, sockfd):
        tail = b''
        while sockfd.fileno() >= 0 and sockfd in self.incoming_connections:
            try:
                buf, tail = self.poolmgr.receive_from_socket(sockfd, pkt_size_stream=tail)
                self.tm_pool.put(buf)
            except socket.timeout:
                continue
            except socket.error:
                break
            except pus.struct.error:
                break
        print('Lost connection to {}:{}, closing socket.'.format(*sockfd.getpeername()))
        sockfd.close()

    def _packet_forward_worker(self):

        def _try_send(sockfd, buf):
            try:
                sockfd.send(buf)
            except OSError as error:
                print('Could not forward packet to {}:{} --'.format(*sockfd.getsockname()), error)
                self.lost_pckts += 1
                print('Total packets lost: {:d}'.format(self.lost_pckts))

        def _forward(buf):
            st, sst = self.poolmgr.unpack_pus(buf)[10:12]
            if st in self.outgoing_connections:
                if sst in self.outgoing_connections[st]:
                    for sockfd in self.outgoing_connections[st][sst]:
                        _try_send(sockfd, buf)
                elif 'x' in self.outgoing_connections[st]:
                    for sockfd in self.outgoing_connections[st]['x']:
                        _try_send(sockfd, buf)
                elif 'default' in self.outgoing_connections:
                    for sockfd in self.outgoing_connections['default']['x']:
                        _try_send(sockfd, buf)
                else:
                    self.lost_pckts += 1
                    print('TM {:d},{:d} not forwarded, total packets lost: {:d}'.format(st, sst, self.lost_pckts))
            elif 'default' in self.outgoing_connections:
                for sockfd in self.outgoing_connections['default']['x']:
                    _try_send(sockfd, buf)
            else:
                self.lost_pckts += 1
                print('TM {:d},{:d} not forwarded, total packets lost: {:d}'.format(st, sst, self.lost_pckts))

        while True:
            if len(self.outgoing_connections) > 0:
                _forward(self.tm_pool.get())
            else:
                time.sleep(0.2)

    # def forward(self, buf):
    #     tm = self.poolmgr.unpack_pus(buf)
    #     if tm[10] in self.connections:
    #         self.connections[tm[10]].send(buf)
    #     else:
    #         self.connections['default'].send(buf)


class PortSplitterGUI(Gtk.Window):

    def __init__(self):
        super(PortSplitterGUI, self).__init__()
        box = self._create_gui()

        self.set_default_size(600, 400)
        self.set_border_width(3)
        self.set_title('PortSplitter')

        self.add(box)
        self.connect('delete-event', Gtk.main_quit)
        self.show_all()

        self.ps = PortSplitter(interactive=True)
        self._populate_connection_views()

    def _create_gui(self):
        box = Gtk.VBox()
        paned = Gtk.Paned(wide_handle=True)
        box.pack_start(paned, 1, 1, 0)

        # incoming pane
        box1 = Gtk.VBox()

        label = Gtk.Label()
        label.set_markup('<span size="large" foreground="black" weight="bold">IN</span>')
        label.set_padding(0, 5)
        box1.pack_start(label, 0, 0, 0)

        entrybox = Gtk.Entry()
        entrybox.set_tooltip_text('<HOST:PORT>')
        box1.pack_start(entrybox, 0, 0, 0)

        buttonbox = Gtk.HBox()
        connect_in = Gtk.Button('Connect')
        buttonbox.pack_start(connect_in, 1, 1, 0)
        disconnect_in = Gtk.Button('Disconnect')
        buttonbox.pack_start(disconnect_in, 1, 1, 0)
        box1.pack_start(buttonbox, 0, 0, 0)

        scrolled_view = Gtk.ScrolledWindow()
        tree_in = Gtk.TreeView()
        scrolled_view.add(tree_in)
        render = Gtk.CellRendererText(xalign=1)
        render.set_property('font', 'Monospace')
        column = Gtk.TreeViewColumn('Connections', render, text=0)
        tree_in.append_column(column)

        self.model_in = Gtk.ListStore(str, object)
        tree_in.set_model(self.model_in)
        box1.pack_start(scrolled_view, 1, 1, 0)

        connect_in.connect('clicked', self.connect_incoming, entrybox)
        disconnect_in.connect('clicked', self.disconnect_incoming, tree_in)

        paned.add1(box1)

        # outgoing pane
        box2 = Gtk.VBox()

        label = Gtk.Label()
        label.set_markup('<span size="large" foreground="black" weight="bold">OUT</span>')
        label.set_padding(0, 5)
        box2.pack_start(label, 0, 0, 0)

        bbox = Gtk.HBox()
        tm_entry = Gtk.Entry()
        tm_entry.set_tooltip_text('<ST[,SST]>')
        bbox.pack_start(tm_entry, 1, 1, 0)
        conn_entry = Gtk.Entry()
        conn_entry.set_tooltip_text('<HOST:PORT>')
        bbox.pack_start(conn_entry, 1, 1, 0)
        box2.pack_start(bbox, 0, 0, 0)

        buttonbox = Gtk.HBox(homogeneous=True)
        add_out = Gtk.Button('Add')
        buttonbox.pack_start(add_out, 1, 1, 0)
        remove_out = Gtk.Button('Remove')
        buttonbox.pack_start(remove_out, 1, 1, 0)
        box2.pack_start(buttonbox, 0, 0, 0)

        scrolled_view = Gtk.ScrolledWindow()
        tree_out = Gtk.TreeView()
        scrolled_view.add(tree_out)
        for i, name in enumerate(['(Sub-)Type', 'Connection']):
            render = Gtk.CellRendererText(xalign=1)
            render.set_property('font', 'Monospace')
            column = Gtk.TreeViewColumn(name, render, text=i)
            tree_out.append_column(column)

        self.model_out = Gtk.ListStore(str, str, object)
        tree_out.set_model(self.model_out)
        box2.pack_start(scrolled_view, 1, 1, 0)

        add_out.connect('clicked', self.add_outgoing, tm_entry, conn_entry)
        remove_out.connect('clicked', self.remove_outgoing, tree_out)

        paned.add2(box2)

        self.statusbar = Gtk.Statusbar()
        self.statusbar.set_halign(Gtk.Align.END)
        box.pack_start(self.statusbar, 0, 0, 0)

        return box

    def connect_incoming(self, widget=None, entrybox=None):
        try:
            host, port = entrybox.get_text().split(':')
        except ValueError:
            print('Invalid address format')
            self.statusbar.push(0, 'Invalid address format')
            return
        if '{}:{}'.format(host, port) in [row[0] for row in self.model_in]:
            return
        sockfd = self.ps.connect_incoming(host, int(port))
        if sockfd is None:
            self.statusbar.push(0, 'Failed to connect to {}:{}'.format(host, port))
            return
        else:
            self.statusbar.push(0, 'Connected to {}:{}'.format(host, port))
        self.model_in.append(['{}:{}'.format(host, port), sockfd])

    def disconnect_incoming(self, widget=None, treeview=None):
        model, treepath = treeview.get_selection().get_selected_rows()
        if len(treepath) == 0:
            return
        sockfd = model[treepath][1]
        self.ps.incoming_connections.remove(sockfd)
        model.remove(model.get_iter(treepath))

    def add_outgoing(self, widget=None, tm_entry=None, conn_entry=None):
        # TM type
        stsst = tm_entry.get_text()
        try:
            if not stsst.count(','):
                stsst += ','
            st, sst = stsst.split(',')
            if st != 'default':
                st = int(st)
            if sst not in ['', 'x']:
                sst = int(sst)
            else:
                sst = 'x'
        except ValueError:
            print('Invalid ST, SST value')
            self.statusbar.push(0, 'Invalid ST, SST value')
            return

        # connection setup
        try:
            host, port = conn_entry.get_text().split(':')
            port = int(port)
        except ValueError:
            print('Invalid address format')
            self.statusbar.push(0, 'Invalid address format')
            return
        sockfd = self.ps.setup_outgoing(st, sst, host, port)
        if sockfd is None:
            self.statusbar.push(0, 'Failed to connect to {}:{}'.format(host, port))
            return
        else:
            self.statusbar.push(0, 'Connected to {}:{}'.format(host, port))
        if st == 'default':
            self.model_out.append(['{}'.format(st), '{}:{}'.format(host, port), sockfd])
        else:
            self.model_out.append(['{},{}'.format(st, sst), '{}:{}'.format(host, port), sockfd])

    def remove_outgoing(self, widget=None, treeview=None):
        model, treepath = treeview.get_selection().get_selected_rows()
        if len(treepath) == 0:
            return
        stsst, addr, sockfd = model[treepath]
        if stsst == 'default':
            st, sst = 'default', 'x'
        else:
            st, sst = stsst.split(',')
        if st != 'default':
            st = int(st)
        if sst != 'x':
            sst = int(sst)
        if len(self.ps.outgoing_connections[st][sst]) <= 1:
            self.ps.outgoing_connections[st].pop(sst)
        else:
            self.ps.outgoing_connections[st][sst].remove(sockfd)
        if len(self.ps.outgoing_connections[st]) == 0:
            self.ps.outgoing_connections.pop(st)
        sockfd.close()
        model.remove(model.get_iter(treepath))

    def _populate_connection_views(self):
        for sockfd in self.ps.incoming_connections:
            self.model_in.append(['{}:{}'.format(*sockfd.getpeername()), sockfd])

        for st in self.ps.outgoing_connections:
            for sst in self.ps.outgoing_connections[st]:
                for sockfd in self.ps.outgoing_connections[st][sst]:
                    if st == 'default':
                        self.model_out.append(['{}'.format(st), '{}:{}'.format(*sockfd.getsockname()), sockfd])
                    else:
                        self.model_out.append(['{},{}'.format(st, sst), '{}:{}'.format(*sockfd.getsockname()), sockfd])


if __name__ == '__main__':
    if '--gui' in sys.argv:
        sys.argv.remove('--gui')
        PortSplitterGUI()
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        Gtk.main()
    else:
        PortSplitter()
