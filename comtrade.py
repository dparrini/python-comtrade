# -*- coding: utf-8 -*-

import datetime as dt
import errno
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
TYPE_ASCII  = "ASCII"
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
re_dt = re.compile("([0-9]{1,2})/([0-9]{1,2})/([0-9]{4}),([0-9]{2}):([0-9]{2}):([0-9]{2})\\.([0-9]{5,12})")

# Non-standard revision warning
WARNING_UNKNOWN_REVISION = "Unknown standard revision \"{}\""
# Date time with nanoseconds resolution warning
WARNING_DATETIME_NANO = "Unsupported datetime objects with nanoseconds \
resolution. Using truncated values."


def _read_sep_values(line):
    return line.strip().split(SEPARATOR)


def _prevent_null(str_value, type, default_value):
        if len(str_value.strip()) == 0:
            return default_value
        else:
            return type(str_value)


def _read_timestamp(tstamp):
    m = re_dt.match(tstamp)
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
        warnings.warn(Warning(WARNING_DATETIME_NANO))
        microsecond = int(microsecond * 1E-3)

    return dt.datetime(year, month, day, hour, minute, second, 
                       microsecond, tzinfo)


class Cfg:
    # time base units
    TIME_BASE_NANOSEC = 1E-9
    TIME_BASE_MICROSEC = 1E-6

    def __init__(self):
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
        self._start_timestamp = ""
        self._trigger_timestamp = ""
        self._ft = TYPE_ASCII
        self._timemult = 1.0
        # 2013 standard revision information
        # time_code,local_code = 0,0 means local time is UTC
        self._time_code = 0
        self._local_code = 0
        # tmq_code,leapsec
        self._tmq_code = 0
        self._leapsec = 0

    @property
    def station_name(self):
        return self._station_name
    
    @property
    def rec_dev_id(self):
        return self._rec_dev_id

    @property
    def rev_year(self):
        return self._rev_year

    @property
    def channels_count(self):
        return self._channels_count

    @property
    def analog_channels(self):
        return self._analog_channels

    @property
    def status_channels(self):
        return self._status_channels
    
    @property
    def analog_count(self):
        return self._analog_count
    
    @property
    def status_count(self):
        return self._status_count
    
    @property
    def time_base(self):
        return self._time_base

    @property
    def frequency(self):
        return self._frequency
    
    @property
    def ft(self):
        return self._ft
    
    @property
    def timemult(self):
        return self._timemult
    
    @property
    def start_timestamp(self):
        return self._start_timestamp
    
    @property
    def trigger_timestamp(self):
        return self._trigger_timestamp
    
    @property
    def nrates(self):
        return self._nrates
    
    @property
    def sample_rates(self):
        return self._sample_rates

    # Deprecated properties - Changed "Digital" for "Status"
    @property
    def digital_channels(self):
        warnings.warn(FutureWarning("digital_channels is deprecated, use status_channels instead."))
        return self._status_channels

    @property
    def digital_count(self):
        warnings.warn(FutureWarning("digital_count is deprecated, use status_channels instead."))
        return self._status_count

    def load(self, filepath):
        self.filepath = filepath

        if os.path.isfile(self.filepath):
            with open(self.filepath, "r") as cfg:
                self._read_file(cfg)
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), 
                self.filepath)

    def read(self, cfg_lines):
        if type(cfg_lines) is str:
            self._read_file(cfg_lines.splitlines())
        else:
            self._read_file(cfg_lines)

    def _read_file(self, cfg):
        line_count = 0
        self._nrates = 1
        self._sample_rates = []
        self._analog_channels = []
        self._status_channels = []
        for line in cfg:
            if 0 == line_count:
                # station, device, and comtrade standard revision information
                packed = _read_sep_values(line)
                if 3 == len(packed):
                    # only 1999 revision and above has the standard revision year
                    self._station_name, self._rec_dev_id, self._rev_year = packed
                    self._rev_year = self._rev_year.strip()

                    if self._rev_year not in (REV_1991, REV_1999, REV_2013):
                        msg = WARNING_UNKNOWN_REVISION.format(self._rev_year)
                        warnings.warn(Warning(msg))
                else:
                    self._station_name, self._rec_dev_id = packed
                    self._rev_year = REV_1999

            if 1 == line_count:
                # number of channels and its type
                totchn, achn, dchn = _read_sep_values(line)
                self._channels_count = int(totchn)
                self._analog_count   = int(achn[:-1])
                self._status_count  = int(dchn[:-1])
                self._analog_channels = [None]*self._analog_count
                self._status_channels = [None]*self._status_count
            if 1 < line_count and line_count <= 1 + self._channels_count:
                # channel information
                # channel index
                ichn = line_count - 2
                packed = _read_sep_values(line)
                # analog or status channel?
                if ichn < self._analog_count:
                    # analog channel index
                    iachn = ichn
                    # unpack values
                    n, name, ph, ccbm, uu, a, b, skew, cmin, cmax, primary, secondary, pors = packed
                    # type conversion
                    n = int(n)
                    a = float(a)
                    b = _prevent_null(b, float, 0.0)
                    skew = _prevent_null(skew, float, 0.0)
                    cmin = float(cmin)
                    cmax = float(cmax)
                    primary = float(primary)
                    secondary = float(secondary)
                    self.analog_channels[iachn] = AnalogChannel(n, a, b, skew, 
                        cmin, cmax, name, uu, ph, ccbm, primary, secondary, pors)
                else:
                    # status channel index
                    idchn = ichn - self._analog_count
                    # unpack values
                    n, name, ph, ccbm, y = packed
                    # type conversion
                    n = int(n)
                    y = int(y)
                    self.status_channels[idchn] = StatusChannel(n, name, ph, ccbm, y)

            if line_count == 2 + self._channels_count:
                self._frequency = float(line.strip())
            if line_count == 3 + self._channels_count:
                # number of different sample rates
                self._nrates = int(line.strip())
                if self._nrates == 0:
                    self._nrates = 1
                    self._timestamp_critical = True
                else:
                    self._timestamp_critical = False
            if line_count > 3 + self._channels_count and line_count <= 3 + self._channels_count + self._nrates:
                # each sample rate
                samp, endsamp = _read_sep_values(line)
                samp = float(samp)
                endsamp = int(endsamp)
                self.sample_rates.append([samp, endsamp])

            if line_count == 4 + self._channels_count + self._nrates:
                # first data point and time base
                ts_str = line.strip()
                self._start_timestamp = _read_timestamp(ts_str)
                self._time_base = self._get_time_base(ts_str)

            if line_count == 5 + self._channels_count + self._nrates:
                # event data point and time base
                ts_str = line.strip()
                self._trigger_timestamp = _read_timestamp(ts_str)

                self._time_base = min([self.time_base, 
                    self._get_time_base(ts_str)])

            if line_count == 6 + self._channels_count + self._nrates:
                # file type
                self._ft = line.strip()

            if self._rev_year in (REV_1999, REV_2013):
                if line_count == 7 + self._channels_count + self._nrates:
                    # timestamp multiplication factor
                    self._timemult = float(line.strip())

            if self._rev_year == REV_2013:
                if line_count == (8 + self._channels_count + self._nrates):
                    # time_code and local_code
                    self._time_code, self._local_code = _read_sep_values(line)
                if line_count == (9 + self._channels_count + self._nrates):
                    # time_code and local_code
                    self._tmq_code, self._leapsec = _read_sep_values(line)

            line_count = line_count + 1

    def _get_time_base(self, timestamp):
        # Return the time base based on the fractionary part of the seconds
        # in a timestamp (00.XXXXX).
        match = re_dt.match(timestamp)
        in_nanoseconds = len(match.group(7)) > 6
        if in_nanoseconds:
            return self.TIME_BASE_NANOSEC
        else:
            return self.TIME_BASE_MICROSEC

class Comtrade:
    # extensions
    EXT_CFG = "cfg"
    EXT_DAT = "dat"
    # format specific
    ASCII_SEPARATOR = ","
    
    def __init__(self):
        self.filename = ""

        self._cfg = Cfg()

        # Default CFG data
        self._analog_channel_ids = []
        self._status_channel_ids = []
        self._timestamp_critical = False

        # DAT file data
        self._time_values = []
        self._analog_values = []
        self._status_values = []

    @property
    def station_name(self):
        return self._cfg._station_name
    
    @property
    def rec_dev_id(self):
        return self._cfg._rec_dev_id

    @property
    def rev_year(self):
        return self._cfg._rev_year

    @property
    def cfg(self):
        return self._cfg

    @property
    def analog_channel_ids(self):
        return self._analog_channel_ids
    
    @property
    def status_channel_ids(self):
        return self._status_channel_ids

    @property
    def time(self):
        return self._time_values

    @property
    def analog(self):
        return self._analog_values
    
    @property
    def status(self):
        return self._status_values

    @property
    def total_samples(self):
        return self._total_samples

    @property
    def frequency(self):
        return self._cfg.frequency

    @property
    def start_timestamp(self):
        return self._cfg.start_timestamp

    @property
    def trigger_timestamp(self):
        return self._cfg.trigger_timestamp

    @property
    def channels_count(self):
        return self._cfg.channels_count

    @property
    def analog_count(self):
        return self._cfg.analog_count

    @property
    def status_count(self):
        return self._cfg.status_count

    @property
    def trigger_time(self):
        """Relative trigger time in seconds."""
        stt = self._cfg.start_timestamp
        trg = self._cfg.trigger_timestamp
        tdiff = trg - stt
        tsec = (tdiff.days*60*60*24) + tdiff.seconds + (tdiff.microseconds*1E-6)
        return tsec

    @property
    def time_base(self):
        return self._cfg.time_base

    @property
    def ft(self):
        return self._cfg.ft

    # Deprecated properties - Changed "Digital" for "Status"
    @property
    def digital_channel_ids(self):
        warnings.warn(FutureWarning("digital_channel_ids is deprecated, use status_channel_ids instead."))
        return self._status_channel_ids

    @property
    def digital(self):
        warnings.warn(FutureWarning("digital is deprecated, use status instead."))
        return self._status_values

    @property
    def digital_count(self):
        warnings.warn(FutureWarning("digital_count is deprecated, use status_count instead."))
        return self._cfg.status_count
    
    def __str__(self):
        pass

    def __repr__(self):
        pass

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

    def read(self, cfg_lines, dat_lines):
        self._cfg.read(cfg_lines)

        # channel ids
        self._cfg_extract_channels_ids(self._cfg)

        dat = self._get_dat_reader()
        dat.read(dat_lines, self._cfg)

        # copy dat object information
        self._dat_extract_data(dat)

    def _cfg_extract_channels_ids(self, cfg):
        self._analog_channel_ids = [channel.name for channel in cfg.analog_channels]
        self._status_channel_ids = [channel.name for channel in cfg.status_channels]

    def _dat_extract_data(self, dat):
        self._time_values    = dat.time
        self._analog_values  = dat.analog
        self._status_values = dat.status
        self._total_samples  = dat.total_samples

    def load(self, cfg_file, dat_file = None):
        # which extension: CFG or CFF?
        file_ext = cfg_file[-3:].upper()
        if file_ext == "CFG":
            # if not informed, infer dat_file with cfg_file
            if dat_file is None:
                dat_file = cfg_file[:-3] + "DAT"

            # load both
            self._load_cfg_dat(cfg_file, dat_file)
        elif file_ext == "CFF":
            # check if the CFF file exists
            # load file
            self._load_cff(cfg_file)
        else:
            # TODO: raise exception: expected CFG file
            pass

    def _load_cfg_dat(self, cfg_filepath, dat_filepath):
        self._cfg.load(cfg_filepath)

        # channel ids
        self._cfg_extract_channels_ids(self._cfg)

        dat = self._get_dat_reader()
        dat.load(dat_filepath, self._cfg)

        # copy dat object information
        self._dat_extract_data(dat)

    def _load_cff(self, cff_filepath):
        # stores each file type lines
        cfg_lines = []
        dat_lines = []
        hdr_lines = []
        inf_lines = []
        with open(cff_filepath, "r") as file:
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
        self.read(cfg_lines, dat_lines)


    def cfg_summary(self):
        st = "Channels (total,A,D): {}A + {}D = {}\n".format(self.analog_count, self.status_count, self.channels_count)
        st = st + "Line frequency: {} Hz\n".format(self.frequency)
        for i in range(self._cfg.nrates):
            rate, points = self._cfg.sample_rates[i]
            st = st + "Sample rate of {} Hz to the sample #{}\n".format(rate, points)
        st = st + "From {} to {} with time mult. = {}\n".format(self.start_timestamp, self.trigger_timestamp, self._cfg.timemult)
        st = st + "{} format\n".format(self.ft)
        return st


class Channel:
    def __init__(self, n=1, name='', ph='', ccbm=''):
        self.n = n
        self.name = name
        self.ph = ph
        self.ccbm = ccbm

    def __str__(self):
        return ','.join([str(self.n), self.name, self.ph, self.ccbm])


class StatusChannel(Channel):
    def __init__(self, n, name='', ph='', ccbm='', y=''):
        self.name = name
        self.n = n
        self.name = name
        self.ph = ph
        self.ccbm = ccbm
        self.y = y

    def __str__(self):
        fields = [str(self.n), self.name, self.ph, self.ccbm, str(self.y)]


class AnalogChannel(Channel):
    def __init__(self, n, a, b=0.0, skew=0.0, cmin=-32767, cmax=32767, 
        name='', uu='', ph='', ccbm='', primary=1, secondary=1, pors='P'):
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
            str(self.cmax), str(self.primary), str(self.secondary), self.ps]
        return ','.join(fields)


class DatReader:
    read_mode = "r"

    def __init__(self):
        self.filepath = ""
        self._content = None
        self._cfg = None
        self.time = []
        self.analog = []
        self.status = []
        self._total_samples = 0

    @property
    def total_samples(self):
        return self._total_samples

    def load(self, dat_filepath, cfg):
        self.filepath = dat_filepath
        self._content = None
        if os.path.isfile(self.filepath):
            # extract CFG file information regarding data dimensions
            self._cfg = cfg
            self._preallocate()
            with open(self.filepath, self.read_mode) as contents:
                self.parse(contents)
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), 
                self.filepath)

    def read(self, dat_lines, cfg):
        self.filepath = None
        self._content = dat_lines
        self._cfg = cfg
        self._preallocate()
        self.parse(dat_lines)

    def _preallocate(self):
        # read from the cfg file the number of samples in the dat file
        steps = self._cfg.sample_rates[-1][1] # last samp field
        self._total_samples = steps

        # analog and status count
        analog_count = self._cfg.analog_count
        status_count = self._cfg.status_count

        # preallocate analog and status values
        self.time = [0.0] * steps
        self.analog  = [None] * analog_count
        self.status = [None] * status_count
        # preallocate each channel values with zeros
        for i in range(analog_count):
            self.analog[i]  = [0.0] * steps
        for i in range(status_count):
            self.status[i] = [0]   * steps

    def parse(self, contents):
        pass


class AsciiDatReader(DatReader):
    ASCII_SEPARATOR = SEPARATOR

    DATA_MISSING = ""

    def parse(self, contents):
        analog_count  = self._cfg.analog_count
        status_count = self._cfg.status_count
        timemult = self._cfg.timemult
        time_base = self._cfg.time_base

        # auxillary vectors (channels gains and offsets)
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

                n = values[0]
                t = float(values[1]) * time_base * timemult
                avalues = [float(x)*a[i] + b[i] for i, x in enumerate(values[2:analog_count+2])]
                svalues = [int(x) for x in values[status_count+2:]]

                # store
                self.time[line_number-1] = t
                for i in range(analog_count):
                    self.analog[i][line_number - 1]  = avalues[i]
                for i in range(status_count):
                    self.status[i][line_number - 1] = svalues[i]


class BinaryDatReader(DatReader):
    ANALOG_BYTES = 2
    STATUS_BYTES = 2
    TIME_BYTES = 4
    SAMPLE_NUMBER_BYTES = 4

    # maximum negative value
    DATA_MISSING = 0xFFFF

    read_mode = "rb"

    STRUCT_FORMAT = "LL {acount:d}h {dcount:d}H"
    STRUCT_FORMAT_ANALOG_ONLY = "LL {acount:d}h"
    STRUCT_FORMAT_STATUS_ONLY = "LL {dcount:d}H"

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
        timemult = self._cfg.timemult
        time_base = self._cfg.time_base
        frequency = self._cfg.frequency
        achannels = self._cfg.analog_count
        dchannels = self._cfg.status_count

        # auxillary vectors (channels gains and offsets)
        a = [x.a for x in self._cfg.analog_channels]
        b = [x.b for x in self._cfg.analog_channels]

        sample_id_bytes = self.SAMPLE_NUMBER_BYTES + self.TIME_BYTES
        abytes = achannels*self.ANALOG_BYTES
        dbytes = self.STATUS_BYTES * math.ceil(dchannels / 16.0)
        bytes_per_row = sample_id_bytes + abytes + dbytes
        groups_of_16bits = math.floor(dbytes / self.STATUS_BYTES)
        period = 1 / frequency

        # Struct format.
        rowreader = struct.Struct(self.get_reader_format(achannels, dbytes))

        # Row reading function.
        nextrow = None
        if hasattr(contents, 'read'):
            # It's an IO buffer.
            nextrow = lambda offset: contents.read(bytes_per_row)
        else:
            # It's an array.
            nextrow = lambda offset: contents[offset:offset + bytes_per_row]

        # Get next row.
        buffer_offset = 0
        row = nextrow(buffer_offset)

        irow = 0
        while row != b'':
            values = rowreader.unpack(row)
            # Sample number
            n = values[0]
            # Calculated time
            # TODO: add support for multiple sampling rates
            t = (n - 1) * period

            # Read time
            ts_val = values[1]
            if ts_val != TIMESTAMP_MISSING:
                ts = values[1] * time_base * timemult
            else:
                # if the timestamp is missing, use calculated.
                ts = t

            # Using calculated timestamp, ignoring file timestamp.
            # TODO: add option to enforce dat file timestamp, when available
            self.time[irow] = t

            # Extract analog channel values.
            for ichannel in range(achannels):
                yint = values[ichannel + 2]
                y = a[ichannel] * yint + b[ichannel]
                self.analog[ichannel][irow] = y

            # Extract status channel values.
            for igroup in range(groups_of_16bits):
                group = values[achannels + 2 + igroup]

                # for each group of 16 bits, extract the status channels
                maxchn = min([ (igroup+1) * 16, dchannels])
                for ichannel in range(igroup * 16, maxchn):
                    chnindex = ichannel - igroup*16
                    mask = int('0b01', 2) << chnindex
                    extract = (group & mask) >> chnindex

                    self.status[ichannel][irow] = extract

            # Get the next row
            irow += 1
            buffer_offset += bytes_per_row
            row = nextrow(buffer_offset)


class Binary32DatReader(BinaryDatReader):
    ANALOG_BYTES = 4

    STRUCT_FORMAT = "LL {acount:d}l {dcount:d}H"
    STRUCT_FORMAT_ANALOG_ONLY = "LL {acount:d}l"

    # maximum negative value
    DATA_MISSING = 0xFFFFFFFF


class Float32DatReader(BinaryDatReader):
    ANALOG_BYTES = 4

    STRUCT_FORMAT = "LL {acount:d}f {dcount:d}H"
    STRUCT_FORMAT_ANALOG_ONLY = "LL {acount:d}f"

    # Maximum negative value
    DATA_MISSING = sys.float_info.min
