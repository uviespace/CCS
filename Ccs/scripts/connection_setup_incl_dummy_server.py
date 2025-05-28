import threading
import socket

def run_server():
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
            
            bits = "".join([bin(b)[2:].zfill(8) for b in data])
            vn = int(bits[0:3], 2)
            typ = int(bits[3:4], 2)
            dfhf = int(bits[4:5], 2)
            apid = int(bits[5:16], 2)
            sf = int(bits[16:18], 2)
            sc = int(bits[18:32], 2)
            pkt_len = int(bits[32:48], 2)
            pus_ver = int(bits[48:52], 2)
            ack = int(bits[52:56], 2)
            st = int(bits[56:64], 2)
            sst = int(bits[64:72], 2)
            sdid = int(bits[72:88], 2)

            tm_data = data[:4]

            tm = cfl.Tmpack(vn=vn, typ=0, dfhf=dfhf, apid=apid, sc=sc, data=tm_data)
            #crc = cfl.crc(tm).to_bytes(2, 'big')

            print(f"[INFO] Calculated CRC: {crc.hex()}")

            reply = tm #+ crc
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
