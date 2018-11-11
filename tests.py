import unittest
from comtrade import Comtrade


COMTRADE_SAMPLE_1_CFG = """STATION_NAME,EQUIPMENT,2001
2,1A,1D
1, IA              ,,,A,2.762,0,0, -32768,32767,1,1,S
1, Diff Trip A     ,,,0
60
0
0,2
01/01/2000,10:30:00.228000
01/01/2000,10:30:00.722000
ASCII
1
"""

COMTRADE_SAMPLE_1_DAT ="1, 0, 0,0\n2,347,-1,1\n"


class TestCfg1Reading(unittest.TestCase):
    """String CFG and DAT 1999 pair test case."""
    def setUp(self):
        self.comtrade = Comtrade()
        self.comtrade.read(COMTRADE_SAMPLE_1_CFG.splitlines(),
            COMTRADE_SAMPLE_1_DAT.splitlines())

    def test_station(self):
        self.assertEqual(self.comtrade.station_name, "STATION_NAME")

    def test_rec_dev_id(self):
        self.assertEqual(self.comtrade.rec_dev_id, "EQUIPMENT")

    def test_rev_year(self):
        self.assertEqual(self.comtrade.rev_year, "2001")

    def test_1a(self):
        self.assertEqual(self.comtrade.analog_count, 1)

    def test_1d(self):
        self.assertEqual(self.comtrade.digital_count, 1)

    def test_2c(self):
        self.assertEqual(self.comtrade.channels_count, 2)

    def test_frequency(self):
        self.assertEqual(float(self.comtrade.frequency), 60.0)

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples, 2)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")


class TestCffReading(unittest.TestCase):
    """CFF 2013 file test case."""
    def setUp(self):
        self.comtrade = Comtrade()
        self.comtrade.load("sample_files\\sample_ascii.cff")

    def test_station(self):
        self.assertEqual(self.comtrade.station_name, "SMARTSTATION")

    def test_rec_dev_id(self):
        self.assertEqual(self.comtrade.rec_dev_id, "IED123")

    def test_rev_year(self):
        self.assertEqual(self.comtrade.rev_year, "2013")

    def test_1a(self):
        self.assertEqual(self.comtrade.analog_count, 4)

    def test_1d(self):
        self.assertEqual(self.comtrade.digital_count, 4)

    def test_2c(self):
        self.assertEqual(self.comtrade.channels_count, 8)

    def test_frequency(self):
        self.assertEqual(float(self.comtrade.frequency), 60.0)

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples, 40)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")


class TestCfg2Reading(TestCffReading):
    """CFG and DAT 2013 file pair test case (same content as the CFF test)
    """
    def setUp(self):
        self.comtrade = Comtrade()
        self.comtrade.load("sample_files\\sample_ascii.cfg")


if __name__ == "__main__":
    unittest.main()