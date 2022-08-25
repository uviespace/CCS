import pickle
import logging
import logging.handlers
import socketserver
import datetime
import dbus
import dbus.service
import time
import select
import os
from os import listdir
from os.path import isfile, join

import confignator
cfg = confignator.get_config()

SOCKET_TIMEOUT = 0.5
SOCKET_RD_INTERVAL = 0.5
LOGFMT = '%(asctime)s: %(name)-15s %(levelname)-8s %(message)s'


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """
    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = int.from_bytes(chunk, 'big')
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = pickle.loads(chunk)
            record = logging.makeLogRecord(obj)
            self.handleLogRecord(record)

    def handleLogRecord(self, record):
        # if a name is specified, we use the named logger rather than the one
        # implied by the record.
        if self.server.logname is not None:
            name = self.server.logname
        else:
            name = record.name
        logger = logging.getLogger(name)
        # N.B. EVERY record gets logged. This is because Logger.handle
        # is normally called AFTER logger-level filtering. If you want
        # to do filtering, do it at the client end to save wasting
        # cycles and network bandwidth!
        logger.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """
    allow_reuse_address = True

    def __init__(self, host='localhost',
                 port=logging.handlers.DEFAULT_TCP_LOGGING_PORT, handler=LogRecordStreamHandler):

        super(LogRecordSocketReceiver, self).__init__((host, port), handler)

        # socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
        # self.abort = 0
        self.timeout = SOCKET_TIMEOUT
        self.logname = None

    def serve_until_stopped(self, cfg):

        # Check all dbus connections if any process is running, if not close the logging file
        while True:
            closing = True
            dbus_names = cfg['ccs-dbus_names'].values()

            for service in dbus.SessionBus().list_names():
                if service.startswith('com') and service[:-1] in dbus_names:
                    closing = False

            # If anything is incoming call the handler and log it
            rd, wr, ex = select.select([self.socket.fileno()], [], [], self.timeout)
            if rd:
                self.handle_request()

        # Close the file if there is no more dbus connection
            if closing:
                break
            else:
                time.sleep(SOCKET_RD_INTERVAL)


def main():
    # Specify how the format of the Log-Filename is and where to save it
    logname = '%Y%m%d_%H%M%S'
    logpath = cfg.get('ccs-paths', 'log-file-dir')

    # Choose which time should be used for the title
    tnow = datetime.datetime.now          # Use the local- Time for the log file title
    # tnow = datetime.datetime.utcnow      # Use the UTC- Time for the log file title

    # Get the time in the correct format
    logtimestart = datetime.datetime.strftime(tnow(), logname)
    logfilename = os.path.join(logpath, logtimestart + '.log')
    logfmt = LOGFMT

    logger = logging.getLogger('log_server')

    # Start the server
    # If it is already running LogRecordSocketReciever() will give an error and the server is therefor not started again
    try:
        tcpserver = LogRecordSocketReceiver()

        # set up the file logging
        # logging.basicConfig(format='%(asctime)s: %(name)-15s %(levelname)-8s %(message)s', filename=logfilename)
        fh = logging.FileHandler(filename=logfilename)
        fh.setFormatter(logging.Formatter(logfmt))
        rl = logging.getLogger()
        rl.addHandler(fh)
        rl.setLevel(getattr(logging, cfg.get('ccs-logging', 'level').upper()))
        # rl.setLevel(logging.INFO)

        # Check how many log files should be kept and delete the rest
        amount = cfg.get('ccs-logging', 'max_logs')
        # If amount is empty keep an endless amount of logs
        if amount:
            while True:
                onlyfiles = [f for f in listdir("logs/") if isfile(join("logs/", f))]
                onlyfiles.sort()
                if len(onlyfiles) > int(amount) + 1:
                    os.system('rm logs/' + str(onlyfiles[1]))
                else:
                    break

        logger.info('TCP-server for logging started')
        tcpserver.serve_until_stopped(cfg)
        logger.info('TCP-server for logging shutting down')
    # Catch exception if log_server is already running and address/port is already in use
    except OSError:
        logger.info('TCP-server for logging seems to be already running.')
    except Exception as err:
        raise err


class Logging:
    # This sets up a logging client for the already running TCP-logging Server,
    # The logger is returned with the given name and can be used like a normal logger
    def start_logging(self, name):
        loglevel = confignator.get_option('ccs-logging', 'level')

        rootLogger = logging.getLogger('')
        rootLogger.setLevel(loglevel)
        socketHandler = logging.handlers.SocketHandler('localhost',
                                                       logging.handlers.DEFAULT_TCP_LOGGING_PORT)
        # don't bother with a formatter, since a socket handler sends the event as
        # an unformatted pickle
        rootLogger.addHandler(socketHandler)
        logger = logging.getLogger(name)
        return logger


if __name__ == '__main__':
    main()
