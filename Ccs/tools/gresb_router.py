#!/usr/bin/env python3

"""
Handle packets prepended with GRESB header
"""

import sys
sys.path.insert(0, '..')

from ccs_function_lib import setup_gresb_routing

if __name__ == "__main__":

    if len(sys.argv) < 3:
        print("USAGE: ./gresb_router.py <GRESB host:port> <TM host:port> [<TC host:port>]")
        sys.exit()

    gw, tm = sys.argv[1:3]

    gw_hp = (gw.split(":")[0], int(gw.split(":")[1]))
    tm_hp = (tm.split(":")[0], int(tm.split(":")[1]))

    if len(sys.argv) == 4:
        tc = sys.argv[3]
        tc_hp = (tc.split(":")[0], int(tc.split(":")[1]))
    else:
        tc = None
        tc_hp = None

    print("Routing between GRESB:{} and TM:{},TC:{}. Adding/removing 4-byte GRESB header".format(gw, tm, tc))
    setup_gresb_routing(gw_hp, tm_hp, tc_hp=tc_hp)
