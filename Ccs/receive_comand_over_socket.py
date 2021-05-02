#!/usr/bin/env python3
import socket
import sys
import os
from pus_datapool import DatapoolManager
import confignator

def main():
    datalist = []
    datadata = None
    cfg = confignator.get_config()

    poolmgr = DatapoolManager(cfg)
    if sys.argv[1]:
        with open(sys.argv[1], 'rb') as fdesc:
            datadata = poolmgr.extract_pus(fdesc.read())

    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = ''
    port = 5590
    print(port)
    serversocket.bind((host, port))

    serversocket.listen(5)
    print('server started and listening')
    while 1:
        (clientsocket, address) = serversocket.accept()
        print("connection found!")
        data = clientsocket.recv(1024)
        print(data)
        print(type(data))
        if datadata:
            clientsocket.send(datadata[94])
        datalist.append(data)

if __name__ == "__main__":
    main()
