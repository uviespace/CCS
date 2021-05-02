import configparser
import os
import unittest

import packets
import pus_datapool
from lib import tools


class TestingMethodsUnittests(unittest.TestCase):

    def setUp(self):
        # Read the project condiguration file
        self.cfgfile = "egse.cfg"
        self.cfg = configparser.ConfigParser()
        self.cfg.read(self.cfgfile)
        self.cfg.source = self.cfgfile

        self.poolmgr = pus_datapool.PUSDatapoolManager()

        self.ccs = packets.CCScom(self.cfg, self.poolmgr)

    ## Check if after calling the function test_get_path_for_testing_logs the directory exists
    # @param self Reference to the current instance of the class TestingMethodsUnittests
    def test_get_path_for_testing_logs(self):
        # Check if after calling the function the directory exists
        path = tools.get_path_for_testing_logs(ccs=ccs)
        self.assertTrue(os.path.isdir(path))


    def test_extract_pid_from_apid(self):
        apids_as_hex = ['0x14C', '0x141', '0x142', '0x143', '0x144', '0x3CC', '0x3C1']
        apid_as_dez = [332, 321, 322, 323, 324, 972, 961]

        self.assertEqual(tools.extract_pid_from_apid(apid_as_dez[1]), 20)
        self.assertEqual(tools.extract_pid_from_apid(apid_as_dez[2]), 20)
        self.assertEqual(tools.extract_pid_from_apid(apid_as_dez[3]), 20)
        self.assertEqual(tools.extract_pid_from_apid(apid_as_dez[4]), 20)
        self.assertEqual(tools.extract_pid_from_apid(apid_as_dez[6]), 60)





if __name__ == '__main__':
    # Verbosity: 1 for less information, 2 for detailed information
    unittest.main(verbosity=2)
