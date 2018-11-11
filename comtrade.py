# -*- coding: utf-8 -*-

import datetime as dt
import errno
import math
import os
import re
import struct
import warnings
import matplotlib.pyplot as plt

# COMTRADE standard revisions
REV_1991 = "1991"
REV_1999 = "1999"
REV_2013 = "2013"

# DAT file format types
TYPE_ASCII  = "ASCII"
TYPE_BINARY = "BINARY"
TYPE_BINARY32 = "BINARY32"
TYPE_FLOAT32 = "FLOAT32"

# common separator character of data fields of CFG and ASCII DAT files
SEPARATOR = ","

# timestamp regular expression
re_dt = re.compile("([0-9]{1,2})/([0-9]{1,2})/([0-9]{4}),([0-9]{2}):([0-9]{2}):([0-9]{2})\\.([0-9]{6,12})")


def _read_sep_values(line):
    return line.strip().split(SEPARATOR)

def _read_timestamp(tstamp):
    m = re_dt.match(tstamp)
    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3))
    hour = int(m.group(4))
    minute = int(m.group(5))
    second = int(m.group(6))
    microsecond = int(m.group(7))
    nanosseconds = (microsecond >= 1E7)

    # timezone information
    tzinfo = None
    if nanosseconds:
        microsecond = microsecond * 1E-3

    return dt.datetime(year, month, day, hour, minute, second, 
                       microsecond, tzinfo)

class Cfg:
    # time base units
    TIME_BASE_NS = 1E-9
    TIME_BASE_US = 1E-6

    def __init__(self):
        self.filename = ""
        # implicit data
        self._time_base = self.TIME_BASE_US

        # Default CFG data
        self._station_name = ""
        self._rec_dev_id = ""
        self._rev_year = 2013
        self._channels_count = 0
        self._analog_channels = []
        self._digital_channels = []
        self._analog_count = 0
        self._digital_count = 0
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
    def digital_channels(self):
        return self._digital_channels
    
    @property
    def analog_count(self):
        return self._analog_count
    
    @property
    def digital_count(self):
        return self._digital_count
    
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
        self._digital_channels = []
        for line in cfg:
            if 0 == line_count:
                # station, device, and comtrade standard revision information
                packed = _read_sep_values(line)
                if 3 == len(packed):
                    # only 1999 revision and above has the standard revision year
                    self._station_name, self._rec_dev_id, self._rev_year = packed
                    self._rev_year = self._rev_year.strip()

                    if self._rev_year not in (REV_1991, REV_1999, REV_2013):
                        warnings.warn(Warning("Unknown standard revision \"{}\"".format(self._rev_year)))
                else:
                    self._station_name, self._rec_dev_id = packed
                    self._rev_year = REV_1999

            if 1 == line_count:
                # number of channels and its type
                totchn, achn, dchn = _read_sep_values(line)
                self._channels_count = int(totchn)
                self._analog_count   = int(achn[:-1])
                self._digital_count  = int(dchn[:-1])
                self._analog_channels = [None]*self._analog_count
                self._digital_channels = [None]*self._digital_count
            if 1 < line_count and line_count <= 1 + self._channels_count:
                # channel information
                # channel index
                ichn = line_count - 2
                packed = _read_sep_values(line)
                # analog or digital channel?
                if ichn < self._analog_count:
                    # analog channel index
                    iachn = ichn
                    # unpack values
                    n, name, ph, ccbm, uu, a, b, skew, cmin, cmax, primary, secondary, pors = packed
                    # type conversion
                    n = int(n)
                    a = float(a)
                    b = float(b)
                    skew = float(skew)
                    cmin = int(cmin)
                    cmax = int(cmax)
                    primary = float(primary)
                    secondary = float(secondary)
                    self.analog_channels[iachn] = AnalogChannel(n, a, b, skew, 
                        cmin, cmax, name, uu, ph, ccbm, primary, secondary, pors)
                else:
                    # digital channel index
                    idchn = ichn - self._analog_count
                    # unpack values
                    n, name, ph, ccbm, y = packed
                    # type conversion
                    n = int(n)
                    y = int(y)
                    self.digital_channels[idchn] = DigitalChannel(n, name, ph, ccbm, y)

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
            if line_count >= 4 + self._channels_count and line_count < 4 + self._channels_count + self._nrates:
                # each sample rate
                samp, endsamp = _read_sep_values(line)
                samp = float(samp)
                endsamp = int(endsamp)
                self.sample_rates.append([samp, endsamp])
            if line_count == 4 + self._channels_count + self._nrates:
                # first data point
                self._start_timestamp = _read_timestamp(line.strip())
            if line_count == 5 + self._channels_count + self._nrates:
                # last data point
                self._trigger_timestamp = _read_timestamp(line.strip())
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
        self._digital_channel_ids = []
        self._timestamp_critical = False

        # DAT file data
        self._time_values = []
        self._analog_values = []
        self._digital_values = []

    @property
    def analog_channel_ids(self):
        return self._analog_channel_ids
    
    @property
    def digital_channel_ids(self):
        return self._digital_channel_ids

    @property
    def time(self):
        return self._time_values

    @property
    def analog(self):
        return self._analog_values
    
    @property
    def digital(self):
        return self._digital_values

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
    def digital_count(self):
        return self._cfg.digital_count

    @property
    def trigger_time(self):
        """Relative trigger time in seconds."""
        stt = self._cfg.start_timestamp
        trg = self._cfg.trigger_timestamp
        tdiff = trg - stt
        tsec = (tdiff.days*60*60*24) + tdiff.seconds + (tdiff.microseconds*1E-6)
        return tsec

    @property
    def ft(self):
        return self._cfg.ft
    
    def __str__(self):
        pass

    def __repr__(self):
        pass

    def _get_dat_reader(self):
        dat = None
        if self.ft == TYPE_ASCII:
            dat = AsciiDatReader()
        elif self.ft == TYPE_BINARY:
            dat = BinaryDatReader()
        elif self.ft == TYPE_BINARY32:
            # not tested
            warnings.warn(FutureWarning("Experimental Binary32 reading"))
            dat = Binary32DatReader()
            # raise Exception("Binary32 format unsupported")
        elif self.ft == TYPE_FLOAT32:
            dat = None
            raise Exception("Float32 format unsupported")
        else:
            dat = None
            raise Exception("Not supported data file format: {}".format(self.ft))
        return dat

    def read(self, cfg_lines, dat_lines):
        self._cfg.read(cfg_lines)

        # channel ids
        self._analog_channel_ids = [channel.name for channel in self._cfg.analog_channels]
        self._digital_channel_ids = [channel.name for channel in self._cfg.digital_channels]

        dat = self._get_dat_reader()
        dat.read(dat_lines, self._cfg)

        # copy dat object information
        self._time_values    = dat.time
        self._analog_values  = dat.analog
        self._digital_values = dat.digital
        self._total_samples  = dat.total_samples

    def load(self, cfg_filepath, dat_filepath):
        self._cfg.load(cfg_filepath)

        # channel ids
        self._analog_channel_ids = [channel.name for channel in self._cfg.analog_channels]
        self._digital_channel_ids = [channel.name for channel in self._cfg.digital_channels]

        dat = self._get_dat_reader()
        dat.load(dat_filepath, self._cfg)

        # copy dat object information
        self._time_values    = dat.time
        self._analog_values  = dat.analog
        self._digital_values = dat.digital
        self._total_samples  = dat.total_samples

    def load_cff(self, cff_filepath):
        with open(cff_filepath, "r") as file:
            line_number = 0
            for line in file:
                if line.strip().lower() == "--- file type: cfg ---":
                    # process CFG
                    pass
                if line.strip().lower() == "--- file type: inf ---":
                    # process INF
                    pass
                if line.strip().lower() == "--- file type: hdr ---":
                    # process HDR
                    pass
                if line.strip().lower() == "--- file type: dat ascii ---":
                    # process ASCII DAT file
                    pass

            pass

    def cfg_summary(self):
        st = "Channels (total,A,D): {}A + {}D = {}\n".format(self.analog_count, self.digital_count, self.channels_count)
        st = st + "Line frequency: {} Hz\n".format(self.frequency)
        for i in range(self._cfg.nrates):
            rate, points = self._cfg.sample_rates[i]
            st = st + "Sample rate of {} Hz until point #{}\n".format(rate, points)
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


class DigitalChannel(Channel):
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
        self.digital = []
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

        # analog and digital count
        analog_count = self._cfg.analog_count
        digital_count = self._cfg.digital_count

        # preallocate analog and digital values
        self.time = [0.0] * steps
        self.analog  = [None] * analog_count
        self.digital = [None] * digital_count
        # preallocate each channel values with zeros
        for i in range(analog_count):
            self.analog[i]  = [0.0] * steps
        for i in range(digital_count):
            self.digital[i] = [0]   * steps

    def parse(self, contents):
        pass


class AsciiDatReader(DatReader):
    ASCII_SEPARATOR = SEPARATOR

    def parse(self, contents):
        analog_count  = self._cfg.analog_count
        digital_count = self._cfg.digital_count
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
                dvalues = [int(x) for x in values[analog_count+2:]]

                # store
                self.time[line_number-1] = t
                for i in range(analog_count):
                    self.analog[i][line_number - 1]  = avalues[i]
                for i in range(digital_count):
                    self.digital[i][line_number - 1] = dvalues[i]


class BinaryDatReader(DatReader):
    ANALOG_BYTES = 2
    DIGITAL_BYTES = 2
    TIME_BYTES = 4
    SAMPLE_NUMBER_BYTES = 4
    
    read_mode = "rb"

    def pad_bytes(self, val, length = 4):
        """Increases a binary-string array to "length" size."""

        # extract sign
        sign = (val[1] & int('0b10000000', 2)) >> 7
        if sign > 0:
            pad_with = b'\xFF'
        else:
            pad_with = b'\x00'

        newval = bytearray(val)
        for i in range(length - len(val)):
            newval.extend(bytearray(pad_with))
        return bytes(newval)

    def parse(self, contents):
        timemult = self._cfg.timemult
        time_base = self._cfg.time_base
        frequency = self._cfg.frequency
        achannels = self._cfg.analog_count
        dchannels = self._cfg.digital_count

        # auxillary vectors (channels gains and offsets)
        a = [x.a for x in self._cfg.analog_channels]
        b = [x.b for x in self._cfg.analog_channels]

        sample_id_bytes = self.SAMPLE_NUMBER_BYTES + self.TIME_BYTES
        abytes = achannels*self.ANALOG_BYTES
        dbytes = self.DIGITAL_BYTES * math.ceil(dchannels / 16.0)
        bytes_per_row = sample_id_bytes + abytes + dbytes

        if hasattr(contents, 'read'):
            row = contents.read(bytes_per_row)
        else:
            offset_f = 0
            row = contents[offset_f:offset_f + bytes_per_row]

        irow = 0
        while row != b'':
            # unpack row of bytes
            nbyte  = row[0:4]
            n  = struct.unpack('i', nbyte)[0]
            tsbyte = row[4:8]
            ts = struct.unpack('i', tsbyte)[0]
            # time
            t = (n - 1) / frequency

            self.time[irow] = t
            # extract channel values
            offset_start = sample_id_bytes
            for ichannel in range(achannels):
                offset = ichannel * self.ANALOG_BYTES + offset_start
                ybyte = row[offset:offset + self.ANALOG_BYTES]
                yint = struct.unpack('i', self.pad_bytes(ybyte))[0]
                y = a[ichannel] * yint + b[ichannel]
                self.analog[ichannel][irow] = y

            offset_start = sample_id_bytes + abytes
            groups_of_16bits = math.floor(dbytes / self.DIGITAL_BYTES)
            for igroup in range(groups_of_16bits):
                offset = igroup * self.DIGITAL_BYTES + offset_start
                group = row[offset:offset + self.DIGITAL_BYTES]
                group = struct.unpack('i', self.pad_bytes(group))[0]
                # for each group of 16 bits, extract the digital channels
                for ichannel in range(igroup * 16, (igroup+1) * 16):
                    chnindex = ichannel - igroup*16
                    mask = int('0b01', 2) << chnindex
                    extract = (group & mask) >> chnindex

                    self.digital[ichannel][irow] = extract

            if hasattr(contents, 'read'):
                row = contents.read(bytes_per_row)
            else:
                offset_f = offset_f + bytes_per_row
                row = contents[offset_f:offset_f + bytes_per_row]
            irow = irow + 1


class Binary32DatReader(BinaryDatReader):
    ANALOG_BYTES = 4



