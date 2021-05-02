#!/usr/bin/env python3

import argparse
import configparser
import time

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import pus_datapool
import packets
import poolview_sql

parser = argparse.ArgumentParser(description='Plot HK data from saved TM pool')
parser.add_argument('pool_file', metavar='FILENAME', type=str)
parser.add_argument('parameters', metavar='HK', type=str, nargs='+')
parser.add_argument('--export', metavar='FILE', help='Save data to file')
parser.add_argument('--noplot', help='Only extract and save HK data to file', const=True, nargs='?')
args = parser.parse_args()

pool_file = args.pool_file
parameter_input = args.parameters
parameters = {p.split(':')[0]: p.split(':')[1].split(',') for p in parameter_input}
print('\nPlotting: ', parameters)
cfgfile = 'egse.cfg'
cfg = configparser.ConfigParser()
cfg.read(cfgfile)
cfg.source = cfgfile

poolmgr = pus_datapool.PUSDatapoolManager(cfg)
ccs = packets.CCScom(cfg, poolmgr)

pv = poolview_sql.TMPoolView(cfg=cfg, ccs=ccs)
pv.load_pool(filename=pool_file)

if hasattr(pv, '_loader_thread'):
    while pv._loader_thread.isAlive():
        time.sleep(0.5)

plv = poolview_sql.PlotViewer(parent=None, loaded_pool=pv.active_pool_info, cfg=cfg, poolmgr=poolmgr, ccs=ccs,
                              parameters=parameters)

if args.export:
    plv.save_plot_data(filename=args.export)
    print('\n >>> Data saved as "{}"'.format(args.export))

if args.noplot is None:
    plv.connect("delete-event", Gtk.main_quit)
    plv.show_all()
    Gtk.main()
