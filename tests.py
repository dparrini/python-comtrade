import datetime as dt
import math
import os
import struct
import time
import unittest
import comtrade
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


COMTRADE_SAMPLE_1_DAT = "1, 0, 0,0\n2,347,-1,1\n"


COMTRADE_SAMPLE_3_CFG = """STATION_NAME,EQUIPMENT,2013
2,1A,1D
1, Signal,,,A,1,0,0,-1,1,1,1,S
1, Status,,,0
60
0
0,{samples}
01/01/2019,00:00:00.000000000
01/01/2019,00:00:{seconds:012.9f}
{format}
1
"""


class TestCfg1Reading(unittest.TestCase):
    """String CFG and DAT 1999 pair test case."""
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)

    def test_station(self):
        self.assertEqual(self.comtrade.station_name, "STATION_NAME")

    def test_rec_dev_id(self):
        self.assertEqual(self.comtrade.rec_dev_id, "EQUIPMENT")

    def test_rev_year(self):
        self.assertEqual(self.comtrade.rev_year, "2001")

    def test_1a(self):
        self.assertEqual(self.comtrade.analog_count, 1)

    def test_1d(self):
        self.assertEqual(self.comtrade.status_count, 1)

    def test_2c(self):
        self.assertEqual(self.comtrade.channels_count, 2)

    def test_frequency(self):
        self.assertEqual(float(self.comtrade.frequency), 60.0)

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples, 2)

    def test_timestamp(self):
        self.assertEqual(self.comtrade.start_timestamp, 
                         dt.datetime(2000, 1, 1, 10, 30, 0, 228000, None))

        self.assertEqual(self.comtrade.trigger_timestamp, 
                         dt.datetime(2000, 1, 1, 10, 30, 0, 722000, None))

    def test_time_base(self):
        self.assertEqual(self.comtrade.time_base, 
                         self.comtrade.cfg.TIME_BASE_MICROSEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")


class TestCffReading(unittest.TestCase):
    """CFF 2013 file test case."""
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("sample_files/sample_ascii.cff")

    def test_station(self):
        self.assertEqual(self.comtrade.station_name, "SMARTSTATION")

    def test_rec_dev_id(self):
        self.assertEqual(self.comtrade.rec_dev_id, "IED123")

    def test_rev_year(self):
        self.assertEqual(self.comtrade.rev_year, "2013")

    def test_1a(self):
        self.assertEqual(self.comtrade.analog_count, 4)

    def test_1d(self):
        self.assertEqual(self.comtrade.status_count, 4)

    def test_2c(self):
        self.assertEqual(self.comtrade.channels_count, 8)

    def test_frequency(self):
        self.assertEqual(float(self.comtrade.frequency), 60.0)

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples, 40)

    def test_time_base(self):
        self.assertEqual(self.comtrade.time_base, 
            self.comtrade.cfg.TIME_BASE_MICROSEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")

    def test_hdr(self):
        self.assertIsNone(self.comtrade.hdr)

    def test_inf(self):
        self.assertIsNone(self.comtrade.inf)


class TestCfg2Reading(TestCffReading):
    """CFG and DAT 2013 file pair test case (same content as the CFF test).
    """
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("sample_files/sample_ascii.cfg")

    def test_hdr(self):
        self.assertIsNone(self.comtrade.hdr)

    def test_inf(self):
        self.assertIsNone(self.comtrade.inf)


class TestBinaryReading(unittest.TestCase):
    dat_format = comtrade.TYPE_BINARY
    filename = "temp_binary"

    def parseAnalog(self, analog_value):
        return int(analog_value)

    def getFormat(self):
        return 'Lf h H'

    def setUp(self):
        # Sample auto-generated Comtrade file.
        timebase = 1e+6 # seconds to microseconds
        timemult = 1
        max_time = 2
        self.samples = 10000
        sample_freq = max_time / self.samples
        # Create temporary cfg file.
        cfg_contents = COMTRADE_SAMPLE_3_CFG.format(samples=self.samples,
                                                    seconds=max_time,
                                                    format=self.dat_format)
        with open("sample_files/{}.cfg".format(self.filename), 'w') as file:
            file.write(cfg_contents)

        # Struct object to write data.
        datawriter = struct.Struct(self.getFormat())

        # Create temporary binary dat file, with one analog and one status
        # channel.
        max_time = 2.0

        def analog(t: float) -> float:
            return math.cos(2*math.pi*60*t)*100

        def status(t: float) -> bool:
            return t > max_time/2.0 and 1 or 0

        with open("sample_files/{}.dat".format(self.filename), 'wb') as file:
            for isample in range(0, self.samples):
                t = isample * sample_freq
                t_us = t * timebase * timemult
                y_analog = self.parseAnalog(analog(t))
                y_status = status(t)
                file.write(datawriter.pack(isample +1, t_us, y_analog, y_status))

        # Load file.
        # start = time.time()
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("sample_files/{}.cfg".format(self.filename))
        # print("In {:.5f}s".format(time.time() - start))

    def tearDown(self):
        # Remove temporary files.
        os.remove("sample_files/{}.cfg".format(self.filename))
        os.remove("sample_files/{}.dat".format(self.filename))

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples,   self.samples)
        self.assertEqual(len(self.comtrade.analog[0]),  self.samples)
        self.assertEqual(len(self.comtrade.status[0]), self.samples)
        self.assertEqual(len(self.comtrade.time),       self.samples)

    def test_analog_channels(self):
        self.assertEqual(self.comtrade.analog_count, 1)
        self.assertEqual(len(self.comtrade.analog), 1)

    def test_status_channels(self):
        self.assertEqual(self.comtrade.status_count, 1)
        self.assertEqual(len(self.comtrade.status), 1)

    def test_max_analog_value(self):
        tolerance = 2
        self.assertLessEqual(100 - max(self.comtrade.analog[0]), 2)

    def test_last_status_value(self):
        self.assertEqual(self.comtrade.status[0][-1], 1)

    def test_timestamps(self):
        self.assertEqual(self.comtrade.start_timestamp, 
                         dt.datetime(2019, 1, 1, 0, 0, 0, 0, None))
        self.assertEqual(self.comtrade.trigger_timestamp, 
                         dt.datetime(2019, 1, 1, 0, 0, 2, 0, None))

    def test_time_base(self):
        self.assertEqual(self.comtrade.time_base, 
            self.comtrade.cfg.TIME_BASE_NANOSEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, self.dat_format)


class TestBinary32Reading(TestBinaryReading):
    dat_format = comtrade.TYPE_BINARY32
    filename = "temp_binary32"

    def parseAnalog(self, analog_value):
        return int(analog_value)

    def getFormat(self):
        return 'Lf l H'


class TestFloat32Reading(TestBinaryReading):
    dat_format = comtrade.TYPE_FLOAT32
    filename = "temp_float32"

    def parseAnalog(self, analog_value):
        return int(analog_value)

    def getFormat(self):
        return 'Lf f H'


if __name__ == "__main__":
    unittest.main()
