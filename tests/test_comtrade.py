import array
import datetime as dt
import math
import os
import shutil
import struct
import tempfile
import unittest
import warnings
from unittest import mock
import comtrade
from comtrade import Comtrade


COMTRADE_SAMPLE_1_CFG = """STATION_NAME,EQUIPMENT,2001
2,1A,1D
1, IA              ,,,A,2.762,0,0, -32768,32767,1,1,S
1, Diff Trip A     ,,,0
60
0
0,2
01/01/2000, 10:30:00.228000
 01/01/2000,10:30:00.722000
ASCII
1
"""

COMTRADE_SAMPLE_1_CFG_LAZY = """,,1999
2,1A,1D
1,,,,A,2.762,0,0, -32768,32767,1,1,S
1,,,,

0
0,2
,

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

COMTRADE_SAMPLE_4_CFG_FILE = "tests/sample_files/sample_bin.cfg"
COMTRADE_SAMPLE_4_DAT_FILE = "tests/sample_files/sample_bin.dat"

# Two sample rates: 1000 Hz up to sample 4, then 500 Hz up to sample 6.
COMTRADE_SAMPLE_5_CFG = """STATION_NAME,EQUIPMENT,1999
2,1A,1D
1, IA,,,A,1,0,0,-32768,32767,1,1,S
1, Trip,,,0
60
2
1000,4
500,6
01/01/2000,10:30:00.000000
01/01/2000,10:30:00.000000
{format}
1
"""

COMTRADE_SAMPLE_5_DAT = "1,0,1,0\n2,1000,2,0\n3,2000,3,0\n4,3000,4,0\n5,5000,5,1\n6,7000,6,1\n"

# Blank (non-critical) timestamps.
COMTRADE_SAMPLE_6_CFG = """STATION_NAME,EQUIPMENT,1999
2,1A,1D
1, IA,,,A,1,0,0,-32768,32767,1,1,S
1, Trip,,,0
60
1
1000,3
01/01/2000,10:30:00.000000
01/01/2000,10:30:00.000000
ASCII
1
"""

COMTRADE_SAMPLE_6_DAT = "1,,1,0\n2,,2,0\n3,,3,1\n"

# Status channels only.
COMTRADE_SAMPLE_7_CFG = """STATION_NAME,EQUIPMENT,2013
2,0A,2D
1, Trip,,,0
2, Close,,,0
60
1
1000,3
01/01/2000,10:30:00.000000
01/01/2000,10:30:00.000000
{format}
1
"""

# Analog channels with 0, 250 and -100 microseconds time skew.
COMTRADE_SAMPLE_8_CFG = """STATION_NAME,EQUIPMENT,1999
3,3A,0D
1, IA,,,A,1,0,0,-32768,32767,1,1,S
2, IB,,,A,1,0,250,-32768,32767,1,1,S
3, IC,,,A,1,0,-100,-32768,32767,1,1,S
60
1
1000,3
01/01/2000,10:30:00.000000
01/01/2000,10:30:00.000000
{format}
1
"""

COMTRADE_SAMPLE_8_DAT = "1,0,1,2,3\n2,1000,4,5,6\n3,2000,7,8,9\n"


class TestTimestamp(unittest.TestCase):
    """Test timestamp parsing."""

    def test_complete_date(self):
        complete_date = "01/01/2000"
        day, month, year = comtrade._get_date(complete_date)
        self.assertEqual(day, 1)
        self.assertEqual(month, 1)
        self.assertEqual(year, 2000)

    def test_complete_time(self):
        complete_time = "10:30:00.228000"
        hour, minute, second, microsecond, \
            in_nanoseconds = comtrade._get_time(complete_time)
        self.assertEqual(hour, 10)
        self.assertEqual(minute, 30)
        self.assertEqual(second, 0)
        self.assertEqual(microsecond, 228000)
        self.assertFalse(in_nanoseconds)

    def test_incomplete_fraction_time(self):
        incomplete_fraction_time = "00:00:00.23"
        hour, minute, second, microsecond, \
            in_nanoseconds = comtrade._get_time(incomplete_fraction_time)
        self.assertEqual(hour, 0)
        self.assertEqual(minute, 0)
        self.assertEqual(second, 0)
        self.assertEqual(microsecond, 230000)
        self.assertFalse(in_nanoseconds)

    def test_nanoseconds(self):
        nanoseconds = "00:00:00.123456789"
        ignore_warnings = True
        hour, minute, second, microsecond, \
            in_nanoseconds = comtrade._get_time(nanoseconds, ignore_warnings)
        self.assertEqual(hour, 0)
        self.assertEqual(minute, 0)
        self.assertEqual(second, 0)
        self.assertEqual(microsecond, 123456)  # s the decimal .789
        self.assertTrue(in_nanoseconds)

    def test_incomplete_seconds(self):
        incomplete_seconds = "01:02:3.012345"
        ignore_warnings = True
        hour, minute, second, microsecond, \
            in_nanoseconds = comtrade._get_time(incomplete_seconds, ignore_warnings)
        self.assertEqual(hour, 1)
        self.assertEqual(minute, 2)
        self.assertEqual(second, 3)
        self.assertEqual(microsecond, 12345)  # s the decimal .789
        self.assertFalse(in_nanoseconds)


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
                         self.comtrade.cfg.TIME_BASE_MICRO_SEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")


class TestCfg1LazyReading(unittest.TestCase):
    """String CFG and DAT 1999 pair test case, abusing missing values in CFG."""
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.read(COMTRADE_SAMPLE_1_CFG_LAZY, COMTRADE_SAMPLE_1_DAT)

    def test_station(self):
        self.assertEqual(self.comtrade.station_name, "")

    def test_rec_dev_id(self):
        self.assertEqual(self.comtrade.rec_dev_id, "")

    def test_rev_year(self):
        self.assertEqual(self.comtrade.rev_year, "1999")

    def test_1a(self):
        self.assertEqual(self.comtrade.analog_count, 1)

    def test_1d(self):
        self.assertEqual(self.comtrade.status_count, 1)

    def test_2c(self):
        self.assertEqual(self.comtrade.channels_count, 2)

    def test_frequency(self):
        self.assertEqual(float(self.comtrade.frequency), 0.0)

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples, 2)

    def test_timestamp(self):
        self.assertEqual(self.comtrade.start_timestamp,
                         dt.datetime(1, 1, 1, 0, 0, 0, 0, None))

        self.assertEqual(self.comtrade.trigger_timestamp,
                         dt.datetime(1, 1, 1, 0, 0, 0, 0, None))

    def test_time_base(self):
        self.assertEqual(self.comtrade.time_base,
                         self.comtrade.cfg.TIME_BASE_MICRO_SEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")


class TestCffReading(unittest.TestCase):
    """CFF 2013 file test case."""
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("tests/sample_files/sample_ascii.cff")

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
                         self.comtrade.cfg.TIME_BASE_MICRO_SEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, "ASCII")

    def test_hdr(self):
        self.assertEqual(self.comtrade.hdr, "")

    def test_inf(self):
        self.assertEqual(self.comtrade.inf, "")


class TestCfg2Reading(TestCffReading):
    """CFG and DAT 2013 file pair test case (same content as the CFF test).
    """
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("tests/sample_files/sample_ascii.cfg")

    def test_hdr(self):
        self.assertIsNone(self.comtrade.hdr)

    def test_inf(self):
        self.assertIsNone(self.comtrade.inf)


class TestCfgWithSubCharsReading(TestCfg2Reading):
    """CFG and DAT 2013 file pair test case, but cfg has <sub> characters.
    """
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True).load("tests/sample_files/sample_sub_char.cfg",
                                                            "tests/sample_files/sample_ascii.dat")


class TestAsciiDatWithSubChars(unittest.TestCase):
    """ASCII DAT files ending with the <sub> (0x1A) control character, as
    some platforms append to text files."""
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        for ext in ("cfg", "dat"):
            shutil.copy(f"tests/sample_files/sample_ascii.{ext}",
                        os.path.join(self.tmp_dir, f"sample.{ext}"))
        dat_path = os.path.join(self.tmp_dir, "sample.dat")
        with open(dat_path, "rb") as file:
            contents = file.read()
        with open(dat_path, "wb") as file:
            file.write(contents.rstrip(b"\r\n") + b"\x1a")
        self.cfg_path = os.path.join(self.tmp_dir, "sample.cfg")
        self.expected = Comtrade(ignore_warnings=True).load(
            "tests/sample_files/sample_ascii.cfg")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_load(self):
        obj = Comtrade(ignore_warnings=True).load(self.cfg_path)
        self.assertEqual(obj.total_samples, self.expected.total_samples)
        self.assertEqual(_channel_values(obj), _channel_values(self.expected))

    def test_read(self):
        # the <sub> character is appended to the last status value
        obj = Comtrade(ignore_warnings=True)
        dat = COMTRADE_SAMPLE_1_DAT.rstrip("\n") + "\x1a"
        obj.read(COMTRADE_SAMPLE_1_CFG, dat)
        self.assertEqual(obj.total_samples, 2)
        self.assertAlmostEqual(obj.analog[0][0], 0.0)
        self.assertAlmostEqual(obj.analog[0][1], -2.762, places=6)
        self.assertEqual(list(obj.status[0]), [0, 1])

    def test_read_analog_last_value(self):
        # the <sub> character is appended to the last analog value
        dat = COMTRADE_SAMPLE_8_DAT.rstrip("\n") + "\x1a"
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_8_CFG.format(format="ASCII"), dat)
        self.assertEqual(obj.total_samples, 3)
        self.assertEqual([list(values) for values in obj.analog],
                         [[1, 4, 7], [2, 5, 8], [3, 6, 9]])

    def test_cff(self):
        contents = ("--- file type: CFG ---\n" + COMTRADE_SAMPLE_1_CFG +
                    "--- file type: DAT ASCII ---\n" +
                    COMTRADE_SAMPLE_1_DAT.rstrip("\n") + "\x1a\n")
        path = os.path.join(self.tmp_dir, "sample.cff")
        with open(path, "w", encoding="utf-8") as file:
            file.write(contents)
        obj = Comtrade(ignore_warnings=True).load(path)
        self.assertEqual(obj.total_samples, 2)
        self.assertAlmostEqual(obj.analog[0][0], 0.0)
        self.assertAlmostEqual(obj.analog[0][1], -2.762, places=6)
        self.assertEqual(list(obj.status[0]), [0, 1])


class TestCffFloat32Reading(unittest.TestCase):
    """Sample CFF file with float32 .dat contents.
    """
    def setUp(self):
        self.comtrade = comtrade.load("tests/sample_files/sample_float32.cff",
                                      ignore_warnings=True)

    def test_hdr(self):
        self.assertEqual(len(self.comtrade.hdr.split("\n")), 4)

    def test_inf(self):
        self.assertEqual(len(self.comtrade.inf.split("\n")), 1)

    def test_cfg(self):
        self.assertEqual(self.comtrade.station_name, "EXAMPLE")
        self.assertEqual(self.comtrade.rec_dev_id, "example")
        self.assertEqual(self.comtrade.analog_count, 1)
        self.assertEqual(self.comtrade.status_count, 1)


class TestCfgAsciiEncodingReading(TestCffReading):
    """CFG and DAT 2013 file pair test case (same content as the CFF test), but
    this time with the file using ASCII text encoding.
    """
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("tests/sample_files/sample_ascii_utf-8.cfg", "tests/sample_files/sample_ascii.dat")

    def test_hdr(self):
        self.assertIsNone(self.comtrade.hdr)

    def test_inf(self):
        self.assertIsNone(self.comtrade.inf)

    def test_station(self):
        self.assertEqual(self.comtrade.station_name, "SMARTSTATION testing text encoding: hgvcj터파크387")


class TestBinaryReading(unittest.TestCase):
    dat_format = comtrade._TYPE_BINARY
    filename = "temp_binary"

    def parseAnalog(self, analog_value):
        return int(analog_value)

    def getFormat(self):
        if struct.calcsize("L") == 4:
            return 'Lf h H'
        else:
            return 'If h H'

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
        file_path = os.path.abspath("tests/{}.cfg".format(self.filename))
        with open(file_path, 'w') as file:
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

        file_path = os.path.abspath("tests/{}.dat".format(self.filename))
        with open(file_path, 'wb') as file:
            for isample in range(0, self.samples):
                t = isample * sample_freq
                t_us = t * timebase * timemult
                y_analog = self.parseAnalog(analog(t))
                y_status = status(t)
                file.write(datawriter.pack(isample +1, t_us, y_analog, y_status))

        # Load file
        file_path = os.path.abspath("tests/{}".format(self.filename))
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load(file_path + ".cfg")

    def tearDown(self):
        # Remove temporary files.
        os.remove("tests/{}.cfg".format(self.filename))
        os.remove("tests/{}.dat".format(self.filename))

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
        self.assertLessEqual(100 - max(self.comtrade.analog[0]), tolerance)

    def test_last_status_value(self):
        self.assertEqual(self.comtrade.status[0][-1], 1)

    def test_timestamps(self):
        self.assertEqual(self.comtrade.start_timestamp, 
                         dt.datetime(2019, 1, 1, 0, 0, 0, 0, None))
        self.assertEqual(self.comtrade.trigger_timestamp, 
                         dt.datetime(2019, 1, 1, 0, 0, 2, 0, None))

    def test_time_base(self):
        self.assertEqual(self.comtrade.time_base,
                         self.comtrade.cfg.TIME_BASE_NANO_SEC)

    def test_ft(self):
        self.assertEqual(self.comtrade.ft, self.dat_format)


class TestBinary32Reading(TestBinaryReading):
    dat_format = comtrade._TYPE_BINARY32
    filename = "temp_binary32"

    def parseAnalog(self, analog_value):
        return int(analog_value)

    def getFormat(self):
        if struct.calcsize("L") == 4:
            return 'Lf l H'
        else:
            return 'If i H'


class TestFloat32Reading(TestBinaryReading):
    dat_format = comtrade._TYPE_FLOAT32
    filename = "temp_float32"

    def parseAnalog(self, analog_value):
        return int(analog_value)

    def getFormat(self):
        if struct.calcsize("L") == 4:
            return 'Lf f H'
        else:
            return 'If f H'


class TestRealBinaryReading(unittest.TestCase):
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load(COMTRADE_SAMPLE_4_CFG_FILE,
                           COMTRADE_SAMPLE_4_DAT_FILE)

    def test_value_conversion(self):
        va_4 = -23425 * 0.000361849
        self.assertAlmostEqual(va_4, self.comtrade.analog[0][3], places=6)

    def test_values(self):
        va = self.comtrade.analog[0][0]
        vb = self.comtrade.analog[1][0]
        vc = self.comtrade.analog[2][0]
        vn = self.comtrade.analog[3][0]
        # sum of phase-ground voltages is approximately 0
        self.assertAlmostEqual(0.0, va + vb + vc + vn, 1)

    def test_time(self):
        time_diff = self.comtrade.time[2] - self.comtrade.time[1]
        sample_rate = self.comtrade.cfg.sample_rates[0][0]
        self.assertAlmostEqual(1.0 / sample_rate, time_diff)


# Most negative single precision value, the FLOAT32 missing data marker.
FLOAT32_MISSING = -3.4028234663852886e+38

# One analog channel (value = 2 * y + 1) and one status channel.
COMTRADE_SAMPLE_FLOAT32_MISSING_CFG = """STATION_NAME,EQUIPMENT,2013
2,1A,1D
1, IA,,,A,2.0,1.0,0,-3.40282347E+38,3.40282347E+38,1,1,P
1, Trip,,,0
60
1
1000,3
01/01/2020,10:30:00.000000
01/01/2020,10:30:00.000000
FLOAT32
1
"""


def _float32_dat(rows) -> bytes:
    """FLOAT32 DAT file contents of (sample number, timestamp, analog,
    status) rows."""
    return b"".join(struct.pack("<IIfH", n, ts, analog, status)
                    for n, ts, analog, status in rows)


class TestFloat32MissingDataReading(unittest.TestCase):
    """FLOAT32 DAT file missing data (the most negative float32 value)."""
    use_numpy_arrays = False
    use_double_precision = False

    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True,
                                 use_numpy_arrays=self.use_numpy_arrays,
                                 use_double_precision=self.use_double_precision)
        self.comtrade.read(COMTRADE_SAMPLE_FLOAT32_MISSING_CFG,
                           _float32_dat([(1, 0, FLOAT32_MISSING, 0),
                                         (2, 1000, 4.0, 1),
                                         (3, 2000, 5.0, 0)]))

    def test_missing_marker(self):
        reader = comtrade._Float32DatReader()
        # the missing marker is the 0xFF7FFFFF single precision value
        self.assertEqual(reader.DATA_MISSING,
                         struct.unpack("<f", b"\xff\xff\x7f\xff")[0])

    def test_missing_value(self):
        self.assertTrue(math.isnan(self.comtrade.analog[0][0]))

    def test_missing_value_is_not_scaled(self):
        # a missing value must not be converted to a (possibly infinite)
        # measurement
        self.assertTrue(math.isnan(self.comtrade.analog_primary[0][0]))
        self.assertTrue(math.isnan(self.comtrade.analog_secondary[0][0]))

    def test_values_after_missing(self):
        self.assertAlmostEqual(2.0 * 4.0 + 1.0, self.comtrade.analog[0][1])
        self.assertAlmostEqual(2.0 * 5.0 + 1.0, self.comtrade.analog[0][2])

    def test_large_negative_values_are_not_missing(self):
        analog = -1.0e+38
        obj = Comtrade(ignore_warnings=True,
                       use_numpy_arrays=self.use_numpy_arrays)
        obj.read(COMTRADE_SAMPLE_FLOAT32_MISSING_CFG,
                 _float32_dat([(1, 0, analog, 0)]))
        self.assertFalse(math.isnan(obj.analog[0][0]))
        single = struct.unpack("<f", struct.pack("<f", analog))[0]
        expected = 2.0 * single + 1.0
        self.assertAlmostEqual(expected, obj.analog[0][0],
                               delta=abs(expected) * 1e-6)

    def test_status_values(self):
        self.assertEqual(list(self.comtrade.status[0]), [0, 1, 0])

    def test_total_samples(self):
        self.assertEqual(self.comtrade.total_samples, 3)
        self.assertEqual(len(self.comtrade.analog[0]), 3)
        self.assertEqual(len(self.comtrade.time), 3)

    def test_time(self):
        for t, expected in zip(self.comtrade.time, [0.0, 0.001, 0.002]):
            self.assertAlmostEqual(t, expected, places=6)


class TestFloat32MissingDataReadingDoublePrecision(
        TestFloat32MissingDataReading):
    use_double_precision = True


@unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
class TestFloat32MissingDataReadingNumpy(TestFloat32MissingDataReading):
    use_numpy_arrays = True


class TestEncodingHandling(unittest.TestCase):
    def test_loading_utf8(self):
        obj = comtrade.load(
            "tests/sample_files/sample_ascii_utf-8.cfg",
            "tests/sample_files/sample_ascii.dat",
            encoding="utf-8",
        )
        self.assertEqual(obj.cfg.station_name, "SMARTSTATION testing text encoding: hgvcj터파크387")
        self.assertEqual(obj.cfg.rec_dev_id, "IED123")

    def test_loading_iso8859_1(self):
        obj = comtrade.load("tests/sample_files/sample_iso8859-1.cfg", encoding="iso-8859-1")
        self.assertEqual(obj.cfg.station_name, "Estação de Medição")
        self.assertEqual(obj.cfg.rec_dev_id, "Oscilógrafo")
    
    def test_loading_iso8859_1_bin(self):
        obj = comtrade.load("tests/sample_files/sample_iso8859-1_bin.cfg", encoding="iso-8859-1")
        self.assertEqual(obj.cfg.station_name, "Estação de Medição")
        self.assertEqual(obj.cfg.rec_dev_id, "Oscilógrafo")


CFF_ENCODING_CONTENTS = """--- file type: CFG ---
Estação de Medição,Oscilógrafo,2013
2,1A,1D
1, IA,,,A,2.0,1.0,0,-3.40282347E+38,3.40282347E+38,1,1,P
1, Trip,,,0
60
1
1000,2
01/01/2020,10:30:00.000000
01/01/2020,10:30:00.000000
ASCII
1

--- file type: HDR ---
Relé de proteção
--- file type: INF ---
[Public Record_Information]
Source=Medição
--- file type: DAT ASCII ---
1,0,1,0
2,1000,2,1
"""


class TestCffEncodingHandling(unittest.TestCase):
    """Text encoding of the CFG, HDR and INF sections of a CFF file."""
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_cff(self, filename: str, encoding: str) -> str:
        path = os.path.join(self.tmp_dir, filename)
        with open(path, "w", encoding=encoding, newline="\n") as file:
            file.write(CFF_ENCODING_CONTENTS)
        return path

    def test_iso8859_1(self):
        path = self._write_cff("sample_latin1.cff", "iso-8859-1")
        obj = Comtrade(ignore_warnings=True).load(path, encoding="iso-8859-1")
        self.assertEqual(obj.station_name, "Estação de Medição")
        self.assertEqual(obj.rec_dev_id, "Oscilógrafo")
        self.assertEqual(obj.hdr, "Relé de proteção")
        self.assertEqual(obj.inf_sections()["Public Record_Information"]["Source"],
                         "Medição")

    def test_utf8(self):
        path = self._write_cff("sample_utf8.cff", "utf-8")
        obj = Comtrade(ignore_warnings=True).load(path, encoding="utf-8")
        self.assertEqual(obj.station_name, "Estação de Medição")
        self.assertEqual(obj.hdr, "Relé de proteção")
        self.assertEqual(obj.inf_sections()["Public Record_Information"]["Source"],
                         "Medição")

    def test_default_encoding_is_utf8(self):
        path = self._write_cff("sample_utf8.cff", "utf-8")
        obj = Comtrade(ignore_warnings=True).load(path)
        self.assertEqual(obj.station_name, "Estação de Medição")

    def test_data_values(self):
        path = self._write_cff("sample_utf8.cff", "utf-8")
        obj = Comtrade(ignore_warnings=True).load(path)
        self.assertEqual(obj.total_samples, 2)
        # analog values are 2 * y + 1
        self.assertEqual(list(obj.analog[0]), [3.0, 5.0])
        self.assertEqual(list(obj.status[0]), [0, 1])

    def test_binary_cff_keeps_the_encoding_option(self):
        obj = Comtrade(ignore_warnings=True)
        obj.load("tests/sample_files/sample_float32.cff", encoding="iso-8859-1")
        self.assertEqual(obj.station_name, "EXAMPLE")
        self.assertEqual(obj.total_samples, 301)
        self.assertEqual(obj.status_count, 1)
 

class TestExtensionCaseHandling(unittest.TestCase):
    def test_lower_case(self):
        self.assertEqual(comtrade._get_same_case(".cfg", ".dat"), ".dat")

    def test_upper_case(self):
        self.assertEqual(comtrade._get_same_case(".CFG", ".dat"), ".DAT")

    def test_capitalized(self):
        self.assertEqual(comtrade._get_same_case(".Cfg", ".dat"), ".Dat")


class TestCfgAsciiMissingDataReading(TestCfgAsciiEncodingReading):
    """CFG and DAT 2013 file pair test case (same content as the CFF test), but
    this time with the file using ASCII text encoding and empty strings (missing data) on dat file.
    """
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("tests/sample_files/sample_ascii.cfg", "tests/sample_files/sample_ascii_missing.dat")

    def test_station(self):
        pass

    def test_known_missing_values(self):
        self.assertTrue(math.isnan(self.comtrade.analog[0][1]))
        self.assertTrue(math.isnan(self.comtrade.analog[1][2]))
        self.assertTrue(math.isnan(self.comtrade.analog[2][3]))
        self.assertTrue(math.isnan(self.comtrade.analog[3][4]))


class TestCfgBinaryMissingDataReading(unittest.TestCase):
    """Binary dat file with missing data (0xFFFF values)."""
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.load("tests/sample_files/sample_bin.cfg", "tests/sample_files/sample_bin_missing.dat")

    def test_known_missing_values(self):
        self.assertTrue(math.isnan(self.comtrade.analog[0][0]))
        self.assertTrue(math.isnan(self.comtrade.analog[1][1]))
        self.assertTrue(math.isnan(self.comtrade.analog[2][2]))
        self.assertTrue(math.isnan(self.comtrade.analog[3][3]))


class TestDoublePrecisionHandling(unittest.TestCase):
    def test_should_use_single_by_default(self):
        comtrade = Comtrade(ignore_warnings=True)
        comtrade.load(
            "tests/sample_files/sample_ascii.cfg",
            "tests/sample_files/sample_ascii.dat",
        )

        self.assertEqual(comtrade._use_double_precision, False)
        self.assertEqual(comtrade._get_dat_reader()._use_double_precision, False)

        self.assertEqual(comtrade.time.typecode, "f")
        for chan in comtrade.analog:
            self.assertEqual(chan.typecode, "f")

    def test_should_use_single_when_specified(self):
        comtrade = Comtrade(ignore_warnings=True, use_double_precision=False)
        comtrade.load(
            "tests/sample_files/sample_ascii.cfg",
            "tests/sample_files/sample_ascii.dat",
        )

        self.assertEqual(comtrade._use_double_precision, False)
        self.assertEqual(comtrade._get_dat_reader()._use_double_precision, False)

        self.assertEqual(comtrade.time.typecode, "f")
        for chan in comtrade.analog:
            self.assertEqual(chan.typecode, "f")

    def test_should_use_double_when_specified(self):
        comtrade = Comtrade(ignore_warnings=True, use_double_precision=True)
        comtrade.load(
            "tests/sample_files/sample_ascii.cfg",
            "tests/sample_files/sample_ascii.dat",
        )

        self.assertEqual(comtrade._use_double_precision, True)
        self.assertEqual(comtrade._get_dat_reader()._use_double_precision, True)

        self.assertEqual(comtrade.time.typecode, "d")
        for chan in comtrade.analog:
            self.assertEqual(chan.typecode, "d")


class TestMultipleSampleRates(unittest.TestCase):
    """ASCII DAT file with two sample rates."""
    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.read(COMTRADE_SAMPLE_5_CFG.format(format="ASCII"),
                           COMTRADE_SAMPLE_5_DAT)

    def test_sample_rates(self):
        self.assertEqual(self.comtrade.cfg.sample_rates, [[1000.0, 4], [500.0, 6]])

    def test_time(self):
        expected = [0.0, 0.001, 0.002, 0.003, 0.005, 0.007]
        self.assertEqual(len(self.comtrade.time), len(expected))
        for t, t_expected in zip(self.comtrade.time, expected):
            self.assertAlmostEqual(t, t_expected, places=6)


class TestMultipleSampleRatesBinary(TestMultipleSampleRates):
    """Binary DAT file with two sample rates."""
    def setUp(self):
        dat = b"".join(struct.pack("<IIhH", n, ts, n, status)
                       for n, ts, status in [(1, 0, 0), (2, 1000, 0), (3, 2000, 0),
                                             (4, 3000, 0), (5, 5000, 1), (6, 7000, 1)])
        self.comtrade = Comtrade(ignore_warnings=True)
        self.comtrade.read(COMTRADE_SAMPLE_5_CFG.format(format="BINARY"), dat)


class TestAsciiMissingTimestamp(unittest.TestCase):
    """ASCII DAT file with blank timestamps."""
    def test_time_from_sample_rate(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_6_CFG, COMTRADE_SAMPLE_6_DAT)
        for t, t_expected in zip(obj.time, [0.0, 0.001, 0.002]):
            self.assertAlmostEqual(t, t_expected, places=6)
        self.assertEqual(list(obj.analog[0]), [1.0, 2.0, 3.0])
        self.assertEqual(list(obj.status[0]), [0, 0, 1])

    def test_critical_timestamp(self):
        # Without a sample rate the timestamps cannot be computed.
        obj = Comtrade(ignore_warnings=True)
        cfg = COMTRADE_SAMPLE_3_CFG.format(samples=3, seconds=0, format="ASCII")
        with self.assertRaises(comtrade.ComtradeError):
            obj.read(cfg, COMTRADE_SAMPLE_6_DAT)

    def test_binary_missing_marker_is_a_valid_timestamp(self):
        # 0xFFFFFFFF marks a missing timestamp in binary files only: in an
        # ASCII file it is an ordinary decimal timestamp (issue #56).
        obj = Comtrade(ignore_warnings=True, use_double_precision=True)
        cfg = COMTRADE_SAMPLE_3_CFG.format(samples=3, seconds=0, format="ASCII")
        obj.read(cfg, "1,4294967294,1,0\n2,4294967295,2,0\n3,4294967296,3,1\n")
        expected = [4.294967294, 4.294967295, 4.294967296]
        self.assertEqual(len(obj.time), len(expected))
        for t, t_expected in zip(obj.time, expected):
            self.assertAlmostEqual(t, t_expected, places=9)


class TestBinaryMissingTimestamp(unittest.TestCase):
    """Binary DAT file with missing (0xFFFFFFFF) timestamps."""
    def test_critical_timestamp(self):
        # Without a sample rate the timestamps cannot be computed.
        dat = b"".join(struct.pack("<IIhH", n, ts, n, 0)
                       for n, ts in [(1, 0), (2, 0xFFFFFFFF), (3, 2000)])
        obj = Comtrade(ignore_warnings=True)
        cfg = COMTRADE_SAMPLE_3_CFG.format(samples=3, seconds=0, format="BINARY")
        with self.assertRaises(comtrade.ComtradeError):
            obj.read(cfg, dat)


class TestStatusOnlyBinaryReading(unittest.TestCase):
    """Binary DAT files without analog channels."""
    def test_status_values(self):
        dat = b"".join(struct.pack("<IIH", n, (n - 1) * 1000, bits)
                       for n, bits in [(1, 0b00), (2, 0b01), (3, 0b11)])
        for dat_format in ("BINARY", "BINARY32", "FLOAT32"):
            with self.subTest(format=dat_format):
                obj = Comtrade(ignore_warnings=True)
                obj.read(COMTRADE_SAMPLE_7_CFG.format(format=dat_format), dat)
                self.assertEqual(obj.analog_count, 0)
                self.assertEqual(list(obj.status[0]), [0, 1, 1])
                self.assertEqual(list(obj.status[1]), [0, 0, 1])


class TestAnalogChannelSkew(unittest.TestCase):
    """ASCII DAT file with skewed analog channels."""
    use_numpy_arrays = False

    def setUp(self):
        self.comtrade = Comtrade(ignore_warnings=True,
                                 use_numpy_arrays=self.use_numpy_arrays)
        self.comtrade.read(COMTRADE_SAMPLE_8_CFG.format(format="ASCII"),
                           COMTRADE_SAMPLE_8_DAT)

    def test_skew(self):
        skews = [channel.skew for channel in self.comtrade.cfg.analog_channels]
        self.assertEqual(skews, [0.0, 250.0, -100.0])

    def test_sample_time(self):
        for t, t_expected in zip(self.comtrade.time, [0.0, 0.001, 0.002]):
            self.assertAlmostEqual(t, t_expected, places=6)

    def test_analog_time(self):
        expected = [[0.0, 0.001, 0.002],
                    [0.00025, 0.00125, 0.00225],
                    [-0.0001, 0.0009, 0.0019]]
        self.assertEqual(len(self.comtrade.analog_time), self.comtrade.analog_count)
        for channel_time, channel_expected in zip(self.comtrade.analog_time, expected):
            self.assertEqual(len(channel_time), len(channel_expected))
            for t, t_expected in zip(channel_time, channel_expected):
                self.assertAlmostEqual(t, t_expected, places=6)


class TestAnalogChannelSkewBinary(TestAnalogChannelSkew):
    """Binary DAT file with skewed analog channels."""
    def setUp(self):
        dat = b"".join(struct.pack("<II3h", n, ts, *values)
                       for n, ts, values in [(1, 0, (1, 2, 3)), (2, 1000, (4, 5, 6)),
                                             (3, 2000, (7, 8, 9))])
        self.comtrade = Comtrade(ignore_warnings=True,
                                 use_numpy_arrays=self.use_numpy_arrays)
        self.comtrade.read(COMTRADE_SAMPLE_8_CFG.format(format="BINARY"), dat)


@unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
class TestAnalogChannelSkewNumpy(TestAnalogChannelSkew):
    """Skewed analog channels using numpy arrays."""
    use_numpy_arrays = True


def _channel_values(obj) -> list:
    """Time, analog and status values lists of a record, with None for NaN
    (since NaN != NaN)."""
    return [[None if math.isnan(value) else value for value in values]
            for values in [obj.time] + obj.analog + obj.status]


class TestAsciiBlockReading(unittest.TestCase):
    """ASCII DAT file read in blocks of a few lines."""
    def test_block_sizes(self):
        files = ("tests/sample_files/sample_ascii.cfg",
                 "tests/sample_files/sample_ascii_missing.dat")
        expected = _channel_values(Comtrade(ignore_warnings=True).load(*files))
        # 10 values per line: 1 and 3 lines per block
        for block_values in (1, 30):
            with self.subTest(block_values=block_values), \
                    mock.patch.object(comtrade, "_ASCII_BLOCK_VALUES", block_values):
                obj = Comtrade(ignore_warnings=True).load(*files)
                self.assertEqual(_channel_values(obj), expected)


class TestDatRowsCount(unittest.TestCase):
    """DAT files with more or fewer rows than the CFG total samples."""
    use_numpy_arrays = False

    def read(self, dat_format, rows):
        obj = Comtrade(ignore_warnings=True,
                       use_numpy_arrays=self.use_numpy_arrays)
        if dat_format == "ASCII":
            dat = "".join("{0},{1},{0},{2}\n".format(n, ts, status)
                          for n, ts, status in rows)
        else:
            dat = b"".join(struct.pack("<IIhH", n, ts, n, status)
                           for n, ts, status in rows)
        obj.read(COMTRADE_SAMPLE_5_CFG.format(format=dat_format), dat)
        return obj

    def test_more_rows(self):
        rows = [(n, (n - 1) * 1000, n % 2) for n in range(1, 9)]
        for dat_format in ("ASCII", "BINARY"):
            with self.subTest(format=dat_format):
                obj = self.read(dat_format, rows)
                self.assertEqual(list(obj.analog[0]), [1, 2, 3, 4, 5, 6])
                self.assertEqual(list(obj.status[0]), [1, 0, 1, 0, 1, 0])

    def test_fewer_rows(self):
        # values of the samples missing in the DAT file are zero
        rows = [(n, (n - 1) * 1000, n % 2) for n in range(1, 5)]
        for dat_format in ("ASCII", "BINARY"):
            with self.subTest(format=dat_format):
                obj = self.read(dat_format, rows)
                self.assertEqual(list(obj.analog[0]), [1, 2, 3, 4, 0, 0])
                self.assertEqual(list(obj.status[0]), [1, 0, 1, 0, 0, 0])
                self.assertEqual(len(obj.time), 6)


@unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
class TestDatRowsCountNumpy(TestDatRowsCount):
    """DAT files with more or fewer rows, using numpy arrays."""
    use_numpy_arrays = True


@unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
class TestNumpyArraysReading(unittest.TestCase):
    """DAT files read into numpy arrays have the same values as arrays."""
    def test_values(self):
        for files in (("tests/sample_files/sample_ascii.cfg",
                       "tests/sample_files/sample_ascii_missing.dat"),
                      ("tests/sample_files/sample_bin.cfg",
                       "tests/sample_files/sample_bin_missing.dat"),
                      ("tests/sample_files/sample_float32.cff",)):
            with self.subTest(files=files):
                expected = Comtrade(ignore_warnings=True).load(*files)
                obj = Comtrade(ignore_warnings=True,
                               use_numpy_arrays=True).load(*files)
                self.assertIsInstance(obj.analog[0], comtrade.numpy.ndarray)
                self.assertIsInstance(obj.status[0], comtrade.numpy.ndarray)
                self.assertEqual(_channel_values(obj), _channel_values(expected))


class TestTimeCodeParsing(unittest.TestCase):
    """2013 revision time code, time quality and leap second fields."""
    def test_time_codes(self):
        cases = {
            "0": dt.timedelta(0),
            "+10": dt.timedelta(hours=10),
            "5": dt.timedelta(hours=5),
            "-5h30": -dt.timedelta(hours=5, minutes=30),
            "+5H45": dt.timedelta(hours=5, minutes=45),
            " -3 ": dt.timedelta(hours=-3),
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(comtrade._parse_time_code(code), expected)

    def test_not_applicable_time_codes(self):
        for code in ("", "x", "X"):
            with self.subTest(code=code):
                self.assertIsNone(comtrade._parse_time_code(code))

    def test_invalid_time_codes(self):
        for code in ("24", "5h60", "abc", "5:30"):
            with self.subTest(code=code):
                with self.assertWarns(Warning):
                    self.assertIsNone(comtrade._parse_time_code(code))
                self.assertIsNone(comtrade._parse_time_code(code, True))

    def test_tmq_codes(self):
        self.assertEqual(comtrade._parse_tmq_code("0"), 0)
        self.assertEqual(comtrade._parse_tmq_code("B"), 11)
        self.assertEqual(comtrade._parse_tmq_code("f"), 15)
        self.assertIsNone(comtrade._parse_tmq_code(""))
        with self.assertWarns(Warning):
            self.assertIsNone(comtrade._parse_tmq_code("G"))

    def test_leap_seconds(self):
        for value in range(4):
            self.assertEqual(comtrade._parse_leap_second(str(value)), value)
        self.assertIsNone(comtrade._parse_leap_second(""))
        with self.assertWarns(Warning):
            self.assertIsNone(comtrade._parse_leap_second("4"))


class TestTimeCodeReading(unittest.TestCase):
    """2013 revision time information read from CFG and CFF files."""
    def test_files(self):
        for files in (("tests/sample_files/sample_ascii.cfg",),
                      ("tests/sample_files/sample_ascii.cff",)):
            with self.subTest(files=files):
                obj = Comtrade(ignore_warnings=True).load(*files)
                cfg = obj.cfg
                offset = -dt.timedelta(hours=5, minutes=30)
                self.assertEqual(cfg.time_code, "-5h30")
                self.assertEqual(cfg.local_code, "-5h30")
                self.assertEqual(cfg.time_offset, offset)
                self.assertEqual(cfg.local_offset, offset)
                self.assertEqual(cfg.tmq_code, 0xB)
                self.assertEqual(cfg.leap_second, 3)
                # naive timestamps are kept as written in the file
                self.assertIsNone(obj.start_timestamp.tzinfo)
                utc = dt.timezone.utc
                self.assertEqual(obj.start_timestamp_utc,
                                 dt.datetime(2011, 1, 12, 11, 25, 30, 75011, utc))
                self.assertEqual(obj.trigger_timestamp_utc,
                                 dt.datetime(2011, 1, 12, 11, 25, 30, 78261, utc))
                self.assertEqual(obj.start_timestamp_utc,
                                 obj.start_timestamp.replace(tzinfo=dt.timezone(offset)))

    def test_older_revision(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        self.assertEqual(obj.cfg.time_code, "")
        self.assertEqual(obj.cfg.local_code, "")
        self.assertIsNone(obj.cfg.time_offset)
        self.assertIsNone(obj.cfg.tmq_code)
        self.assertIsNone(obj.cfg.leap_second)
        self.assertIsNone(obj.start_timestamp_utc)
        self.assertIsNone(obj.trigger_timestamp_utc)

    def _read_cfg_with_last_lines(self, last_lines: str) -> comtrade.Cfg:
        with open("tests/sample_files/sample_ascii.cfg", encoding="utf-8") as f:
            lines = f.read().splitlines()
        cfg = comtrade.Cfg(ignore_warnings=True)
        cfg.read("\n".join(lines[:-2]) + "\n" + last_lines)
        return cfg

    def test_missing_tmq_line(self):
        cfg = self._read_cfg_with_last_lines("+2,x\n")
        self.assertEqual(cfg.time_offset, dt.timedelta(hours=2))
        self.assertIsNone(cfg.local_offset)
        self.assertIsNone(cfg.tmq_code)
        self.assertIsNone(cfg.leap_second)
        self.assertEqual(cfg.start_timestamp_utc,
                         dt.datetime(2011, 1, 12, 3, 55, 30, 75011, dt.timezone.utc))

    def test_single_time_code(self):
        cfg = self._read_cfg_with_last_lines("0\n0,0\n")
        self.assertEqual(cfg.time_offset, dt.timedelta(0))
        self.assertIsNone(cfg.local_offset)
        self.assertEqual(cfg.tmq_code, 0)
        self.assertEqual(cfg.leap_second, 0)

    def test_empty_time_code_line(self):
        # the tmq line follows an empty time code line
        cfg = self._read_cfg_with_last_lines("\nB,3\n")
        self.assertEqual(cfg.time_code, "")
        self.assertEqual(cfg.local_code, "")
        self.assertIsNone(cfg.time_offset)
        self.assertIsNone(cfg.local_offset)
        self.assertEqual(cfg.tmq_code, 0xB)
        self.assertEqual(cfg.leap_second, 3)
        self.assertIsNone(cfg.start_timestamp_utc)

    def test_empty_time_code_line_without_tmq_line(self):
        cfg = self._read_cfg_with_last_lines("\n")
        self.assertEqual(cfg.time_code, "")
        self.assertIsNone(cfg.time_offset)
        self.assertIsNone(cfg.tmq_code)
        self.assertIsNone(cfg.leap_second)

    def test_empty_time_code_and_tmq_lines(self):
        cfg = self._read_cfg_with_last_lines("\n\n")
        self.assertIsNone(cfg.time_offset)
        self.assertIsNone(cfg.tmq_code)
        self.assertIsNone(cfg.leap_second)

    def test_empty_time_code_line_record(self):
        cfg_text = COMTRADE_SAMPLE_2013_EMPTY_TIME_CODE_CFG
        obj = Comtrade(ignore_warnings=True)
        obj.read(cfg_text, "1,0,1\n2,1000,2\n")
        self.assertEqual(obj.rev_year, "2013")
        self.assertEqual(obj.cfg.tmq_code, 0xB)
        self.assertEqual(obj.cfg.leap_second, 3)
        self.assertIsNone(obj.start_timestamp_utc)
        self.assertEqual(obj.start_timestamp,
                         dt.datetime(2013, 1, 1, 10, 30, 0, 0, None))
        self.assertEqual(obj.total_samples, 2)


COMTRADE_SAMPLE_2013_EMPTY_TIME_CODE_CFG = """STATION_NAME,EQUIPMENT,2013
1,1A,0D
1, IA,,,A,1,0,0,-32768,32767,1,1,S
60
1
1000,2
01/01/2013,10:30:00.000000
01/01/2013,10:30:00.000000
ASCII
1

B,3
"""


INF_SAMPLE = """; Information file sample
[Public Record_Information]
Source=SMARTSTATION relay
Record_Information=FAULT,PHASE-A,TRIP
Location=12.3 km

[Public Analog_Channel_#1]
Channel_ID=IA
Channel_Phase=A

[ABC Corp Private Section]
Some_Key=a = b
"""


class TestInfSections(unittest.TestCase):
    """INF file contents parsed into a ConfigParser object."""
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        for ext in ("cfg", "dat"):
            shutil.copy(f"tests/sample_files/sample_ascii.{ext}",
                        os.path.join(self.tmp_dir, f"sample.{ext}"))
        self.cfg_path = os.path.join(self.tmp_dir, "sample.cfg")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_inf(self, contents: str):
        with open(os.path.join(self.tmp_dir, "sample.inf"), "w",
                  encoding="utf-8") as f:
            f.write(contents)

    def test_sections(self):
        self._write_inf(INF_SAMPLE)
        obj = Comtrade(ignore_warnings=True).load(self.cfg_path)
        self.assertEqual(obj.inf, INF_SAMPLE)
        inf = obj.inf_sections()
        self.assertEqual(inf.sections(), ["Public Record_Information",
                                          "Public Analog_Channel_#1",
                                          "ABC Corp Private Section"])
        record = inf["Public Record_Information"]
        self.assertEqual(record["Source"], "SMARTSTATION relay")
        self.assertEqual(record["Record_Information"], "FAULT,PHASE-A,TRIP")
        self.assertEqual(inf["Public Analog_Channel_#1"]["Channel_ID"], "IA")
        self.assertEqual(inf["ABC Corp Private Section"]["Some_Key"], "a = b")

    def test_duplicates(self):
        self._write_inf("[Public Record_Information]\nSource=A\nSource=B\n"
                        "[Public Record_Information]\nLocation=1\n")
        inf = Comtrade(ignore_warnings=True).load(self.cfg_path).inf_sections()
        record = inf["Public Record_Information"]
        self.assertEqual(record["Source"], "B")
        self.assertEqual(record["Location"], "1")

    def test_no_inf(self):
        obj = Comtrade(ignore_warnings=True).load(self.cfg_path)
        self.assertIsNone(obj.inf)
        self.assertIsNone(obj.inf_sections())
        cff = Comtrade(ignore_warnings=True).load("tests/sample_files/sample_ascii.cff")
        self.assertIsNone(cff.inf_sections())


COMTRADE_SAMPLE_1991_CFG = """STATION_NAME,EQUIPMENT
3,2A,1D
1,IA,A,LINE,A,2,0,0,-32767,32767
2,VA,A,LINE,kV,1,0,0,-32767,32767
1,TRIP,1
60
1
1000,2
01/02/2000,10:30:00.000000
01/02/2000,10:30:00.001000
ASCII
"""

COMTRADE_SAMPLE_RATIO_CFG = """STATION_NAME,EQUIPMENT,1999
4,4A,0D
1,IA_P,A,,A,1,0,0,-32767,32767,1000,5,P
2,IA_S,A,,A,1,0,0,-32767,32767,1000,5,s
3,VA_S,A,,V,1,0,0,-32767,32767,0,0,S
4,FREQ,,,Hz,1,0,0,-32767,32767,,,
60
1
1000,2
01/02/2000,10:30:00.000000
01/02/2000,10:30:00.001000
ASCII
1
"""

COMTRADE_SAMPLE_RATIO_DAT = "1,0,10,10,10,60\n2,1000,-20,-20,-20,61\n"


class TestChannelLines(unittest.TestCase):
    """Analog and status channel lines of different revisions."""
    def test_1991_channels(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_1991_CFG, "1,0,1,2,1\n2,1000,3,4,0\n")
        self.assertEqual(obj.rev_year, "1991")
        status = obj.cfg.status_channels[0]
        self.assertEqual((status.n, status.name, status.ph, status.ccbm, status.y),
                         (1, "TRIP", "", "", 1))
        analog = obj.cfg.analog_channels[0]
        self.assertEqual((analog.primary, analog.secondary, analog.pors),
                         (1.0, 1.0, "P"))
        # without ratio information, values are not scaled
        self.assertEqual(list(obj.analog_secondary[0]), list(obj.analog[0]))

    def test_missing_normal_state_warning(self):
        cfg_text = COMTRADE_SAMPLE_1_CFG.replace("Diff Trip A     ,,,0",
                                                 "Diff Trip A     ,,,")
        obj = Comtrade()
        with self.assertWarns(Warning) as context:
            obj.read(cfg_text, COMTRADE_SAMPLE_1_DAT)
        self.assertIn("status channel 1", str(context.warning))
        self.assertEqual(obj.cfg.status_channels[0].y, 0)

    def test_normal_state(self):
        obj = Comtrade()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        self.assertEqual(obj.cfg.status_channels[0].y, 0)


class TestAnalogScaling(unittest.TestCase):
    """Analog values in primary and secondary units."""
    use_numpy_arrays = False

    def setUp(self):
        self.obj = Comtrade(ignore_warnings=True,
                            use_numpy_arrays=self.use_numpy_arrays)
        self.obj.read(COMTRADE_SAMPLE_RATIO_CFG, COMTRADE_SAMPLE_RATIO_DAT)

    def test_primary(self):
        primary = self.obj.analog_primary
        self.assertEqual(list(primary[0]), [10, -20])
        self.assertEqual(list(primary[1]), [2000, -4000])
        # invalid ratio: unscaled values
        self.assertEqual(list(primary[2]), [10, -20])
        self.assertEqual(list(primary[3]), [60, 61])

    def test_secondary(self):
        secondary = self.obj.analog_secondary
        for value, expected in zip(secondary[0], [0.05, -0.1]):
            self.assertAlmostEqual(value, expected, places=6)
        self.assertEqual(list(secondary[1]), [10, -20])
        self.assertEqual(list(secondary[2]), [10, -20])
        self.assertEqual(list(secondary[3]), [60, 61])

    def test_array_types(self):
        for values in self.obj.analog_primary + self.obj.analog_secondary:
            self.assertIs(type(values), type(self.obj.analog[0]))

    def test_cached(self):
        self.assertIs(self.obj.analog_primary, self.obj.analog_primary)
        self.obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        self.assertEqual(len(self.obj.analog_primary), 1)

    def test_invalid_ratio_warning(self):
        obj = Comtrade()
        obj.read(COMTRADE_SAMPLE_RATIO_CFG, COMTRADE_SAMPLE_RATIO_DAT)
        with self.assertWarns(Warning) as context:
            obj.analog_primary
        self.assertIn("analog channel 3", str(context.warning))


@unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
class TestAnalogScalingNumpy(TestAnalogScaling):
    use_numpy_arrays = True


class TestNanosecondTimestamps(unittest.TestCase):
    """Timestamps with nanoseconds resolution."""
    def test_time_without_fraction(self):
        self.assertEqual(comtrade._get_time("10:30:00"), (10, 30, 0, 0, False))

    def test_invalid_time(self):
        with self.assertWarns(Warning):
            self.assertEqual(comtrade._get_time("abc"), (0, 0, 0, 0, False))

    def test_extra_digits(self):
        hour, minute, second, nanosecond, in_nanoseconds = \
            comtrade._parse_time("00:00:01.123456789123", True)
        self.assertEqual((second, nanosecond, in_nanoseconds), (1, 123456789, True))

    def test_nanoseconds_warning(self):
        with self.assertWarns(Warning):
            comtrade._read_timestamp("01/01/2019,00:00:00.000000001", "2013")

    def test_timestamps_ns(self):
        cfg_text = COMTRADE_SAMPLE_3_CFG.format(samples=2, seconds=0.000001500,
                                                format="ASCII")
        obj = Comtrade(ignore_warnings=True)
        obj.read(cfg_text, "1,0,1,0\n2,1,2,1\n")
        self.assertEqual(obj.time_base, obj.cfg.TIME_BASE_NANO_SEC)
        start_ns = (dt.datetime(2019, 1, 1) - dt.datetime(1970, 1, 1)) \
            // dt.timedelta(microseconds=1) * 1000
        self.assertEqual(obj.start_timestamp_ns, start_ns)
        self.assertEqual(obj.trigger_timestamp_ns, start_ns + 1500)
        # datetime objects are truncated
        self.assertEqual(obj.trigger_timestamp.microsecond, 1)
        self.assertAlmostEqual(obj.trigger_time, 1.5E-6, places=15)

    def test_microseconds_timestamps_ns(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        self.assertEqual(obj.trigger_timestamp_ns - obj.start_timestamp_ns,
                         494000000)
        self.assertAlmostEqual(obj.trigger_time, 0.494)

    @unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
    def test_numpy_datetime64(self):
        cfg_text = COMTRADE_SAMPLE_3_CFG.format(samples=2, seconds=0.000001500,
                                                format="ASCII")
        obj = Comtrade(ignore_warnings=True)
        obj.read(cfg_text, "1,0,1,0\n2,1,2,1\n")
        value = comtrade.numpy.datetime64(obj.trigger_timestamp_ns, "ns")
        self.assertEqual(str(value), "2019-01-01T00:00:00.000001500")


PARTIAL_LOADING_FILES = (
    ("tests/sample_files/sample_ascii.cfg",),
    ("tests/sample_files/sample_bin.cfg",),
    ("tests/sample_files/sample_ascii.cff",),
    ("tests/sample_files/sample_float32.cff",),
)


class TestTimeWindowLoading(unittest.TestCase):
    """Loading only the samples within a time window."""
    use_numpy_arrays = False

    def load(self, *files, **kwargs):
        return Comtrade(ignore_warnings=True,
                        use_numpy_arrays=self.use_numpy_arrays).load(*files, **kwargs)

    def assertWindow(self, obj, full, first: int, last: int):
        self.assertEqual(obj.total_samples, last - first)
        self.assertEqual(list(obj.time), list(full.time[first:last]))
        self.assertEqual(_channel_values(obj),
                         [values[first:last] for values in _channel_values(full)])

    def test_window(self):
        for files in PARTIAL_LOADING_FILES:
            with self.subTest(files=files):
                full = self.load(*files)
                n = full.total_samples
                first, last = n // 4, n // 2
                obj = self.load(*files, start_time=full.time[first],
                                end_time=full.time[last])
                self.assertWindow(obj, full, first, last + 1)

    def test_start_or_end_only(self):
        for files in PARTIAL_LOADING_FILES:
            with self.subTest(files=files):
                full = self.load(*files)
                n = full.total_samples
                obj = self.load(*files, start_time=full.time[n // 2])
                self.assertWindow(obj, full, n // 2, n)
                obj = self.load(*files, end_time=full.time[n // 3])
                self.assertWindow(obj, full, 0, n // 3 + 1)

    def test_between_samples(self):
        full = self.load("tests/sample_files/sample_bin.cfg")
        t = list(full.time)
        obj = self.load("tests/sample_files/sample_bin.cfg",
                        start_time=(t[0] + t[1]) / 2, end_time=(t[2] + t[3]) / 2)
        self.assertWindow(obj, full, 1, 3)

    def test_empty_window(self):
        for files in PARTIAL_LOADING_FILES:
            with self.subTest(files=files):
                obj = self.load(*files, start_time=1000.0)
                self.assertEqual(obj.total_samples, 0)
                self.assertEqual(len(obj.time), 0)
                self.assertTrue(all(len(values) == 0
                                    for values in _channel_values(obj)))

    def test_read_window(self):
        # Comtrade.read with multiple sample rates: 1000 Hz up to sample 4,
        # then 500 Hz
        for dat_format in ("ASCII", "BINARY"):
            with self.subTest(format=dat_format):
                rows = [(n, 0, n % 2) for n in range(1, 7)]
                if dat_format == "ASCII":
                    dat = "".join("{0},{1},{0},{2}\n".format(*row) for row in rows)
                else:
                    dat = b"".join(struct.pack("<IIhH", n, ts, n, status)
                                   for n, ts, status in rows)
                obj = Comtrade(ignore_warnings=True,
                               use_numpy_arrays=self.use_numpy_arrays)
                obj.read(COMTRADE_SAMPLE_5_CFG.format(format=dat_format), dat,
                         start_time=0.0025, end_time=0.006)
                self.assertEqual(list(obj.analog[0]), [4, 5])
                self.assertEqual(list(obj.status[0]), [0, 1])
                for t, expected in zip(obj.time, [0.003, 0.005]):
                    self.assertAlmostEqual(t, expected, places=6)


@unittest.skipUnless(comtrade._HAS_NUMPY, "numpy is not installed")
class TestTimeWindowLoadingNumpy(TestTimeWindowLoading):
    use_numpy_arrays = True


class TestLazyLoading(unittest.TestCase):
    """Binary DAT files values decoded when first accessed."""
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        for ext in ("cfg", "dat"):
            shutil.copy(f"tests/sample_files/sample_bin.{ext}",
                        os.path.join(self.tmp_dir, f"sample.{ext}"))
        self.cfg_path = os.path.join(self.tmp_dir, "sample.cfg")
        self.full = Comtrade(ignore_warnings=True).load(self.cfg_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_values(self):
        with Comtrade(ignore_warnings=True).load(self.cfg_path, lazy=True) as obj:
            self.assertEqual(len(obj.analog), self.full.analog_count)
            self.assertEqual(list(obj.time), list(self.full.time))
            self.assertEqual(_channel_values(obj), _channel_values(self.full))

    def test_decoded_when_accessed(self):
        with Comtrade(ignore_warnings=True).load(self.cfg_path, lazy=True) as obj:
            count = len(obj.analog)

            def decoded():
                return [values is not None for values in obj.analog._values]

            self.assertEqual(decoded(), [False] * count)
            values = obj.analog[1]
            self.assertIs(obj.analog[1], values)
            self.assertEqual(decoded(), [i == 1 for i in range(count)])
            self.assertIs(obj.analog[-1], obj.analog[count - 1])
            self.assertEqual(decoded(), [i in (1, count - 1) for i in range(count)])
            self.assertEqual(list(values), list(self.full.analog[1]))

    def test_slices(self):
        with Comtrade(ignore_warnings=True).load(self.cfg_path, lazy=True) as obj:
            self.assertEqual([list(v) for v in obj.status[1:3]],
                             [list(v) for v in self.full.status[1:3]])

    def test_closed(self):
        obj = Comtrade(ignore_warnings=True).load(self.cfg_path, lazy=True)
        first = list(obj.analog[0])
        obj.close()
        # values decoded before closing are kept
        self.assertEqual(list(obj.analog[0]), first)
        with self.assertRaises(comtrade.ComtradeError):
            obj.analog[1]
        # the file is released
        os.remove(os.path.join(self.tmp_dir, "sample.dat"))

    def test_reload_closes_file(self):
        obj = Comtrade(ignore_warnings=True).load(self.cfg_path, lazy=True)
        obj.load("tests/sample_files/sample_ascii.cfg")
        os.remove(os.path.join(self.tmp_dir, "sample.dat"))

    def test_eager_loading_releases_file(self):
        Comtrade(ignore_warnings=True).load(self.cfg_path, start_time=0.0)
        os.remove(os.path.join(self.tmp_dir, "sample.dat"))

    def test_lazy_time_window(self):
        t = list(self.full.time)
        with comtrade.load(self.cfg_path, ignore_warnings=True, lazy=True,
                           start_time=t[1], end_time=t[3]) as obj:
            self.assertEqual(list(obj.analog[0]), list(self.full.analog[0][1:4]))
            self.assertEqual(list(obj.status[0]), list(self.full.status[0][1:4]))

    def test_cff(self):
        full = Comtrade(ignore_warnings=True).load("tests/sample_files/sample_float32.cff")
        with comtrade.load("tests/sample_files/sample_float32.cff",
                           ignore_warnings=True, lazy=True) as obj:
            self.assertIsInstance(obj.analog, comtrade._LazyChannels)
            self.assertEqual(_channel_values(obj), _channel_values(full))

    def test_ascii_loads_eagerly(self):
        obj = comtrade.load("tests/sample_files/sample_ascii.cfg",
                            ignore_warnings=True, lazy=True)
        self.assertIsInstance(obj.analog, list)

    def test_scaled_values(self):
        with Comtrade(ignore_warnings=True).load(self.cfg_path, lazy=True) as obj:
            self.assertEqual([list(v) for v in obj.analog_primary],
                             [list(v) for v in self.full.analog_primary])


WRITE_FORMATS = ("ASCII", "BINARY", "BINARY32", "FLOAT32")
# maximum relative error (to the channel's largest value) of each format
WRITE_FORMAT_TOLERANCE = {"ASCII": 1E-5, "BINARY": 2E-5, "BINARY32": 1E-6,
                          "FLOAT32": 1E-6}


class TestSaving(unittest.TestCase):
    """Saving loaded files and reading them back."""
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def path(self, name: str) -> str:
        return os.path.join(self.tmp_dir, name)

    def assert_same_data(self, expected, actual, tolerance: float):
        self.assertEqual(actual.analog_channel_ids, expected.analog_channel_ids)
        self.assertEqual(actual.status_channel_ids, expected.status_channel_ids)
        self.assertEqual(actual.station_name, expected.station_name)
        self.assertEqual(actual.frequency, expected.frequency)
        self.assertEqual(actual.start_timestamp_ns, expected.start_timestamp_ns)
        self.assertEqual(actual.trigger_timestamp_ns, expected.trigger_timestamp_ns)
        self.assertEqual(actual.total_samples, expected.total_samples)
        for t_expected, t_actual in zip(expected.time, actual.time):
            self.assertAlmostEqual(t_actual, t_expected, places=6)
        for values_expected, values_actual in zip(expected.analog, actual.analog):
            scale = max(abs(v) for v in values_expected if not math.isnan(v)) or 1
            for v_expected, v_actual in zip(values_expected, values_actual):
                if math.isnan(v_expected):
                    self.assertTrue(math.isnan(v_actual))
                else:
                    self.assertLessEqual(abs(v_actual - v_expected) / scale, tolerance)
        self.assertEqual([list(v) for v in actual.status],
                         [list(v) for v in expected.status])

    def test_formats_round_trip(self):
        for source in ("tests/sample_files/sample_ascii.cfg",
                       "tests/sample_files/sample_bin.cfg",
                       "tests/sample_files/sample_float32.cff"):
            original = comtrade.load(source, ignore_warnings=True)
            for ft in WRITE_FORMATS:
                for ext in ("cfg", "cff"):
                    with self.subTest(source=source, ft=ft, ext=ext):
                        path = self.path("saved." + ext)
                        original.save(path, ft=ft, rev_year="2013")
                        saved = comtrade.load(path, ignore_warnings=True)
                        self.assertEqual(saved.ft, ft)
                        self.assertEqual(saved.cfg.sample_rates,
                                         original.cfg.sample_rates)
                        self.assert_same_data(original, saved,
                                              WRITE_FORMAT_TOLERANCE[ft])

    def test_same_format_keeps_raw_values(self):
        original = comtrade.load(COMTRADE_SAMPLE_4_CFG_FILE, ignore_warnings=True)
        original.save(self.path("saved.cfg"))
        saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
        self.assertEqual(saved.rev_year, "1999")
        self.assertEqual([c.a for c in saved.cfg.analog_channels],
                         [c.a for c in original.cfg.analog_channels])
        self.assertEqual(_channel_values(saved), _channel_values(original))
        with open(COMTRADE_SAMPLE_4_DAT_FILE, "rb") as file:
            original_rows = file.read()
        with open(self.path("saved.dat"), "rb") as file:
            saved_rows = file.read()
        # same rows, except the timestamps (zero in the original file)
        row_size = 4 + 4 + 4 * 2 + 2
        self.assertEqual(len(saved_rows), len(original_rows))
        for k in range(0, len(saved_rows), row_size):
            self.assertEqual(saved_rows[k + 8:k + row_size],
                             original_rows[k + 8:k + row_size])

    def test_cfg_contents(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        obj.save(self.path("saved.cfg"))
        with open(self.path("saved.cfg"), "rb") as file:
            lines = file.read().decode().split("\r\n")
        self.assertEqual(lines[0], "STATION_NAME,EQUIPMENT,2001")
        self.assertEqual(lines[1], "2,1A,1D")
        self.assertEqual(lines[2], "1,IA,,,A,2.762,0,0,-32768,32767,1,1,S")
        self.assertEqual(lines[3], "1,Diff Trip A,,,0")
        # non-uniformly sampled: no fixed sample rate
        self.assertEqual(lines[4:8], ["60", "0", "0,2",
                                      "01/01/2000,10:30:00.228000"])
        self.assertEqual(lines[8:12], ["01/01/2000,10:30:00.722000",
                                       "ASCII", "1", ""])
        with open(self.path("saved.dat")) as file:
            self.assertEqual(file.read(), "1,0,0,0\n2,347,-1,1\n")

    def test_missing_values(self):
        for source in ("tests/sample_files/sample_ascii.cfg",
                       "tests/sample_files/sample_bin.cfg"):
            dat = source[:-4] + "_missing.dat"
            original = comtrade.load(source, dat, ignore_warnings=True)
            self.assertTrue(any(math.isnan(v) for v in original.analog[0]))
            for ft in WRITE_FORMATS:
                with self.subTest(source=source, ft=ft):
                    original.save(self.path("saved.cfg"), ft=ft, rev_year="2013")
                    saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
                    self.assert_same_data(original, saved, WRITE_FORMAT_TOLERANCE[ft])

    def test_float32_missing_marker(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        obj.analog[0][1] = float("nan")
        obj.save(self.path("saved.cfg"), ft="FLOAT32", rev_year="2013")
        with open(self.path("saved.dat"), "rb") as file:
            rows = list(struct.iter_unpack("<IIfH", file.read()))
        self.assertEqual(rows[1][2], struct.unpack("<f", b"\xff\xff\x7f\xff")[0])
        saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
        self.assertTrue(math.isnan(saved.analog[0][1]))

    def test_time_window(self):
        full = comtrade.load("tests/sample_files/sample_ascii.cfg",
                             ignore_warnings=True)
        start_time = full.time[10]
        obj = comtrade.load("tests/sample_files/sample_ascii.cfg",
                            ignore_warnings=True, start_time=start_time,
                            end_time=full.time[19])
        obj.save(self.path("window.cfg"))
        saved = comtrade.load(self.path("window.cfg"), ignore_warnings=True)
        self.assertEqual(saved.total_samples, 10)
        self.assertEqual(saved.cfg.sample_rates, [[1200.0, 10]])
        self.assertEqual(saved.start_timestamp_ns - full.start_timestamp_ns,
                         round(start_time * 1E6) * 1000)
        self.assertEqual(saved.trigger_timestamp_ns, full.trigger_timestamp_ns)
        self.assertEqual(_channel_values(saved)[1:],
                         [list(v)[10:20] for v in full.analog + full.status])

    def test_multiple_sample_rates(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_5_CFG.format(format="ASCII"),
                 COMTRADE_SAMPLE_5_DAT)
        obj.save(self.path("saved.cfg"), ft="BINARY")
        saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
        self.assertEqual(saved.cfg.sample_rates, obj.cfg.sample_rates)
        self.assertEqual(list(saved.time), list(obj.time))

    def test_nanoseconds_and_time_codes(self):
        cfg_text = COMTRADE_SAMPLE_3_CFG.format(samples=2, seconds=0.000001500,
                                                format="ASCII")
        cfg_text = cfg_text + "-3h30,+2\nA,1\n"
        obj = Comtrade(ignore_warnings=True)
        obj.read(cfg_text, "1,0,1,0\n2,1,2,1\n")
        obj.save(self.path("saved.cfg"), ft="BINARY32")
        saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
        self.assertEqual(saved.time_base, Comtrade(ignore_warnings=True).cfg.TIME_BASE_NANO_SEC)
        self.assertEqual(saved.trigger_timestamp_ns, obj.trigger_timestamp_ns)
        self.assertEqual((saved.cfg.time_code, saved.cfg.local_code), ("-3h30", "+2"))
        self.assertEqual((saved.cfg.tmq_code, saved.cfg.leap_second), (10, 1))

    def test_hdr_and_inf(self):
        obj = comtrade.load("tests/sample_files/sample_ascii.cff", ignore_warnings=True)
        obj._inf = "[Public Record_Information]\nSource=Test"
        obj._hdr = "Header text"
        obj.save(self.path("saved.CFG"))
        self.assertTrue(os.path.isfile(self.path("saved.DAT")))
        saved = comtrade.load(self.path("saved.CFG"), ignore_warnings=True)
        self.assertEqual(saved.hdr, "Header text")
        self.assertEqual(saved.inf_sections()["Public Record_Information"]["Source"], "Test")
        obj.save(self.path("saved.cff"), ft="FLOAT32")
        saved = comtrade.load(self.path("saved.cff"), ignore_warnings=True)
        self.assertEqual(saved.hdr, "Header text")
        self.assertEqual(saved.inf_sections()["Public Record_Information"]["Source"], "Test")

    def test_lazy_loaded(self):
        with comtrade.load(COMTRADE_SAMPLE_4_CFG_FILE, ignore_warnings=True,
                           lazy=True) as obj:
            obj.save(self.path("saved.cfg"), ft="FLOAT32", rev_year="2013")
            values = _channel_values(obj)
        saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
        self.assertEqual(_channel_values(saved), values)

    def test_large_timestamps_use_time_multiplier(self):
        obj = Comtrade(ignore_warnings=True)
        obj.read(COMTRADE_SAMPLE_1_CFG, COMTRADE_SAMPLE_1_DAT)
        obj._time_values = array.array("d", [0.0, 5000.0])
        obj.save(self.path("saved.cfg"), ft="BINARY")
        saved = comtrade.load(self.path("saved.cfg"), ignore_warnings=True)
        self.assertEqual(saved.cfg.timemult, 2.0)
        self.assertEqual(list(saved.time), [0.0, 5000.0])

    def test_invalid_options(self):
        obj = comtrade.load("tests/sample_files/sample_ascii.cfg", ignore_warnings=True)
        with self.assertRaises(comtrade.ComtradeError):
            obj.save(self.path("saved.cfg"), rev_year="1991")
        with self.assertRaises(comtrade.ComtradeError):
            obj.save(self.path("saved.cfg"), ft="FLOAT32", rev_year="1999")
        with self.assertRaises(comtrade.ComtradeError):
            obj.save(self.path("saved.cff"), rev_year="1999")
        with self.assertRaises(comtrade.ComtradeError):
            obj.save(self.path("saved.cfg"), ft="FLOAT64")
        with self.assertRaises(comtrade.ComtradeError):
            obj.save(self.path("saved.txt"))
        obj.cfg.analog_channels[0].name = "I,A"
        with self.assertRaises(comtrade.ComtradeError):
            obj.save(self.path("saved.cfg"))


@unittest.skipUnless(comtrade._HAS_PANDAS, "pandas is not installed")
class TestFromDataFrame(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cfg_path = os.path.join(self.tmp_dir, "df.cfg")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_seconds_index(self):
        pd = comtrade.pd
        df = pd.DataFrame({"IA": [0.0, 120.5, float("nan"), -310.25],
                           "VA": [13800.0, 0.0, -13800.0, 0.0],
                           "TRIP": [False, False, True, True]},
                          index=[0.0, 0.00025, 0.0005, 0.00075])
        obj = comtrade.from_dataframe(
            df, station_name="SUB", rec_dev_id="REL1", frequency=60,
            start_timestamp=dt.datetime(2024, 3, 5, 10, 0, 0), trigger_time=0.0005,
            channels={"IA": {"uu": "A", "ph": "A", "primary": 600.0, "secondary": 5.0},
                      "TRIP": {"y": 1}})
        self.assertEqual(obj.analog_channel_ids, ["IA", "VA"])
        self.assertEqual(obj.status_channel_ids, ["TRIP"])
        self.assertEqual(obj.cfg.sample_rates, [[4000.0, 4]])
        self.assertAlmostEqual(obj.trigger_time, 0.0005)
        for ft in WRITE_FORMATS:
            with self.subTest(ft=ft):
                obj.save(self.cfg_path, ft=ft)
                saved = comtrade.load(self.cfg_path, ignore_warnings=True)
                self.assertEqual((saved.station_name, saved.rec_dev_id, saved.rev_year),
                                 ("SUB", "REL1", "2013"))
                self.assertEqual(saved.frequency, 60.0)
                self.assertEqual(saved.start_timestamp, dt.datetime(2024, 3, 5, 10, 0, 0))
                self.assertEqual(saved.trigger_timestamp,
                                 dt.datetime(2024, 3, 5, 10, 0, 0, 500))
                channel = saved.cfg.analog_channels[0]
                self.assertEqual((channel.uu, channel.ph, channel.primary,
                                  channel.secondary), ("A", "A", 600.0, 5.0))
                self.assertEqual(saved.cfg.status_channels[0].y, 1)
                self.assertEqual(list(saved.status[0]), [0, 0, 1, 1])
                for t_expected, t_actual in zip(obj.time, saved.time):
                    self.assertAlmostEqual(t_actual, t_expected, places=9)
                for expected, actual in zip(obj.analog, saved.analog):
                    for v_expected, v_actual in zip(expected, actual):
                        if math.isnan(v_expected):
                            self.assertTrue(math.isnan(v_actual))
                        else:
                            self.assertAlmostEqual(v_actual, v_expected,
                                                   delta=13800 * WRITE_FORMAT_TOLERANCE[ft])

    def test_datetime_index(self):
        pd = comtrade.pd
        index = pd.date_range("2024-03-05 10:00:00.000000250", periods=3,
                              freq="1ms", tz="America/Sao_Paulo")
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0]}, index=index)
        obj = comtrade.from_dataframe(df, trigger_timestamp=index[1], ft="BINARY")
        obj.save(self.cfg_path)
        saved = comtrade.load(self.cfg_path, ignore_warnings=True)
        self.assertEqual(saved.ft, "BINARY")
        self.assertEqual(saved.start_timestamp_ns, index[0].tz_localize(None).value)
        self.assertEqual(saved.trigger_timestamp_ns, index[1].tz_localize(None).value)
        self.assertEqual(saved.cfg.time_code, "-3")
        self.assertEqual(saved.start_timestamp_utc,
                         dt.datetime(2024, 3, 5, 13, 0, tzinfo=dt.timezone.utc))
        self.assertEqual(saved.cfg.sample_rates, [[1000.0, 3]])

    def test_timedelta_index_not_uniform(self):
        pd = comtrade.pd
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0]},
                          index=pd.to_timedelta([0, 100, 350], unit="ms"))
        obj = comtrade.from_dataframe(df)
        obj.save(self.cfg_path)
        saved = comtrade.load(self.cfg_path, ignore_warnings=True)
        self.assertTrue(saved.cfg.timestamp_critical)
        self.assertEqual([round(t, 6) for t in saved.time], [0.0, 0.1, 0.35])

    def test_to_dataframe_round_trip(self):
        original = comtrade.load("tests/sample_files/sample_ascii.cfg",
                                 ignore_warnings=True)
        for index_type in ("time", "sample"):
            with self.subTest(index_type=index_type):
                df = original.to_dataframe(index_type=index_type)
                obj = comtrade.from_dataframe(df, start_timestamp=original.start_timestamp)
                self.assertEqual(obj.analog_channel_ids, original.analog_channel_ids)
                self.assertEqual(obj.status_channel_ids, original.status_channel_ids)
                obj.save(self.cfg_path, ft="FLOAT32")
                saved = comtrade.load(self.cfg_path, ignore_warnings=True)
                self.assertEqual(saved.cfg.sample_rates, original.cfg.sample_rates)
                self.assertEqual(_channel_values(saved), _channel_values(original))

    def test_sample_rate_and_status_columns(self):
        pd = comtrade.pd
        df = pd.DataFrame({"tap": [0, 1, 1], "breaker": [1.0, 0.0, 1.0]})
        obj = comtrade.from_dataframe(df, sample_rate=960, status_columns=["breaker"])
        self.assertEqual(obj.analog_channel_ids, ["tap"])
        self.assertEqual(obj.status_channel_ids, ["breaker"])
        self.assertEqual(obj.cfg.sample_rates, [[960.0, 3]])
        self.assertEqual(list(obj.status[0]), [1, 0, 1])

    def test_missing_time_values(self):
        df = comtrade.pd.DataFrame({"x": [1.0, 2.0]})
        with self.assertRaises(comtrade.ComtradeError):
            comtrade.from_dataframe(df)
        df = comtrade.pd.DataFrame({"x": [1.0, 2.0]}, index=[1.0, 0.5])
        with self.assertRaises(comtrade.ComtradeError):
            comtrade.from_dataframe(df)


if __name__ == "__main__":
    unittest.main()
