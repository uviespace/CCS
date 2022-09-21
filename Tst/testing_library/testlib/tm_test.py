import tm
import ccs_function_lib as cfl
import confignator
import matplotlib
matplotlib.use('Gtk3Cairo')
from confignator import config
check_cfg = config.get_config(file_path=confignator.get_option('config-files', 'ccs'))
import inspect


telemetry = cfl.get_pool_rows("PLM")
telemetry_packet_1_1 = cfl.get_pool_rows("PLM")[0].data
telemetry_packet_1 = cfl.get_pool_rows("PLM")[0].raw
telemetry_packet_2 = cfl.get_pool_rows("PLM")[1].raw
telemetry_packet_3 = cfl.get_pool_rows("PLM")[-7]

# print(telemetry_packet_3.timestamp)
# print(telemetry_packet_3.stc)


list_of_tm_packets = [telemetry_packet_1, telemetry_packet_2]


# decode_list = tm.decode_single_tm_packet(telemetry_packet_3)[1][0]

# print(tm.get_tm_data_entries(telemetry_packet_3, "EvtId"))


# print(type(len(telemetry_packet_1)))

timestamp = cfl.get_cuctime(telemetry_packet_1)
# test = tm.get_tm_data_entries(telemetry_packet_1, "EvtId")
# print(test)
timestamp_test = tm.highest_cuc_timestamp(list_of_tm_packets)

"""
test_1 = cfl.get_header_parameters_detailed(telemetry_packet_1)
test_2 = cfl.get_header_parameters_detailed(telemetry_packet_2)


print(test_1)
print(test_2)
"""

# y = tm.get_tc_acknow(pool_name='PLM', t_tc_sent=60.0, tc_apid=321, tc_ssc=9, tm_st=3, tm_sst=1)
# print(y)
x = tm.get_5_1_tc_acknow(pool_name='PLM', t_tc_sent=82.0, tc_apid=321, tc_ssc=1, tm_st=5, tm_sst=None)
print(x[0][0][1])
# read = cfl.Tmread(x[0][0][1])
# print(read)
# for i in x:
    # print(i[0][1].hex())
    # print(i)
    # print(tm.get_tm_data_entries(i, "EvtId"))
    # tm.decode_single_tm_packet(i)

# get_list_from_d b = tm.fetch_packets(pool_name="PLM", is_tm=True, st=None, sst=None, apid=None, ssc=None, t_from=0., t_to=1401.,
#                  dest_id=None, not_apid=None, decode=False, silent=False)


# test = tm.get_tc_acknow(pool_name="PLM", t_tc_sent=1980., tc_apid=321, tc_ssc=1, tm_st=1, tm_sst=1)
# test = tm.get_5_1_tc_acknow(pool_name='PLM', t_tc_sent=0., tc_apid=321, tc_ssc=0, tm_st=5, tm_sst=1)

# print(test)
# print(test[0])
# print(test[1][0][0][0].CTIME + (test[1][0][0][0].FTIME/1000000))


# print(tm.get_tc_acknow.__globals__["get_tc_acknow"])

# print(inspect.signature(tm.get_tc_acknow))



# identified_tc = tm.get_tc_identifier(pool_name="PLM",tc_apid=321,tc_ssc=1, tc_time=100)



# acknowledgement = tm.await_tc_acknow(pool_name="PLM", tc_identifier=identified_tc, duration=10, tm_st=1, tm_sst=7)


# print(acknowledgement[1][0][0][0].CTIME + (acknowledgement[1][0][0][0].FTIME/1000000))







"""
# fetch funktion, demonstration von .CTIME und FTIME

test = tm.fetch_packets(pool_name="PLM", is_tm=True, st=3, sst=25, apid=321, ssc=None, t_from=0.00, t_to=21.0,
                  dest_id=None, not_apid=None, decode=True, silent=False)


# print(test)
# print(test[0][0][1])
# print("Test: ", test[0][0][1])
header = test[0][0][0]
# print(header.CTIME)
# print(header.FTIME)

print(header.CTIME + (header.FTIME/1000000))

test_liste = []

for i in test:
    test_liste.append(i[0][0])

print(len(test_liste))
print(test_liste)

"""




