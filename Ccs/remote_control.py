"""
The remote_control module facilitates remote commanding of and data exchange with the CCS.
"""

# import os
import pickle
import socket
import struct
import subprocess
import sys
import time

import Pyro4


@Pyro4.expose
class DataReceiver(object):

    """The DataReceiver provides remote commanding of and data retrieval from the CCS."""

    header_len = 4

    def __init__(self, host='', sendport=4242, recvport=4343):
        """

        @param host:
        @param sendport:
        @param recvport:
        """
        self.host = host
        self.sendport = sendport
        self.recvport = recvport

    def sender(self, msg):
        """

        @param msg:
        @return:
        """
        emsg = msg.encode()
        s = socket.socket()
        s.connect((self.host, self.sendport))
        tb = s.send(emsg)
        ack = s.recv(1024)
        s.close()
        return tb, ack

    def receiver(self):
        """

        @return:
        """
        s = socket.socket()
        s.connect((self.host, self.recvport))
        datalen, = struct.unpack('>I', s.recv(self.header_len))
        data = b''
        lencopy = datalen
        while len(data) < datalen:
            data += s.recv(datalen)
            datalen -= len(data)
        s.close()
        return pickle.loads(data) if len(data) > 0 else data, lencopy

    def getdata(self, varname, timeout=5):
        """

        @param varname:
        @param timeout:
        @return:
        """
        self.sender('ccs.data_dl({})'.format(varname))
        data, datalen = self.receiver()
        start_time = time.time()
        while (datalen == 0) and (time.time() < (start_time + timeout)):
            data, datalen = self.receiver()
            time.sleep(0.1)
        return data


if __name__ == '__main__':
    # adapter_name = "enp0s8"
    # ipv4 = os.popen('ip addr show {}'.format(adapter_name)).read().split("inet ")[1].split("/")[0]
    if len(sys.argv) >= 3:
        hostip = sys.argv[1]
        hostport = int(sys.argv[2])
        nameserv = subprocess.Popen("python -m Pyro4.naming -n {} -p {}".format(hostip, hostport), shell=True)
        daemon = Pyro4.Daemon(host=hostip)
    else:
        nameserv = subprocess.Popen("python -m Pyro4.naming", shell=True)
        daemon = Pyro4.Daemon()
    ns = Pyro4.locateNS()
    uri = daemon.register(DataReceiver)
    ns.register("DataReceiver", uri)
    daemon.requestLoop()
