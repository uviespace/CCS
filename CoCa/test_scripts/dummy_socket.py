# dummy script to start a socket server
#
# it will create two ports and will print out the binary comands received
# the ports are the same as in the standard connection_setup.py
# the sockets are TCP

import socket
import threading


# Function to handle incoming data on socket
def handle_client(client_socket):
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            print(f"Received message: {data}")
    finally:
        client_socket.close()


# Function to start listening on the socket
def listen_on_socket(sock):
    while True:
        client_sock, addr = sock.accept()
        print(f"Accepted connection from {addr}")
        client_handler = threading.Thread(target=handle_client, args=(client_sock,))
        client_handler.start()


# Create two sockets
socket_tm = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socket_tc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Avoid bind() exception: OSError: [Errno 48] Address already in use
socket_tm.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
socket_tc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Bind the sockets to addresses and ports
socket_tm.bind(('localhost', 5570))
socket_tc.bind(('localhost', 5571))

# Listen on the sockets
socket_tm.listen(5)
socket_tc.listen(5)

# Print info
print("Socket tm listening on localhost:5570")
print("Socket tc listening on localhost:5571")

# Create two threads for handling sockets
thread1 = threading.Thread(target=listen_on_socket, args=(socket_tm,))
thread2 = threading.Thread(target=listen_on_socket, args=(socket_tc,))

# Start the threads
thread1.start()
thread2.start()

# You can now use a TCP client to connect to these sockets and send messages.
