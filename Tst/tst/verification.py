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
# import tm


# test = tm.get_tc_acknow(pool_name="PLM", t_tc_sent=1020., tc_apid=321, tc_ssc=1, tm_st=1, tm_sst=None)

"""
def verification_template(verification_descr, pool_name="LIVE", ST_1=None, ST_2=None, SST_1=None, SST_2=None, time=2,
                          comment="", preamble="Ver.verification", add_parcfg=False):

    if comment:
        commentstr = "# TC({}, {}): {} [{}]\n# {}\n".format(*cmd[3:], cmd[1], cmd[0], cmd[2])
        newline = "\n"
    else:
        commentstr = ""
        newline = ""

    parcfg = ''
    if add_parcfg:
        for par in pars:
            if par[2] == 'E':
                if par[4] is not None:
                    if par[5] == 'E':
                        parval = '"{}"'.format(par[4])
                    elif par[6] == 'H':
                        parval = '0x{}'.format(par[4])
                    else:
                        parval = par[4]
                else:
                    parval = par[4]
                line = '{} = {}  # {}\n'.format(par[0], parval, par[3])
            elif par[2] == 'F':
                line = '# {} = {}  # {} [NOT EDITABLE]\n'.format(par[0], par[4], par[3])
            else:
                line = ''
            parcfg += line

    parstr = ', '.join(parsinfo_to_str(pars))
    if len(parstr) > 0:
        parstr = ', ' + parstr


    exe = "{}('{}', ST_1={}, SST_1={}, ST_2={}, SST_2={}, pool_name='{}', time={})".format(preamble, verification_descr,
                                                                                  ST_1, SST_1, ST_2, SST_2,
                                                                                  pool_name, time)
    return commentstr + exe + newline
"""

# verification template nach Stefan
"""
def verification_template(cmd, pars, pool_name='LIVE', preamble='cfl.Tcsend_DB', options='', comment=True, add_parcfg=False):

    if comment:
        commentstr = "# TC({}, {}): {} [{}]\n# {}\n".format(*cmd[3:], cmd[1], cmd[0], cmd[2])
        newline = "\n"
    else:
        commentstr = ""
        newline = ""
    
    parcfg = ''
    if add_parcfg:
        for par in pars:
            if par[2] == 'E':
                if par[4] is not None:
                    if par[5] == 'E':
                        parval = '"{}"'.format(par[4])
                    elif par[6] == 'H':
                        parval = '0x{}'.format(par[4])
                    else:
                        parval = par[4]
                else:
                    parval = par[4]
                line = '{} = {}  # {}\n'.format(par[0], parval, par[3])
            elif par[2] == 'F':
                line = '# {} = {}  # {} [NOT EDITABLE]\n'.format(par[0], par[4], par[3])
            else:
                line = ''
            parcfg += line

    parstr = ', '.join(parsinfo_to_str(pars))
    if len(parstr) > 0:
        parstr = ', ' + parstr
    
    
    exe = "{}('{}'{}, pool_name='{}'{})".format(preamble, cmd[1], parstr, pool_name, options)
    return commentstr + parcfg + exe + newline
    
"""










































"""

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

"""
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

















































"""

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



"""



