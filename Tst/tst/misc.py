import socket
# ToDo: get the ports from the Configuration File
ed_host = ''
ed_ul_port = 4242


def to_console_via_socket(buf):
    """ Send something to the CCS IPyhton console CCS via socket

    :param buf: what will be sent to the IPhython console of CCS
    :return: acknowledgement of the socket
    """
    editor_sock = socket.socket()
    try:
        editor_sock.connect((ed_host, ed_ul_port))
    except ConnectionRefusedError:
        print('Connection to CCS Ipython console was refused')
    editor_sock.send(buf.encode())
    ack = editor_sock.recv(1024)
    editor_sock.close()
    return ack
