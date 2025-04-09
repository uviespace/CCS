import socket
import confignator
import sys
sys.path.append(confignator.get_option('paths', 'ccs'))
import ccs_function_lib as cfl

TM_HEADER = b'\t0\xc0\x01\x00\x12\x10\x01\x01\x00\x00\x07\xf7\x00\x00\x00\x01\x00\x01'

print("TMTC dummy server started")


TC = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
TC.bind(("localhost", 5571))

TM = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
TM.bind(("localhost", 5570))

TM.listen()
connTM, addrTM = TM.accept()
print("TM Connection:", connTM, addrTM)


TC.listen()
connTC, addrTC = TC.accept()
print("TC Connection:", connTC, addrTC)


while True:
	data = connTC.recv(5571)
	if not data:
		break
	message = data.hex()
	print("TC: " + message)
	TM_DATA = data[0:4]
	# print(TM_DATA)
	print("TM: " + TM_DATA.hex())
	CRC = b'\x00\x00'
	CRC = cfl.crc(TM_HEADER + TM_DATA).to_bytes(2,'big')
	print(CRC)
	reply = TM_HEADER + TM_DATA + CRC
	connTM.sendall(reply)

print("User disconnected")
TC.close()
TM.close()
