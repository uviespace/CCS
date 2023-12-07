"""
Examples for Athena WFI DE communications
"""

import communication as com
import packet_config_ATHENA_DE as de

# set up socket and connect
decon = com.Connector('', 12345, msgdecoding='hex')
decon.connect()

# example commands
# test echo interface (0x20)
decon.send(b'\x20\xDE\xAD')

# HK interface 0x33
decon.send(de.HkCmdRead(0x1000))  # get PCM MODE register
decon.send(de.HkCmdWrite(0x1000, 0x0001))  # set PCM MODE register

# CMD interface 0x34
decon.send(de.CmdWrite(0x3C00, 0x0001))  # write sequencer register
decon.send(de.CmdWrite(0x3C00, 1), rx=False)  # write sequencer register, but don't fetch cmd response from socket
decon.send(de.CmdRead(0x3C00))  # read sequencer register

# SCI interface 0x35
decon.send(de.SciCmd(100))  # set science data output rate

# dump cmd log (decon.log)
logfile = '/path/to/de_cmd.log'
decon.dump_log(logfile)

# automatically log to file
decon.setup_storage(logfile)

# run rx thread on socket, received data is put in recvd_data_buf queue
decon.start_receiver()
decon.receiver.recvd_data_buf


# custom TM processing function; must take bytestring as arg *data*, and timestamp kwarg *ts*
def msg_to_hex_string(data, ts=''):
    try:
        return '{}: {}\n'.format(ts, data.hex(' ', 1))
    except Exception as err:
        print(err)
        return '# ERROR #\n'


# optionally, add custom TM processing
# this logs the received data hex-formatted in outfile
decon.start_receiver(procfunc=msg_to_hex_string, outfile='/path/to/de_rx.log', ofmode='w')

# processed data is also collected in
decon.receiver.proc_data

