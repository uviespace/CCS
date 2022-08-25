#!/usr/bin/env python3
import logging

import confignator
cfg = confignator.get_config()

from testlib import analyse_command_log

from testlib import tm
from testlib import tools

import pus_datapool
import packets
import poolview_sql
import tst_logger

# create a logger
logger = logging.getLogger(__name__)
tst_logger.set_level(logger=logger)
tst_logger.create_console_handler(logger=logger)
tst_logger.create_file_handler(logger=logger)

example_pool_file = '../example/IASW_777.tmpool'

pm = pus_datapool.PUSDatapoolManager(cfg=cfg)
ccs = packets.CCScom(cfg=cfg, poolmgr=pm)

# load the tmpool file into the database
tpv = poolview_sql.TMPoolView(cfg=cfg)
tpv.set_ccs(ccs=ccs)
tpv.load_pool(filename=example_pool_file)

pool_name = tpv.active_pool_info.filename
# get all TC from the database
packets = tm.fetch_packets(ccs=ccs, pool_name=pool_name, is_tm=False)


def get_tc_acknow(ccs, pool_name, tc_apid, tc_ssc, tc_st, tc_sst, tm_st=1, tm_sst=None):
    """
    Check if for the TC acknowledgement packets can be found in the database.
    This function makes a single database query.
    :param packets.CCScom ccs: instance of the class packets.CCScom
    :param str pool_name:  Name of the TM pool in the database
    :param float t_tc_sent: CUC timestamp of the telecommand
    :param int or str tc_apid: Application process ID of the sent TC. Can be provided as integer or hexadecimal string
    :param int tc_ssc:  Source sequence counter of the sent TC
    :return: (boolean, list)

        * boolean:

             * True if one or up to all acknowledgement packets TM(1,1), TM(1,3), TM(1,7) were found
             * False if one or all of TM(1,2), TM(1,4), TM(1,8) were found

        * list:

            * List of the acknowledgement TM packets for the TC,
            * [] if no acknowledgement TM packets could be found in the database

    :rtype (boolean , list)
    """
    result = None
    assert isinstance(pool_name, str)
    assert isinstance(tc_apid, int) or isinstance(tc_apid, str)

    # if the tc_apid is provided as hexadecimal number, convert it to and integer
    tc_apid = tools.convert_apid_to_int(apid=tc_apid)

    # make database query
    packets = tm.fetch_packets(ccs=ccs, pool_name=pool_name, st=tm_st, sst=tm_sst)

    # filter for TM packets with the correct APID and source sequence counter (SSC) in the data field
    ack_tms = []
    for i in range(len(packets)):
        if packets[i][1] is not None and packets[i][1][0] is not None:
            # get the data entries for APID and SSC
            pac_apid = packets[i][0][3]
            if pac_apid == 961:  # for acknowledgements from SEM
                name_apid = 'PAR_CMD_APID'
                name_psc = 'PAR_CMD_SEQUENCE_COUNT'
            else:
                name_apid = 'TcPacketId'
                name_psc = 'TcPacketSeqCtrl'
            para = tm.get_tm_data_entries(ccs=ccs, tm_packet=packets[i], data_entry_names=[name_apid, name_psc])
            if name_apid in para and name_psc in para:
                # extract the SSC from the PSC
                ssc = tm.extract_ssc_from_psc(psc=para[name_psc])
                apid = tm.extract_apid_from_packetid(packet_id=para[name_apid])
                if pac_apid == 961:  # acknowledgement packets from SEM have the PID in the field 'PAR_CMD_APID'
                    tc_pid = tools.extract_pid_from_apid(tc_apid)
                    if apid == tc_pid and ssc == tc_ssc:
                        ack_tms.append(packets[i])
                else:
                    if apid == tc_apid and ssc == tc_ssc:
                        ack_tms.append(packets[i])
        else:
            logger.debug('get_tc_acknow: could not read the data from the TM packet')

    # treat with the result from the database query
    if len(ack_tms) > 0:
        logger.info('Received acknowledgement TM packets for TC({},{}) apid={} ssc={}:'
                 .format(tc_st, tc_sst, tc_apid, tc_ssc))

        # check if there was a failure, the result becomes False if a failure occurred
        for i in range(len(ack_tms)):
            head = ack_tms[i][0]
            data = ack_tms[i][1]
            if result is not False:
                if head[11] == 1 or head[11] == 3 or head[11] == 7:
                    logger.info('TM({},{}) @ {}'.format(head[10], head[11], ccs.get_cuctime(head)))
                    result = True
                if head[11] == 2 or head[11] == 4 or head[11] == 8:
                    if head[11] == 2:
                        logger.info('TM({},{}) @ {} FAILURE: Acknowledge failure of acceptance check for a command.'
                                 .format(head[10], head[11], ccs.get_cuctime(head)))
                        logger.debug('Data of the TM packet: {}'.format(data))
                    if head[11] == 4:
                        logger.info('TM({},{}) @ {} FAILURE: Acknowledge failure of start check for a command.'
                                 .format(head[10], head[11], ccs.get_cuctime(head)))
                        logger.debug('Data of the TM packet: {}'.format(data))
                    if head[11] == 8:
                        logger.info(
                            'TM({},{}) @ {} FAILURE: Acknowledge failure of termination check for a command.'
                            .format(head[10], head[11], ccs.get_cuctime(head)))
                        logger.debug('Data of the TM packet: {}'.format(data))
                    result = False

    return result, ack_tms


tc_and_acks = []
for tc_packet in packets:
    apid = tc_packet[0][3]
    ssc = tc_packet[0][5]
    st = tc_packet[0][10]
    sst = tc_packet[0][11]
    tc_id = analyse_command_log.TcId(apid=apid, ssc=ssc, st=st, sst=sst)
    tm_1s = get_tc_acknow(ccs=ccs, pool_name=pool_name, tc_apid=apid, tc_ssc=ssc, tc_st=st, tc_sst=sst, tm_st=1, tm_sst=None)
    acks = []
    if len(tm_1s) > 0:
        for item in tm_1s[1]:
            acks.append(item)
    tc_and_acks.append((tc_packet, acks))


def print_tc_and_acks(tc_and_acks):
    for combi in tc_and_acks:
        print('TC:')
        print(combi[0])
        print('Acknowledgements:')
        for item in combi[1]:
            print(item)


print_tc_and_acks(tc_and_acks=tc_and_acks)
