# -*- coding: utf-8 -*-
# MIT License

# Copyright (c) 2018 David Rodrigues Parrini

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import datetime as dt
import errno
import io
import math
import os
import re
import struct
import sys
import warnings


# COMTRADE standard revisions
REV_1991 = "1991"
REV_1999 = "1999"
REV_2013 = "2013"

# DAT file format types
TYPE_ASCII = "ASCII"
TYPE_BINARY = "BINARY"
TYPE_BINARY32 = "BINARY32"
TYPE_FLOAT32 = "FLOAT32"

# Special values
TIMESTAMP_MISSING = 0xFFFFFFFF

# CFF headers
CFF_HEADER_REXP = "(?i)--- file type: ([a-z]+)(?:\\s([a-z]+))? ---$"

# common separator character of data fields of CFG and ASCII DAT files
SEPARATOR = ","

# timestamp regular expression
re_dt = re.compile("([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4}),([0-9]{2}):([0-9]{2}):([0-9]{2})\\.([0-9]{5,12})")

# Non-standard revision warning
WARNING_UNKNOWN_REVISION = "Unknown standard revision \"{}\""
# Date time with nanoseconds resolution warning
WARNING_DATETIME_NANO = "Unsupported datetime objects with nanoseconds \
resolution. Using truncated values."


def _read_sep_values(line, expected: int = -1, default: str = ''):
    values = line.strip().split(SEPARATOR)
    if expected == -1 or len(values) == expected:
        return values
    return [values[i] if i < len(values) else default
            for i in range(expected)]


def _prevent_null(str_value: str, value_type: type, default_value):
    if len(str_value.strip()) == 0:
        return default_value
    else:
        return value_type(str_value)


def _read_timestamp(timestamp: str, ignore_warnings=False) -> dt.datetime:
    m = re_dt.match(timestamp)
    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3))
    hour = int(m.group(4))
    minute = int(m.group(5))
    second = int(m.group(6))
    frac_second = int(m.group(7))
    in_nanoseconds = len(m.group(7)) > 6

    # timezone information
    tzinfo = None
    microsecond = frac_second
    if in_nanoseconds:
        # Nanoseconds resolution is not supported by datetime module, so it's
        # converted to integer below.
        if not ignore_warnings:
            warnings.warn(Warning(WARNING_DATETIME_NANO))
        microsecond = int(microsecond * 1E-3)

    return dt.datetime(year, month, day, hour, minute, second, 
                       microsecond, tzinfo)


class Cfg:
    """Parses and stores Comtrade's CFG data."""
    # time base units
    TIME_BASE_NANOSEC = 1E-9
    TIME_BASE_MICROSEC = 1E-6

    def __init__(self, **kwargs):
        """
        Cfg object constructor.

        Keyword arguments:
        ignore_warnings -- whether warnings are displayed in stdout 
            (default: False)
        """
        self.filename = ""
        # implicit data
        self._time_base = self.TIME_BASE_MICROSEC

        # Default CFG data
        self._station_name = ""
        self._rec_dev_id = ""
        self._rev_year = 2013
        self._channels_count = 0
        self._analog_channels = []
        self._status_channels = []
        self._analog_count = 0
        self._status_count = 0
        self._frequency = 60.0
        self._nrates = 1
        self._sample_rates = []
        self._timestamp_critical = False
        self._start_timestamp = dt.datetime(1900, 1, 1)
        self._trigger_timestamp = dt.datetime(1900, 1, 1)
        self._ft = TYPE_ASCII
        self._time_multiplier = 1.0
        # 2013 standard revision information
        # time_code,local_code = 0,0 means local time is UTC
        self._time_code = 0
        self._local_code = 0
        # tmq_code,leapsec
        self._tmq_code = 0
        self._leap_second = 0

        if "ignore_warnings" in kwargs:
            self.ignore_warnings = kwargs["ignore_warnings"]
        else:
            self.ignore_warnings = False

    @property
    def station_name(self) -> str:
        """Return the recording device's station name."""
        return self._station_name
    
    @property
    def rec_dev_id(self) -> str:
        """Return the recording device id."""
        return self._rec_dev_id

    @property
    def rev_year(self) -> int:
        """Return the COMTRADE revision year."""
        return self._rev_year

    @property
    def channels_count(self) -> int:
        """Return the number of channels, total."""
        return self._channels_count

    @property
    def analog_channels(self) -> list:
        """Return the analog channels list with complete channel description."""
        return self._analog_channels

    @property
    def status_channels(self) -> list:
        """Return the status channels list with complete channel description."""
        return self._status_channels
    
    @property
    def analog_count(self) -> int:
        """Return the number of analog channels."""
        return self._analog_count
    
    @property
    def status_count(self) -> int:
        """Return the number of status channels."""
        return self._status_count
    
    @property
    def time_base(self) -> float:
        """Return the time base."""
        return self._time_base

    @property
    def frequency(self) -> float:
        """Return the measured line frequency in Hertz."""
        return self._frequency
    
    @property
    def ft(self) -> str:
        """Return the expected DAT file format."""
        return self._ft
    
    @property
    def timemult(self) -> float:
        """Return the DAT time multiplier (Default = 1)."""
        return self._time_multiplier

    @property
    def timestamp_critical(self) -> bool:
        """Returns whether the DAT file must contain non-zero
         timestamp values."""
        return self._timestamp_critical
    
    @property
    def start_timestamp(self) -> dt.datetime:
        """Return the recording start time stamp as a datetime object."""
        return self._start_timestamp
    
    @property
    def trigger_timestamp(self) -> dt.datetime:
        """Return the trigger time stamp as a datetime object."""
        return self._trigger_timestamp
    
    @property
    def nrates(self) -> int:
        """Return the number of different sample rates within the DAT file."""
        return self._nrates
    
    @property
    def sample_rates(self) -> list:
        """
        Return a list with pairs describing the number of samples for a given
        sample rate.
        """ 
        return self._sample_rates

    # Deprecated properties - Changed "Digital" for "Status"
    @property
    def digital_channels(self) -> list:
        """Returns the status channels bidimensional values list."""
        if not self.ignore_warnings:
            warnings.warn(FutureWarning("digital_channels is deprecated, "
                                        "use status_channels instead."))
        return self._status_channels

    @property
    def digital_count(self) -> int:
        """Returns the number of status channels."""
        if not self.ignore_warnings:
            warnings.warn(FutureWarning("digital_count is deprecated, "
                                        "use status_count instead."))
        return self._status_count

    def load(self, filepath):
        """Load and read a CFG file contents."""
        self.filepath = filepath

        if os.path.isfile(self.filepath):
            with open(self.filepath, "r") as cfg:
                self._read_io(cfg)
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), 
                                    self.filepath)

    def read(self, cfg_lines):
        """Read CFG-format data of a FileIO or StringIO object."""
        if type(cfg_lines) is str:
            self._read_io(io.StringIO(cfg_lines))
        else:
            self._read_io(cfg_lines)

    def _read_io(self, cfg):
        """Read CFG-format lines and stores its data."""
        line_count = 0
        self._nrates = 1
        self._sample_rates = []
        self._analog_channels = []
        self._status_channels = []

        # First line
        line = cfg.readline()
        # station, device, and comtrade standard revision information
        packed = _read_sep_values(line)
        if 3 == len(packed):
            # only 1999 revision and above has the standard revision year
            self._station_name, self._rec_dev_id, self._rev_year = packed
            self._rev_year = self._rev_year.strip()

            if self._rev_year not in (REV_1991, REV_1999, REV_2013):
                if not self.ignore_warnings:
                    msg = WARNING_UNKNOWN_REVISION.format(self._rev_year)
                    warnings.warn(Warning(msg))
        else:
            self._station_name, self._rec_dev_id = packed
            self._rev_year = REV_1999
        line_count = line_count + 1

        # Second line
        line = cfg.readline()
        # number of channels and its type
        totchn, achn, schn = _read_sep_values(line, 3, '0')
        self._channels_count = int(totchn)
        self._analog_count = int(achn[:-1])
        self._status_count = int(schn[:-1])
        self._analog_channels = [None]*self._analog_count
        self._status_channels = [None]*self._status_count
        line_count = line_count + 1

        # Analog channel description lines
        for ichn in range(self._analog_count):
            line = cfg.readline()
            packed = _read_sep_values(line, 13, '0')
            # unpack values
            n, name, ph, ccbm, uu, a, b, skew, cmin, cmax, \
                primary, secondary, pors = packed
            # type conversion
            n = int(n)
            a = float(a)
            b = _prevent_null(b, float, 0.0)
            skew = _prevent_null(skew, float, 0.0)
            cmin = int(cmin)
            cmax = int(cmax)
            primary = float(primary)
            secondary = float(secondary)
            self.analog_channels[ichn] = AnalogChannel(n, a, b, skew, 
                cmin, cmax, name, uu, ph, ccbm, primary, secondary, pors)
            line_count = line_count + 1

        # Status channel description lines
        for ichn in range(self._status_count):
            line = cfg.readline()
            # unpack values
            packed = _read_sep_values(line, 5, '0')
            n, name, ph, ccbm, y = packed
            # type conversion
            n = int(n)
            y = int(y)
            self.status_channels[ichn] = StatusChannel(n, name, ph, ccbm, y)
            line_count = line_count + 1

        # Frequency line
        line = cfg.readline()
        self._frequency = float(line.strip())
        line_count = line_count + 1

        # Nrates line
        # number of different sample rates
        line = cfg.readline()
        self._nrates = int(line.strip())
        if self._nrates == 0:
            self._nrates = 1
            self._timestamp_critical = True
        else:
            self._timestamp_critical = False
        line_count = line_count + 1

        for inrate in range(self._nrates):
            line = cfg.readline()
            # each sample rate
            samp, endsamp = _read_sep_values(line)
            samp = float(samp)
            endsamp = int(endsamp)
            self.sample_rates.append([samp, endsamp])
            line_count = line_count + 1

        # First data point time and time base
        line = cfg.readline()
        ts_str = line.strip()
        self._start_timestamp = _read_timestamp(ts_str, self.ignore_warnings)
        self._time_base = self._get_time_base(ts_str)
        line_count = line_count + 1

        # Event data point and time base
        line = cfg.readline()
        ts_str = line.strip()
        self._trigger_timestamp = _read_timestamp(ts_str, self.ignore_warnings)
        self._time_base = min([self.time_base, self._get_time_base(ts_str)])
        line_count = line_count + 1

        # DAT file type
        line = cfg.readline()
        self._ft = line.strip()
        line_count = line_count + 1

        # Timestamp multiplication factor
        if self._rev_year in (REV_1999, REV_2013):
            line = cfg.readline().strip()
            if len(line) > 0:
                self._time_multiplier = float(line)
            else:
                self._time_multiplier = 1.0
            line_count = line_count + 1

        # time_code and local_code
        if self._rev_year == REV_2013:
            line = cfg.readline()

            if line:
                self._time_code, self._local_code = _read_sep_values(line)
                line_count = line_count + 1

                line = cfg.readline()
                # time_code and local_code
                self._tmq_code, self._leap_second = _read_sep_values(line)
                line_count = line_count + 1

    def _get_time_base(self, timestamp):
        """
        Return the time base, which is based on the fractionary part of the 
        seconds in a timestamp (00.XXXXX).
        """
        match = re_dt.match(timestamp)
        in_nanoseconds = len(match.group(7)) > 6
        if in_nanoseconds:
            return self.TIME_BASE_NANOSEC
        else:
            return self.TIME_BASE_MICROSEC


class Comtrade:
    """Parses and stores Comtrade data."""
    # extensions
    EXT_CFG = "cfg"
    EXT_DAT = "dat"
    EXT_INF = "inf"
    EXT_HDR = "hdr"
    # format specific
    ASCII_SEPARATOR = ","
    
    def __init__(self, **kwargs):
        """
        Comtrade object constructor.

        Keyword arguments:
        ignore_warnings -- whether warnings are displayed in stdout 
            (default: False).
        """
        self.filename = ""

        self._cfg = Cfg(**kwargs)

        # Default CFG data
        self._analog_channel_ids = []
        self._analog_phases = []
        self._status_channel_ids = []
        self._status_phases = []
        self._timestamp_critical = False

        # DAT file data
        self._time_values = []
        self._analog_values = []
        self._status_values = []

        # Additional CFF data (or additional comtrade files)
        self._hdr = None
        self._inf = None

        if "ignore_warnings" in kwargs:
            self.ignore_warnings = kwargs["ignore_warnings"]
        else:
            self.ignore_warnings = False

    @property
    def station_name(self) -> str:
        """Return the recording device's station name."""
        return self._cfg.station_name
    
    @property
    def rec_dev_id(self) -> str:
        """Return the recording device id."""
        return self._cfg.rec_dev_id

    @property
    def rev_year(self) -> int:
        """Return the COMTRADE revision year."""
        return self._cfg.rev_year

    @property
    def cfg(self) -> Cfg:
        """Return the underlying CFG class instance."""
        return self._cfg

    @property
    def hdr(self):
        """Return the HDR file contents."""
        return self._hdr
    
    @property
    def inf(self):
        """Return the INF file contents."""
        return self._inf

    @property
    def analog_channel_ids(self) -> list:
        """Returns the analog channels name list."""
        return self._analog_channel_ids
    
    @property
    def analog_phases(self) -> list:
        """Returns the analog phase name list."""
        return self._analog_phases
    
    @property
    def status_channel_ids(self) -> list:
        """Returns the status channels name list."""
        return self._status_channel_ids
    
    @property
    def status_phases(self) -> list:
        """Returns the status phase name list."""
        return self._status_phases

    @property
    def time(self) -> list:
        """Return the time values list."""
        return self._time_values

    @property
    def analog(self) -> list:
        """Return the analog channel values bidimensional list."""
        return self._analog_values
    
    @property
    def status(self) -> list:
        """Return the status channel values bidimensional list."""
        return self._status_values

    @property
    def total_samples(self) -> int:
        """Return the total number of samples (per channel)."""
        return self._total_samples

    @property
    def frequency(self) -> float:
        """Return the measured line frequency in Hertz."""
        return self._cfg.frequency

    @property
    def start_timestamp(self):
        """Return the recording start time stamp as a datetime object."""
        return self._cfg.start_timestamp

    @property
    def trigger_timestamp(self):
        """Return the trigger time stamp as a datetime object."""
        return self._cfg.trigger_timestamp

    @property
    def channels_count(self) -> int:
        """Return the number of channels, total."""
        return self._cfg.channels_count

    @property
    def analog_count(self) -> int:
        """Return the number of analog channels."""
        return self._cfg.analog_count

    @property
    def status_count(self) -> int:
        """Return the number of status channels."""
        return self._cfg.status_count

    @property
    def trigger_time(self) -> float:
        """Return relative trigger time in seconds."""
        stt = self._cfg.start_timestamp
        trg = self._cfg.trigger_timestamp
        tdiff = trg - stt
        tsec = (tdiff.days*60*60*24) + tdiff.seconds + (tdiff.microseconds*1E-6)
        return tsec

    @property
    def time_base(self) -> float:
        """Return the time base."""
        return self._cfg.time_base

    @property
    def ft(self) -> str:
        """Return the expected DAT file format."""
        return self._cfg.ft

    # Deprecated properties - Changed "Digital" for "Status"
    @property
    def digital_channel_ids(self) -> list:
        """Returns the status channels name list."""
        if not self.ignore_warnings:
            warnings.warn(FutureWarning("digital_channel_ids is deprecated, use status_channel_ids instead."))
        return self._status_channel_ids

    @property
    def digital(self) -> list:
        """Returns the status channels bidimensional values list."""
        if not self.ignore_warnings:
            warnings.warn(FutureWarning("digital is deprecated, use status instead."))
        return self._status_values

    @property
    def digital_count(self) -> int:
        """Returns the number of status channels."""
        if not self.ignore_warnings:
            warnings.warn(FutureWarning("digital_count is deprecated, use status_count instead."))
        return self._cfg.status_count

    def _get_dat_reader(self):
        # case insensitive comparison of file format
        dat = None
        ft_upper = self.ft.upper()
        if ft_upper == TYPE_ASCII:
            dat = AsciiDatReader()
        elif ft_upper == TYPE_BINARY:
            dat = BinaryDatReader()
        elif ft_upper == TYPE_BINARY32:
            dat = Binary32DatReader()
        elif ft_upper == TYPE_FLOAT32:
            dat = Float32DatReader()
        else:
            dat = None
            raise Exception("Not supported data file format: {}".format(self.ft))
        return dat

    def read(self, cfg_lines, dat_lines) -> None:
        """
        Read CFG and DAT files contents. Expects FileIO or StringIO objects.
        """
        self._cfg.read(cfg_lines)

        # channel ids
        self._cfg_extract_channels_ids(self._cfg)
        
        # channel phases
        self._cfg_extract_phases(self._cfg)

        dat = self._get_dat_reader()
        dat.read(dat_lines, self._cfg)

        # copy dat object information
        self._dat_extract_data(dat)

    def _cfg_extract_channels_ids(self, cfg) -> None:
        self._analog_channel_ids = [channel.name for channel in cfg.analog_channels]
        self._status_channel_ids = [channel.name for channel in cfg.status_channels]
        
    def _cfg_extract_phases(self, cfg) -> None:
        self._analog_phases = [channel.ph for channel in cfg.analog_channels]
        self._status_phases = [channel.ph for channel in cfg.status_channels]

    def _dat_extract_data(self, dat) -> None:
        self._time_values   = dat.time
        self._analog_values = dat.analog
        self._status_values = dat.status
        self._total_samples = dat.total_samples

    def load(self, cfg_file, dat_file = None, **kwargs) -> None:
        """
        Load CFG, DAT, INF, and HDR files. Each must be a FileIO or StringIO
        object. dat_file, inf_file, and hdr_file are optional (Default: None).

        cfg_file is the cfg file path, including its extension.
        dat_file is optional, and may be set if the DAT file name differs from 
            the CFG file name.

        Keyword arguments:
        inf_file -- optional INF file path (Default = None)
        hdr_file -- optional HDR file path (Default = None)
        """
        if "inf_file" in kwargs:
            inf_file = kwargs["inf_file"]
        else:
            inf_file = None

        if "hdr_file" in kwargs:
            hdr_file = kwargs["hdr_file"]
        else:
            hdr_file = None

        # which extension: CFG or CFF?
        file_ext = cfg_file[-3:].upper()
        if file_ext == "CFG":
            basename = cfg_file[:-3]
            # if not informed, infer dat_file with cfg_file
            if dat_file is None:
                dat_file = cfg_file[:-3] + self.EXT_DAT

            if inf_file is None:
                inf_file = basename + self.EXT_INF

            if hdr_file is None:
                hdr_file = basename + self.EXT_HDR

            # load both cfg and dat
            self._load_cfg_dat(cfg_file, dat_file)

            # Load additional inf and hdr files, if they exist.
            self._load_inf(inf_file)
            self._load_hdr(hdr_file)

        elif file_ext == "CFF":
            # check if the CFF file exists
            self._load_cff(cfg_file)
        else:
            raise Exception(r"Expected CFG file path, got intead \"{}\".".format(cfg_file))

    def _load_cfg_dat(self, cfg_filepath, dat_filepath):
        self._cfg.load(cfg_filepath)

        # channel ids
        self._cfg_extract_channels_ids(self._cfg)
        
        # channel phases
        self._cfg_extract_phases(self._cfg)

        dat = self._get_dat_reader()
        dat.load(dat_filepath, self._cfg)

        # copy dat object information
        self._dat_extract_data(dat)

    def _load_inf(self, inf_file):
        if os.path.exists(inf_file):
            with open(inf_file, 'r') as file:
                self._inf = file.read()
                if len(self._inf) == 0:
                    self._inf = None
        else:
            self._inf = None

    def _load_hdr(self, hdr_file):
        if os.path.exists(hdr_file):
            with open(hdr_file, 'r') as file:
                self._hdr = file.read()
                if len(self._hdr) == 0:
                    self._hdr = None
        else:
            self._hdr = None

    def _load_cff(self, cff_file_path: str):
        # stores each file type lines
        cfg_lines = []
        dat_lines = []
        hdr_lines = []
        inf_lines = []
        with open(cff_file_path, "r") as file:
            line_number = 0
            # file type: CFG, HDR, INF, DAT
            ftype = None
            # file format: ASCII, BINARY, BINARY32, FLOAT32
            fformat = None
            header_re = re.compile(CFF_HEADER_REXP)
            last_match = None
            for line in file:
                mobj = header_re.match(line.strip().upper())
                if mobj is not None:
                    last_match = mobj
                    ftype   = last_match.groups()[0]
                    fformat = last_match.groups()[1]
                    continue
                if last_match is not None and ftype == "CFG":
                    cfg_lines.append(line.strip())

                if last_match is not None and ftype == "DAT":
                    dat_lines.append(line.strip())

                if last_match is not None and ftype == "HDR":
                    hdr_lines.append(line.strip())

                if last_match is not None and ftype == "INF":
                    inf_lines.append(line.strip())
        
        # process CFF data
        self.read("\n".join(cfg_lines), "\n".join(dat_lines))

        # stores additional data
        self._hdr = "\n".join(hdr_lines)
        if len(self._hdr) == 0:
            self._hdr = None

        self._inf = "\n".join(inf_lines)
        if len(self._inf) == 0:
            self._inf = None

    def cfg_summary(self):
        """Returns the CFG attributes summary string."""
        header_line = "Channels (total,A,D): {}A + {}D = {}"
        sample_line = "Sample rate of {} Hz to the sample #{}"
        interval_line = "From {} to {} with time mult. = {}"
        format_line = "{} format"

        lines = [header_line.format(self.analog_count, self.status_count,
                                    self.channels_count),
                 "Line frequency: {} Hz".format(self.frequency)]
        for i in range(self._cfg.nrates):
            rate, points = self._cfg.sample_rates[i]
            lines.append(sample_line.format(rate, points))
        lines.append(interval_line.format(self.start_timestamp,
                                          self.trigger_timestamp,
                                          self._cfg.timemult))
        lines.append(format_line.format(self.ft))
        return "\n".join(lines)


class Channel:
    """Holds common channel description data."""
    def __init__(self, n=1, name='', ph='', ccbm=''):
        """Channel abstract class constructor."""
        self.n = n
        self.name = name
        self.ph = ph
        self.ccbm = ccbm

    def __str__(self):
        return ','.join([str(self.n), self.name, self.ph, self.ccbm])


class StatusChannel(Channel):
    """Holds status channel description data."""
    def __init__(self, n: int, name='', ph='', ccbm='', y=0):
        """StatusChannel class constructor."""
        super().__init__(n, name, ph, ccbm)
        self.name = name
        self.n = n
        self.name = name
        self.ph = ph
        self.ccbm = ccbm
        self.y = y

    def __str__(self):
        fields = [str(self.n), self.name, self.ph, self.ccbm, str(self.y)]


class AnalogChannel(Channel):
    """Holds analog channel description data."""
    def __init__(self, n: int, a: float, b=0.0, skew=0.0, cmin=-32767,
                 cmax=32767, name='', uu='', ph='', ccbm='', primary=1.0,
                 secondary=1.0, pors='P'):
        """AnalogChannel class constructor."""
        super().__init__(n, name, ph, ccbm)
        self.name = name
        self.uu = uu
        self.n = n
        self.a = a
        self.b = b
        self.skew = skew
        self.cmin = cmin
        self.cmax = cmax
        # misc
        self.uu = uu
        self.ph = ph
        self.ccbm = ccbm
        self.primary = primary
        self.secondary = secondary
        self.pors = pors

    def __str__(self):
        fields = [str(self.n), self.name, self.ph, self.ccbm, self.uu, 
            str(self.a), str(self.b), str(self.skew), str(self.cmin), 
            str(self.cmax), str(self.primary), str(self.secondary), self.pors]
        return ','.join(fields)


class DatReader:
    """Abstract DatReader class. Used to parse DAT file contents."""
    read_mode = "r"

    def __init__(self):
        """DatReader class constructor."""
        self.file_path = ""
        self._content = None
        self._cfg = None
        self.time = []
        self.analog = []
        self.status = []
        self._total_samples = 0

    @property
    def total_samples(self):
        """Return the total samples (per channel)."""
        return self._total_samples

    def load(self, dat_filepath, cfg):
        """Load a DAT file and parse its contents."""
        self.file_path = dat_filepath
        self._content = None
        if os.path.isfile(self.file_path):
            # extract CFG file information regarding data dimensions
            self._cfg = cfg
            self._preallocate()
            with open(self.file_path, self.read_mode) as contents:
                self.parse(contents)
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    self.file_path)

    def read(self, dat_lines, cfg):
        """
        Read a DAT file contents, expecting a list of string or FileIO object.
        """
        self.file_path = None
        self._content = dat_lines
        self._cfg = cfg
        self._preallocate()
        self.parse(dat_lines)

    def _preallocate(self):
        # read from the cfg file the number of samples in the dat file
        steps = self._cfg.sample_rates[-1][1]  # last samp field
        self._total_samples = steps

        # analog and status count
        analog_count = self._cfg.analog_count
        status_count = self._cfg.status_count

        # preallocate analog and status values
        self.time = [0.0] * steps
        self.analog = [None] * analog_count
        self.status = [None] * status_count
        # preallocate each channel values with zeros
        for i in range(analog_count):
            self.analog[i] = [0.0] * steps
        for i in range(status_count):
            self.status[i] = [0] * steps

    def _get_samp(self, n) -> float:
        """Get the sampling rate for a sample n (1-based index)."""
        # TODO: make tests.
        last_sample_rate = 1.0
        for samp, endsamp in self._cfg.sample_rates:
            if n <= endsamp:
                return samp
        return last_sample_rate

    def _get_time(self, n: int, ts_value: float, time_base: float,
                  time_multiplier: float):
        # TODO: add option to enforce dat file timestamp, when available.
        # TODO: make tests.
        ts = 0
        sample_rate = self._get_samp(n)
        if not self._cfg.timestamp_critical or ts_value == TIMESTAMP_MISSING:
            # if the timestamp is missing, use calculated.
            if sample_rate != 0.0:
                return (n - 1) / sample_rate
            else:
                raise Exception("Missing timestamp and no sample rate "
                                "provided.")
        else:
            # Use provided timestamp if its not missing
            return ts_value * time_base * time_multiplier

    def parse(self, contents):
        """Virtual method, parse DAT file contents."""
        pass


class AsciiDatReader(DatReader):
    """ASCII format DatReader subclass."""
    ASCII_SEPARATOR = SEPARATOR

    DATA_MISSING = ""

    def parse(self, contents):
        """Parse a ASCII file contents."""
        analog_count = self._cfg.analog_count
        status_count = self._cfg.status_count
        time_mult = self._cfg.timemult
        time_base = self._cfg.time_base

        # auxiliary vectors (channels gains and offsets)
        a = [x.a for x in self._cfg.analog_channels]
        b = [x.b for x in self._cfg.analog_channels]

        # extract lines
        if type(contents) is str:
            lines = contents.splitlines()
        else:
            lines = contents

        line_number = 0
        for line in lines:
            line_number = line_number + 1
            if line_number <= self._total_samples:
                values = line.strip().split(self.ASCII_SEPARATOR)

                n = int(values[0])
                # Read time
                ts_val = float(values[1])
                ts = self._get_time(n, ts_val, time_base, time_mult)

                avalues = [float(x)*a[i] + b[i] for i, x in enumerate(values[2:analog_count+2])]
                svalues = [int(x) for x in values[len(values)-status_count:]]

                # store
                self.time[line_number-1] = ts
                for i in range(analog_count):
                    self.analog[i][line_number - 1] = avalues[i]
                for i in range(status_count):
                    self.status[i][line_number - 1] = svalues[i]


class BinaryDatReader(DatReader):
    """16-bit binary format DatReader subclass."""
    ANALOG_BYTES = 2
    STATUS_BYTES = 2
    TIME_BYTES = 4
    SAMPLE_NUMBER_BYTES = 4

    # maximum negative value
    DATA_MISSING = 0xFFFF

    read_mode = "rb"

    if struct.calcsize("L") == 4:
        STRUCT_FORMAT = "LL {acount:d}h {dcount:d}H"
        STRUCT_FORMAT_ANALOG_ONLY = "LL {acount:d}h"
        STRUCT_FORMAT_STATUS_ONLY = "LL {dcount:d}H"
    else:
        STRUCT_FORMAT = "II {acount:d}h {dcount:d}H"
        STRUCT_FORMAT_ANALOG_ONLY = "II {acount:d}h"
        STRUCT_FORMAT_STATUS_ONLY = "II {dcount:d}H"

    def get_reader_format(self, analog_channels, status_bytes):
        # Number of status fields of 2 bytes based on the total number of 
        # bytes.
        dcount = math.floor(status_bytes / 2)
        
        # Check the file configuration
        if int(status_bytes) > 0 and int(analog_channels) > 0:
            return self.STRUCT_FORMAT.format(acount=analog_channels, 
                dcount=dcount)
        elif int(analog_channels) > 0:
            # Analog channels only.
            return self.STRUCT_FORMAT_ANALOG_ONLY.format(acount=analog_channels)
        else:
            # Status channels only.
            return self.STRUCT_FORMAT_STATUS_ONLY.format(acount=dcount)

    def parse(self, contents):
        """Parse DAT binary file contents."""
        time_mult = self._cfg.timemult
        time_base = self._cfg.time_base
        achannels = self._cfg.analog_count
        schannel = self._cfg.status_count

        # auxillary vectors (channels gains and offsets)
        a = [x.a for x in self._cfg.analog_channels]
        b = [x.b for x in self._cfg.analog_channels]

        sample_id_bytes = self.SAMPLE_NUMBER_BYTES + self.TIME_BYTES
        abytes = achannels*self.ANALOG_BYTES
        dbytes = self.STATUS_BYTES * math.ceil(schannel / 16.0)
        bytes_per_row = sample_id_bytes + abytes + dbytes
        groups_of_16bits = math.floor(dbytes / self.STATUS_BYTES)

        # Struct format.
        row_reader = struct.Struct(self.get_reader_format(achannels, dbytes))

        # Row reading function.
        next_row = None
        if isinstance(contents, io.TextIOBase) or \
                isinstance(contents, io.BufferedIOBase):
            def next_row(offset: int):
                return contents.read(bytes_per_row)

        elif isinstance(contents, str):
            def next_row(offset: int):
                return contents[offset:offset + bytes_per_row]
        else:
            raise TypeError("Unsupported content type: {}".format(
                type(contents)))

        # Get next row.
        buffer_offset = 0
        row = next_row(buffer_offset)

        irow = 0
        while row != b'':
            values = row_reader.unpack(row)
            # Sample number
            n = values[0]
            # Time stamp
            ts_val = values[1]
            ts = self._get_time(n, ts_val, time_base, time_mult)

            self.time[irow] = ts

            # Extract analog channel values.
            for ichannel in range(achannels):
                yint = values[ichannel + 2]
                y = a[ichannel] * yint + b[ichannel]
                self.analog[ichannel][irow] = y

            # Extract status channel values.
            for igroup in range(groups_of_16bits):
                group = values[achannels + 2 + igroup]

                # for each group of 16 bits, extract the status channels
                maxchn = min([ (igroup+1) * 16, schannel])
                for ichannel in range(igroup * 16, maxchn):
                    chnindex = ichannel - igroup*16
                    mask = int('0b01', 2) << chnindex
                    extract = (group & mask) >> chnindex

                    self.status[ichannel][irow] = extract

            # Get the next row
            irow += 1
            buffer_offset += bytes_per_row
            row = next_row(buffer_offset)


class Binary32DatReader(BinaryDatReader):
    """32-bit binary format DatReader subclass."""
    ANALOG_BYTES = 4

    STRUCT_FORMAT = "LL {acount:d}l {dcount:d}H"
    STRUCT_FORMAT_ANALOG_ONLY = "LL {acount:d}l"

    # maximum negative value
    DATA_MISSING = 0xFFFFFFFF


class Float32DatReader(BinaryDatReader):
    """Single precision (float) binary format DatReader subclass."""
    ANALOG_BYTES = 4

    STRUCT_FORMAT = "LL {acount:d}f {dcount:d}H"
    STRUCT_FORMAT_ANALOG_ONLY = "LL {acount:d}f"

    # Maximum negative value
    DATA_MISSING = sys.float_info.min
