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


def type_comparison(comparison_data, sst_1=1, sst_2=7, st_=1, st_2=1,):
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


    if sst_list_reverse == [sst_1, sst_2]:
        print("Verification successful")
    else:
        print("Verification unsuccessful")

    return False


def Verification( st_1=1, sst_1=1, st_2=1, sst_2=7, pool_name="PLM", verification_duration=2):
    verification_running = True

    print("RUNNING!!")

    print("Variables: ")
    print(st_1)
    print(sst_1)
    print(st_2)
    print(sst_2)
    print(pool_name)
    print(verification_duration)


    while verification_running == True:

        # while running the script checks the last three entries of the database and keeps them up to date
        # to recognize a tc it checks the time

        pool_rows = cfl.get_pool_rows(pool_name)

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
            verification_time = telecommand_verification_timestamp + verification_duration

            for i in telecommand_raw:
                first_raw_digits += str(i)
                if len(first_raw_digits) > 7:
                    break

            # print("After Loop telecommand_first_digits: ", first_raw_digits)


            while system_time < verification_time and system_time != verification_time:
                system_time = time.clock_gettime(0)

                if system_time >= verification_time:

                    verification_running = type_comparison(first_raw_digits, sst_1, sst_2)



def verification_template(verification_descr, pool_name="LIVE", ST_1=None, ST_2=None, SST_1=None, SST_2=None, time=2,
                          comment="", preamble="Ver.verification"):
    if comment:
        commentstr = "# TC({}, {}): {} [{}]\n# {}\n".format(*cmd[3:], cmd[1], cmd[0], cmd[2])
        newline = "\n"
    else:
        commentstr = ""
        newline = ""

    exe = "{}('{}', ST_1={}, SST_1={}, ST_2={}, SST_2={}, pool_name='{}', time={})".format(preamble, verification_descr,
                                                                                  ST_1, SST_1, ST_2, SST_2,
                                                                                  pool_name, time)
    return commentstr + exe + newline


# def  new_verification_template(verification_descr, pool_name="LIVE", comment="", preamble=):


# reads in verification as soon as exec button in step widget is pressed
def read_verification(verification_string):


    first_split = verification_string.split("(")


    second_split = ""
    for i in first_split[1]:
        if i != ")":
            second_split += i


    third_split = second_split.split(",")


    st_1 = third_split[1]
    sst_1 = third_split[2]
    st_2 = third_split[3]
    sst_2 = third_split[4]
    pool_name = third_split[5]
    time_duration = third_split[6]


    st_1_value = st_1.split("=")[1]
    sst_1_value = sst_1.split("=")[1]
    st_2_value = st_2.split("=")[1]
    sst_2_value = sst_2.split("=")[1]
    pool_name_value = pool_name.split("=")[1]
    time_duration_value = time_duration.split("=")[1]

    st_sst_list = [st_1_value, sst_1_value, st_2_value, sst_2_value]



    value_list = []

    for element in st_sst_list:
        #  print(element)
        if element == "None":
            element = None
        else:
            try:
                element = int(element)
            except:
                raise AssertionError("ST and SST values have to be None or int")

        value_list.append(element)


    if type(pool_name_value) == str:
        # print("if pool name: ", pool_name_value)
        value_list.append(pool_name_value)
    else:
        raise AssertionError("Pool Name needs to be str")

    # time_duration_value_checker = isinstance(time_duration_value, int)
    # print("Time instance: ", time_duration_value_checker)
    try:
        time_duration_value = int(time_duration_value)
        value_list.append(time_duration_value)
    except:
        raise AssertionError("Time has to be int")

    Verification(value_list[0], value_list[1], value_list[2], value_list[3], value_list[4], value_list[5])






