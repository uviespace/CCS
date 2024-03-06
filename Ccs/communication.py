#!/usr/bin/env python3

"""
General purpose socket communication utilities

"""
import io
import queue
import select
import socket
import threading
import time


class Connector:
    """
    Utility class for bidirectional socket handling
    """

    RECV_NBYTES = 4096
    _decoding_types = ('hex', 'ascii')

    def __init__(self, host, port, is_server=False, response_to=2, recv_nbytes_min=0, save_to_file=None, msgdecoding='hex', resp_decoder=None):

        self.sock_timeout = 10
        self._response_to = response_to
        self.host = host
        self.port = port
        self.isserver = is_server
        self.recv_nbytes_min = recv_nbytes_min
        self.msgdecoding = msgdecoding
        self.resp_decoder = resp_decoder

        self.conn = None
        self.log = []
        self._storagefd = None
        self._storage_hexsep = ''
        self._storage_fmt = '{:.3f}\t{}\t{}\n'

        self.receiver = None

        self._startup(save_to_file)

    @property
    def msgdecoding(self):
        return self._msgdecoding

    @msgdecoding.setter
    def msgdecoding(self, typ):
        if typ not in self._decoding_types:
            print('WARNING: Invalid decoding format {}. Using hex. {}'.format(typ, self._decoding_types))
            typ = 'hex'
        self._msgdecoding = typ

    def _startup(self, save_to):

        self.setup_port()
        if save_to is not None:
            self.setup_storage(save_to)

    def setup_storage(self, fname, hexsep=None, fmt=None):
        self._storagefd = open(fname, 'w')
        if hexsep is not None:
            self._storage_hexsep = hexsep
        if fmt is not None:
            self._storage_fmt = fmt

    def setup_port(self):

        self.sockfd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockfd.settimeout(self.sock_timeout)

        if self.isserver:
            self.sockfd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sockfd.bind((self.host, self.port))
            self.sockfd.listen()
            print('Listening for connections on {}:{}'.format(self.host, self.port))

    def _connect(self):

        if self.isserver:
            self.conn, addr = self.sockfd.accept()
            print('Got connection on {}:{}'.format(self.host, self.port))
        else:
            self.sockfd.connect((self.host, self.port))
            self.conn = self.sockfd
            print('Connected to {}:{}'.format(self.host, self.port))

        self.conn.settimeout(self._response_to)

    def _close(self, servershtdwn):
        if self.conn.fileno() != -1:
            self.conn.close()
            print('Closed connection to {}:{}'.format(self.host, self.port))

        if servershtdwn and self.sockfd.fileno() != -1:
            print('Closing server {}'.format(self.sockfd.getsockname()))
            self.sockfd.close()

    def connect(self):
        if self.conn is not None and self.conn.fileno() < 0:
            self.setup_port()
        self._connect()

    def close(self):
        self._close(False)

    def close_server(self):
        if self.isserver:
            self._close(True)
        else:
            print('Not a server')

    def close_storage(self):
        if self._storagefd is None:
            print('No file to close')
            return

        self._storagefd.close()
        self._storagefd = None

    def dump_log(self, fname, hexsep='', fmt='{:.3f}\t{}\t{}'):
        with open(fname, 'w') as fd:
            fd.write('\n'.join([fmt.format(t, _msgdecoder(msg, self.msgdecoding, sep=hexsep), _msgdecoder(resp, self.msgdecoding, sep=hexsep)) for (t, msg, resp) in self.log]))

    def send(self, msg, rx=True, output=False):

        if hasattr(msg, 'raw'):
            msg = msg.raw

        if self.conn is not None:
            self.conn.sendall(msg)
            t = time.time()

            resp = b''
            if rx:
                resp += self._recv_response()

            self.log.append((t, msg, resp))

            if self._storagefd is not None:
                self._storagefd.write(self._storage_fmt.format(t, _msgdecoder(msg, self.msgdecoding, sep=self._storage_hexsep), _msgdecoder(resp, self.msgdecoding, sep=self._storage_hexsep)))
                self._storagefd.flush()

            if output:
                print('{:.3f}: SENT {} | RECV {}'.format(t, _msgdecoder(msg, self.msgdecoding), _msgdecoder(resp, self.msgdecoding)))

            if rx:
                return resp if self.resp_decoder is None else self.resp_decoder(resp)

        else:
            print('Not connected!')

    def recv(self, nbytes=None):

        if nbytes is None and self.recv_nbytes_min != 0:
            nbytes = self.recv_nbytes_min
        elif nbytes is None:
            nbytes = self.RECV_NBYTES

        return self.conn.recv(nbytes)

    def _recv_response(self):

        data = b''

        try:
            if self.recv_nbytes_min != 0:
                while len(data) < self.recv_nbytes_min:
                    data += self.conn.recv(self.recv_nbytes_min - len(data))
            else:
                data += self.conn.recv(self.RECV_NBYTES)
        except Exception as err:
            print('No/invalid response ({})'.format(err))
        finally:
            return data

    def set_response_to(self, seconds):
        self.conn.settimeout(seconds)
        self._response_to = seconds

    def start_receiver(self, procfunc=None, outfile=None, ofmode='w', pkt_parser_func=None):
        """

        :param procfunc:
        :param outfile:
        :param ofmode:
        :return:
        """
        if self.conn is None:
            print('No connection')
            return

        if self.receiver is None:
            self.receiver = Receiver([self.conn], procfunc=procfunc, outfile=outfile, ofmode=ofmode, pkt_parser_func=pkt_parser_func)
            self.receiver.start()
        else:
            print('Receiver already initialised')

    def stop_receiver(self, clear=False):
        if self.receiver is None:
            print('No receiver to stop')
            return

        self.receiver.stop()

        if clear:
            self.receiver = None

    @property
    def recvd_data(self):
        if self.receiver is not None:
            return self.receiver.recvd_data_buf.queue

    @property
    def proc_data(self):
        if self.receiver is not None:
            return self.receiver.proc_data


class Receiver:
    """
    Reads and processes data from sockets
    """

    RECV_BYTES = 4096
    SEL_TIMEOUT = 2
    RECV_BUF_SIZE = 1024**3

    def __init__(self, sockfds, procfunc=None, recv_buf_size=RECV_BUF_SIZE, outfile=None, ofmode='w', pkt_parser_func=None):

        self.sockfds = sockfds
        self.recvd_data_buf = queue.Queue(recv_buf_size)
        self._procfunc = procfunc
        self._recv_thread = None
        self._proc_thread = None
        self.proc_data = []
        self._pkt_parser_func = pkt_parser_func

        if outfile is not None:
            self.proc_data_fd = open(outfile, ofmode)
        else:
            self.proc_data_fd = None

        self._isrunning = False

    def start(self):
        if (self._recv_thread is None) or (not self._recv_thread.is_alive()):
            self._start_recv()
        else:
            print('Recv already running!')

        if self._procfunc is not None:
            if (self._proc_thread is None) or (not self._proc_thread.is_alive()):
                self._start_processing()

    def stop(self):
        self._isrunning = False

    def _start_recv(self):
        self._isrunning = True
        self._recv_thread = threading.Thread(target=self._recv_worker, name='recv_worker')
        # self._recv_thread.daemon = True
        self._recv_thread.start()

    def _recv_worker(self):

        for sockfd in self.sockfds:
            if sockfd is not None:
                print('Receiving from socket {}:{}'.format(*sockfd.getpeername()))
            else:
                self.sockfds.remove(sockfd)

        while self._isrunning:
            try:
                rd, wr, er = select.select(self.sockfds, [], self.sockfds, self.SEL_TIMEOUT)
                for sock in rd:
                    if self._pkt_parser_func is not None:
                        self.recvd_data_buf.put((time.time(), self._pkt_parser_func(sock)))
                    else:
                        self.recvd_data_buf.put((time.time(), sock.recv(self.RECV_BYTES)))

                for sock in er:
                    print('Error in {}'.format(sock.getpeername()))
                    self.sockfds.remove(sock)
                    if not self.sockfds:
                        self.stop()

            except socket.timeout:
                continue

            except (ValueError, OSError) as err:
                print(err)
                self.stop()
                break

        # for sockfd in self.sockfds:
        #     print('Stopped receiving from socket {}:{}'.format(*sockfd.getpeername()))
        print('Receiving stopped')

    def _start_processing(self):
        self._proc_thread = threading.Thread(target=self._proc_worker, name='proc_worker')
        self._proc_thread.daemon = True
        self._proc_thread.start()

    def _proc_worker(self):
        while self._isrunning:
            try:
                t, data = self.recvd_data_buf.get(timeout=1)
                procdata = self._procfunc(data, ts=t)
                self.proc_data.append(procdata)

                if self.proc_data_fd is not None:
                    try:
                        if self.proc_data_fd.mode.count('b'):
                            self.proc_data_fd.write(procdata)
                        else:
                            self.proc_data_fd.write(str(procdata))
                    except io.UnsupportedOperation as err:
                        print(err)
                        break
                    except Exception as err:
                        self.proc_data_fd.write('# {} #\n'.format(err))
                        continue
                    finally:
                        self.proc_data_fd.flush()

            except queue.Empty:
                continue
            except Exception as err:
                print('Processing error:', err)
                self._isrunning = False

        print('Processing stopped')
        if self.proc_data_fd is not None:
            self.proc_data_fd.close()


def _msgdecoder(msg, fmt, sep=''):
    if fmt == 'hex':
        return hexify(msg, sep=sep)
    elif fmt == 'ascii':
        return toascii(msg)
    else:
        raise NotImplementedError('Unknown decoding style {}'.format(fmt))


def hexify(bs, sep=''):

    if bs is None:
        bs = b''

    if isinstance(sep, tuple):
        sep, grp = sep
    else:
        grp = 1

    return bs.hex().upper() if sep == '' else bs.hex(sep, grp).upper()


def toascii(bs, errors='replace'):
    return bs.decode('ascii', errors=errors)


def proc_func_generic(data, ts=None):
    """
    Generic function that takes data and returns it in a list. Example function to process raw data from Receiver input queue recvd_data_buf for proc_data storage.

    :param data: raw data
    :param ts: timestamp from input queue associated with the raw data
    :return:
    """

    if ts is None:
        ts = ''
    else:
        ts = '{:.6f}'.format(ts)

    return [ts, str(data)]


def pkt_parser(sock, default_len=7):
    headlen = 1
    pkt = sock.recv(headlen)
    if pkt == b'\x35':
        plen = 40
        while len(pkt) < plen:
            pkt += sock.recv(plen - len(pkt))
        return pkt
    else:
        return pkt + sock.recv(default_len - headlen)
