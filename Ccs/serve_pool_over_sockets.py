#!/usr/bin/env python3
import socket
import sys
import os
from pus_datapool import DatapoolManager
import configparser

def main():

    if len(sys.argv) == 3:
        PORT = int(sys.argv[2])

        sys.argv = sys.argv[0:2]
        wait_time = 0.5
    elif len(sys.argv) == 4:
        PORT = int(sys.argv[2])
        wait_time = float (sys.argv[3])
        sys.argv = sys.argv[0:2]
    else:
        PORT = 5570
        wait_time = 0.5

    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "somePoolFile")
        sys.exit(1)


    cfgfile = 'ccs_main_config.cfg'
    cfg = configparser.ConfigParser()
    cfg.read(cfgfile)
    cfg.source = cfgfile

    poolmgr = DatapoolManager(cfg)
    with open(sys.argv[1], 'rb') as fdesc:
        data = poolmgr.extract_pus(fdesc.read())
        # data is now a list of individual TM/TC packets

    #with open(sys.argv[1], 'rb') as fdesc:
    #    data = fdesc.read()
    # for the TM channel (change the port as needed)
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


    s.bind(('', PORT))
    print("Listening for incoming connection on port", PORT)
    s.listen()
    tmport, addr = s.accept()
    print("Incoming connection:", tmport, addr)

    #tmport.send(data)

    '''
    def serializeLengthLE(n):
        res = bytearray()
        for _ in range(4):
            res.append(n & 255)
            n >>= 8
        return res
    '''
    idx = 0

    import time
    for idx, pckt in enumerate(data):
        #print(idx, pckt)
        #tmport.send(serializeLengthLE(len(pckt)))
        tmport.send(pckt)
        time.sleep(wait_time)

    print("Sent", idx, "packets. Closing socket...")

if __name__ == "__main__":
    main()
