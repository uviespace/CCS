import threading
import socket

def run_server():
    TM_HEADER = b'\t0\xc0\x01\x00\x12\x10\x01\x01\x00\x00\x07\xf7\x00\x00\x00\x01\x00\x01'
    print("=== TMTC Dummy Server Started ===")

    # Set up TC and TM sockets
    TC = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    TC.bind(("localhost", 5571))
    TM = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    TM.bind(("localhost", 5570))

    TM.listen()
    print("[INFO] Waiting for TM connection on port 5570...")
    connTM, addrTM = TM.accept()
    print(f"[CONNECTED] TM Client: {addrTM}")

    TC.listen()
    print("[INFO] Waiting for TC connection on port 5571...")
    connTC, addrTC = TC.accept()
    print(f"[CONNECTED] TC Client: {addrTC}")

    try:
        while True:
            data = connTC.recv(5571)
            if not data:
                print("[INFO] No data received. Closing connections.")
                break
            
            
            message_hex = data.hex()
            #message_bin = [int(single_bytes, 2) for single_bytes in data]
            print(f"\n[RECEIVED] TC Packet (hex): {message_hex}")
            #print(f"\n[RECEIVED] TC Packet (hex): {message_bin}")
            
            #apid = message_bin[2+5:2+5+11]
            #print(apid, int(apid,2))

            TM_DATA = data[0:4]
            print(f"[INFO] Extracted TM Data (hex): {TM_DATA.hex()}")

            CRC = cfl.crc(TM_HEADER + TM_DATA).to_bytes(2, 'big')
            print(f"[INFO] Calculated CRC: {CRC.hex()}")

            reply = TM_HEADER + TM_DATA + CRC
            # reply = cfl.Tmpack(st=1, sst=1, apid=int(apid), data=b'', ack=0)
            print(f"[SENT] TM Packet (hex): {reply.hex()}")
            connTM.sendall(reply)

    except Exception as e:
        print(f"[ERROR] Exception in server loop: {e}")
        raise e

    finally:
        print("[INFO] User disconnected. Closing sockets.")
        TC.close()
        TM.close()

# Start the server in a background thread
threading.Thread(target=run_server, daemon=True).start()

### Poolmanager ###
cfl.start_pmgr()

# PLM connection
cfl.connect('LIVE', '', 5570, protocol='PUS')
cfl.connect_tc('LIVE', '', 5571, protocol='PUS')

### Poolviewer ###
cfl.start_pv()

#! CCS.BREAKPOINT
### Monitor ###
cfl.start_monitor('LIVE')
