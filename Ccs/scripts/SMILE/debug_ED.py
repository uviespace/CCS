"""
Interactively debug raw event data in downlinked frames
"""

import matplotlib.pyplot as plt
import numpy as np

from tools.dataprocessing.smile_raw_ce_converter import CompressionEntity, ED_PKT_DTYPE

plt.ion()

# get all downlinks in the currently loaded pool
s13 = cfl.collect_13(cfl._get_displayed_pool_path(), collect_all=True)

# create the CE objects
ces = {k: CompressionEntity(s13[k]) for k in s13}

# filter for the ED frames
ed_ces = {k: ces[k] for k in ces if ces[k].header.items.product == 0}

# create an array with the event packets for a specific frame
ce = ed_ces[828.104595]  # get specific frame/CE
ce.meta_group  # GROUP meta data
ce.meta_frame  # FRAME meta data
evts = np.frombuffer(ce.scidata, ED_PKT_DTYPE)

# in case of events from multiple frames in one CE, optionally filter for a single frame counter
evts = evts[evts['fc']==12]

# create empty node arrays
ff = np.zeros((4, 639, 384))

# populate the node arrays with events
for evt in evts[evts['row'] != 0]:
    ccd = (evt['dtyp'] >> 4) & 1
    n = (evt['dtyp'] >> 5) & 0b11
    ff[(ccd << 1) | n, evt['row'] - 2:evt['row'] + 3, evt['col'] - 2:evt['col'] + 3] = evt['evts'].reshape(5, 5)

# select a node and plot it
node = 0  # 0=2F,1=2E,2=4F,3=4E
plt.matshow(ff[node], origin='lower')
