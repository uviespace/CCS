import os
import json
import struct
import threading
import subprocess
import time
import sys
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import DBus_Basic

import ccs_function_lib as cfl

from typing import NamedTuple
import confignator
import gi

import matplotlib
matplotlib.use('Gtk3Cairo')


# from sqlalchemy.sql.expression import func, distinct
from sqlalchemy.orm import load_only
from database.tm_db import DbTelemetryPool, DbTelemetry, RMapTelemetry, FEEDataTelemetry, scoped_session_maker

import importlib
from confignator import config
check_cfg = config.get_config(file_path=confignator.get_option('config-files', 'ccs'))


def type_comparison(comparison_data):
    pool_rows = cfl.get_pool_rows("PLM")

    st_list = []
    sst_list = []
    x = 0
    header_counter = 0
    while header_counter < 2:
        x += 1
        entry = pool_rows.all()[-x]

        if entry.data.hex() == comparison_data:

            st_list.append(entry.stc)
            sst_list.append(entry.sst)

            # print("ST Entry_" + str(x) + ": ", entry.stc)
            # print("SST Entry_" + str(x) + ": ", entry.sst)
            # print("Timestamp entry_" + str(x) + ": ", entry.timestamp)
            header_counter += 1


    st_list_reverse = [st_list[1], st_list[0]]
    sst_list_reverse = [sst_list[1], sst_list[0]]


    if sst_list_reverse == [1, 7]:
        print("Verification successful")
    else:
        print("Verification unsuccessful")

    return False



verification_running = True

print("RUNNING!!")


while verification_running == True:

    # while running the script checks the last three entries of the database and keeps them up to date
    # to recognize a tc it checks the time

    pool_rows = cfl.get_pool_rows("PLM")

    system_time = time.clock_gettime(0)

    entry_1_data = pool_rows.all()[-1]
    # entry_2_data = pool_rows.all()[-2]
    # entry_3_data = pool_rows.all()[-3]

    time_1 = entry_1_data.timestamp
    # time_2 = entry_2_data.timestamp
    # time_3 = entry_3_data.timestamp

    # in this script the number 1 after a variable name always refers to data from the last entry
    # number 2 refers to second last entry, number 3 to third last entry and so on
    # this part triggers as soon as a tc has arrived in the database

    if time_1 == "":

        first_raw_digits = ""           # this string will contain the first bytes of raw data

        telecommand = entry_1_data
        telecommand_time = telecommand.timestamp
        telecommand_raw = telecommand.raw.hex()
        # telecommand_data = telecommand.data.hex()
        # Variable to generate new telecommand timestamp, other than telecommand_time
        telecommand_verification_timestamp = time.clock_gettime(0)
        verification_time = telecommand_verification_timestamp + 2

        for i in telecommand_raw:
            first_raw_digits += str(i)
            if len(first_raw_digits) > 7:
                break

        # print("After Loop telecommand_first_digits: ", first_raw_digits)


        while system_time < verification_time and system_time != verification_time:
            system_time = time.clock_gettime(0)

            if system_time >= verification_time:

                verification_running = type_comparison(first_raw_digits)













