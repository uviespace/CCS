import communication as com
import iwf_egse as iwf

econ = com.Connector('', iwf.PORT, msgdecoding='ascii')
econ.connect()

econ.start_receiver(procfunc=iwf.response_proc_func)

econ.send(iwf.Command.get_status(), rx=False)
