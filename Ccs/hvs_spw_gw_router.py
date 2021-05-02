#!/usr/bin/env python3

"""
Routing packets from and to HVS SpW gateway
"""

import sys
from ccs_function_lib import setup_gw_spw_routing

if __name__ == "__main__":

    if len(sys.argv) < 4:
        print("USAGE: ./hvs_spw_gw_router.py <GW host:port> <TM host:port> <TC host:port> [-spwhead <HEX> (default FE020000)]")
        sys.exit()

    if "-spwhead" in sys.argv:
        sys.argv.remove("-spwhead")
        gw, tm, tc, spwhead = sys.argv[1:]
        spwhead = bytes.fromhex(spwhead)
    else:
        gw, tm, tc = sys.argv[1:]
        spwhead = b'\xfe\x02\x00\x00'

    gw_hp = (gw.split(":")[0], int(gw.split(":")[1]))
    tm_hp = (tm.split(":")[0], int(tm.split(":")[1]))
    tc_hp = (tc.split(":")[0], int(tc.split(":")[1]))

    print("Routing between GW:{} and TM:{},TC:{}. Adding/removing header {}".format(gw, tm, tc, spwhead.hex().upper()))
    setup_gw_spw_routing(gw_hp, tm_hp, tc_hp, spw_head=spwhead)
