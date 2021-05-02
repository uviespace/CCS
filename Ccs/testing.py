import pus_datapool
import poolview
import packets
import importlib
import monitor
import tcgui
import numpy as np
import configparser

cfg = configparser.ConfigParser()
cfg.read()

poolmgr = pus_datapool.PUSDatapoolManager()
ccs = packets.CCScom(cfg,poolmgr)

importlib.reload(monitor)

tc = tcgui.TcGui(cfg,ccs)

import matplotlib.pyplot as plt
plt.ion()
buf=ccs.collect_13('fullframeS13.tmpool',starttime=0,endtime=25000,join=True)
arr=np.frombuffer(b'\x00\x00'+buf.strip(b'\x00'),'>u4')
plt.imshow(arr.reshape(1076,-1))

mv = monitor.ParameterMonitor(ccs=ccs,cfg=cfg,pool_name='IASW-15.tmpool',parameter_set='default')

ex=poolmgr.extract_pus(d)



poolmgr.connect('TM','',12345)

pool='/home/mess/mecina/cheops/testpools/DBS-2.tmpool'

ppp=[["DPT06030", "DPT06031", "DPT06032", "DPT06033"], ["DPT06036"], ["DPT06045", "DPT06046", "DPT06047", "DPT06048", "DPT06049"]]

pckts=poolmgr.datapool['DBS-7.tmpool']['pckts']
tm6=pckts[139]
tm197=pckts[60]
tm1=pckts[166]

ccs.Tmdata(tm1)
ccs.Tmdata(tm6)
ccs.Tmdata(tm197)


tmlist = ccs.poolmgr.datapool['TM']['pckts'].values()

poolmgr = pus_datapool.PUSDatapoolManager()
poolmgr.create('TM')
poolmgr.load_pckts('IASW-103',pool)
pv = poolview.TMPoolView(cfg)
pv.set_ccs(ccs)
pv.add_colour_filter({'APID': 322, 'colour' : 'blue'})
pv.add_colour_filter({'SST' : 25,  'colour' : 'green'})
pv.add_colour_filter({'TM/TC':'TC','colour':'red'})
pvqueue = poolmgr.register_queue('TM')
pv.set_queue(*pvqueue)
pv.set_pool(poolmgr)
pv.show_all()

d,dd=ccs.collect_21_3('IASW-103')

import glob
dd={}
#n=[1,2,3,4,5,7,8,9,100,101,103]
pools=glob.glob('/home/mess/mecina/cheops/IFSW/acceptance_tests/09minusTests/**/*.tmpool',recursive=True)
pools.sort()
for pool in pools:
	#pool='/home/mess/mecina/cheops/testpools/IASW-{:d}.tmpool'.format(i)
	pname=pool.split('/')[-1]
	poolmgr.create(pname)
	poolmgr.load_pckts(pname,pool)
	pckts=poolmgr.datapool[pname]['pckts'].values()
	dd[pname]=ccs.Tm_filter_st(pckts,13,2)

d = open('/home/mess/mecina/cheops/testpools/IASW-103.tmpool','rb').read()

data = io.BufferedReader(io.BytesIO(d))

import threading
thread=threading.Thread(target=ccs.srec_direct,kwargs={'fname':'/home/mess/mecina/cheops/srec_test/ifswOK.srec','tcsend':'TC'})
thread.start()
ccs.srec_direct('/home/mess/mecina/cheops/srec_test/ifswOK.srec',tcsend='TC')

def peektest(data):
	pckts = []
	while 1:
		pus_size = data.peek(10)
		if len(pus_size) == 0:
			print(data.tell())
			break
		pckt_size = pus_size[6]
		pckts.append(data.read(pckt_size))
	return pckts

def seektest(data):
	pckts = []
	while True:
		mark=data.tell()
		pus_size = data.read(6)
		data.seek(mark)
		if len(pus_size) < 7:
			print(data.tell())
			break
		pckt_size = pus_size[6]
		pckts.append(data.read(pckt_size))
	return pckts