import pickle
import logging
import logging.handlers
import socketserver
import struct
import datetime
import dbus
import dbus.service
import time
import os
from os import listdir
from os.path import isfile, join

import confignator


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
            slen = struct.unpack('>L', chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = self.unPickle(chunk)
            record = logging.makeLogRecord(obj)
            self.handleLogRecord(record)

    def unPickle(self, data):
        return pickle.loads(data)

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

        socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
        self.abort = 0
        self.timeout = 1
        self.logname = None

    def serve_until_stopped(self, cfg):

        import select

        # Check all dbus connections if any process is running, if not close the logging file
        dbustype = dbus.SessionBus()
        while True:
            dbus_names = cfg['ccs-dbus_names']
            closing = True

            our_con = []
            for service in dbus.SessionBus().list_names():
                if service.startswith('com'):
                    our_con.append(service)

            for app in our_con:
                if app[:-1] in cfg['ccs-dbus_names'].values():
                    closing = False

            #for name in dbus_names:
            #    Bus_name = cfg.get('ccs-dbus_names', name)
            #    try:
            #        connection = dbustype.get_object(Bus_name, '/MessageListener')
            #        connection.LoggingCheck()
            #    except:
            #        closing += 1

            # If anything is incomming call the handler and log it
            rd, wr, ex = select.select([self.socket.fileno()],
                                       [], [],
                                       self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort

        # Close the file if there is no more dbus connection
            if closing:
                break
            else:
                time.sleep(.1)


def main():
    # Specify how the format of the Log-Filename is and where to save it
    logname = '%Y%m%d_%H%M%S'
    logpath = confignator.get_option('ccs-paths', 'log-file-dir')

    # Choose which time should be used for the title
    tnow = datetime.datetime.now          # Use the local- Time for the log file title
    # tnow = datetime.datetime.utcnow      # Use the UTC- Time for the log file title

    # Get the time in the correct format
    logtimestart = datetime.datetime.strftime(tnow(), logname)
    logfilename = os.path.join(logpath, logtimestart + '.log')

    # Connect to the config file
    cfg = confignator.get_config(file_path=confignator.get_option('config-files', 'ccs'))

    # Start the server
    # If it is already running LogRecordSocketReciever() will give an error and the server is therefor not started again
    try:
        tcpserver = LogRecordSocketReceiver()

        # Check how many log files should be kept and delete the rest
        amount = cfg.get('ccs-logging', 'max_logs')
        if amount: # If amount is empty keep an endless amount of logs
            while True:
                onlyfiles = [f for f in listdir("logs/") if isfile(join("logs/", f))]
                onlyfiles.sort()
                if len(onlyfiles) > int(amount) + 1:
                    os.system('rm logs/' + str(onlyfiles[1]))
                else:
                    break

        # Give a format and filename configuration for logging
        logging.basicConfig(
            format='%(asctime)s: %(name)-15s %(levelname)-8s %(message)s', filename=logfilename)
        # print('TCP-server for logging is started')
        tcpserver.serve_until_stopped(cfg)
    except:
        pass


class Logging():
    # This sets up a logging client for the already running TCP-logging Server,
    # The logger is returned with the given name an can be used like a normal logger
    def start_logging(self, name):
        loglevel = confignator.get_option('logging', 'level')

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
