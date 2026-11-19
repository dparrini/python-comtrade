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

__version__ = "0.3.2"

import array
import bisect
import collections.abc
import configparser
import datetime as dt
import errno
import io
import itertools
import math
import mmap
import operator
import os
import re
import struct
import sys
from typing import Union
import warnings

try:
    import numpy

    _HAS_NUMPY = True
except ModuleNotFoundError:
    _HAS_NUMPY = False

try:
    import pandas as pd

    _HAS_PANDAS = True
except ModuleNotFoundError:
    _HAS_PANDAS = False


# COMTRADE standard revisions
REV_1991 = "1991"
REV_1999 = "1999"
REV_2001 = "2001"
REV_2013 = "2013"

# DAT file format types
_TYPE_ASCII = "ASCII"
_TYPE_BINARY = "BINARY"
_TYPE_BINARY32 = "BINARY32"
_TYPE_FLOAT32 = "FLOAT32"

# Reference of integer timestamps (naive, as numpy.datetime64)
_EPOCH = dt.datetime(1970, 1, 1)

# Special values
_TIMESTAMP_MISSING = 0xFFFFFFFF

# DAT file loading options (keyword arguments of Comtrade.load and read)
_DAT_OPTIONS = ("lazy", "start_time", "end_time")

# CFF headers
_CFF_HEADER_REXP = r"(?i)--- file type: ([a-z]+)(?:\s+([a-z0-9]+)(?:\s*\:\s*([0-9]+))?)? ---$"

# common separator character of data fields of CFG and ASCII DAT files
_SEPARATOR = ","

# maximum number of ASCII DAT file values converted at once
_ASCII_BLOCK_VALUES = 1000000

# timestamp regular expression
_re_date = re.compile(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})")
_re_time = re.compile(r"([0-9]{1,2}):([0-9]{2}):([0-9]{1,2})(.([0-9]{1,12}))?")

# Non-standard revision warning
_WARNING_UNKNOWN_REVISION = "Unknown standard revision \"{}\""
# Date time with nanoseconds resolution warning
_WARNING_DATETIME_NANO = "datetime objects don't support nanoseconds \
resolution, start_timestamp and trigger_timestamp are truncated to \
microseconds. Use start_timestamp_ns and trigger_timestamp_ns for full \
resolution."
# Status channel without normal state
_WARNING_MISSING_NORMAL_STATE = "Missing normal state (y) of status channel \
{}. Using 0."
# Analog channel without valid ratio information
_WARNING_INVALID_RATIO = "Invalid ratio information of analog channel {} \
(primary={}, secondary={}, PS=\"{}\"). Values are not scaled."
# Unrecognized time of a timestamp
_WARNING_INVALID_TIME = "Invalid time \"{}\". Using 00:00:00."
# DAT file with fewer samples than the CFG file declares
_WARNING_MISSING_SAMPLES = "The DAT file has {} fewer samples than the {} \
declared in the CFG file. Only the samples in the DAT file were loaded."
# Date time with year 0, month 0 and/or day 0.
_WARNING_MIN_DATE = "Missing date values. Using minimum values: {}."
# Invalid 2013 revision time information fields
_WARNING_INVALID_TIME_CODE = "Invalid time code \"{}\". Ignoring it."
_WARNING_INVALID_TMQ_CODE = "Invalid time quality code \"{}\". Ignoring it."
_WARNING_INVALID_LEAP_SECOND = "Invalid leap second indicator \"{}\". Ignoring it."

# IEEE C37.232 time code, such as "-5h30", "+10", or "0"
_re_time_code = re.compile(r"(?i)^([+-]?)([0-9]{1,2})(?:h([0-9]{1,2}))?$")

# File writing
# revisions which files can be written
_WRITABLE_REVISIONS = (REV_1999, REV_2001, REV_2013)
# DAT file formats introduced by the 2013 revision
_FORMATS_2013 = (_TYPE_BINARY32, _TYPE_FLOAT32)
# maximum absolute raw value of the integer DAT file formats (the values
# beyond are missing data markers)
_INT_LIMITS = {_TYPE_ASCII: 99998, _TYPE_BINARY: 32767,
               _TYPE_BINARY32: 2147483647}
# missing data markers
_ASCII_MISSING = "99999"
# most negative single precision value (-3.40282347E+38, 0xFF7FFFFF)
_FLOAT32_MISSING = -3.4028234663852886e+38
_BINARY_MISSING = {_TYPE_BINARY: -32768, _TYPE_BINARY32: -2147483648,
                   _TYPE_FLOAT32: _FLOAT32_MISSING}
_BINARY_ANALOG_TYPECODE = {_TYPE_BINARY: "h", _TYPE_BINARY32: "i",
                           _TYPE_FLOAT32: "f"}
# maximum timestamp value (0xFFFFFFFF marks missing timestamps)
_MAX_TIMESTAMP = 0xFFFFFFFE
# CRLF line endings, as required by the standard
_NEWLINE = "\r\n"


class ComtradeError(ValueError):
    """Invalid COMTRADE data or unsupported operation. It is a ValueError,
    so that code catching the ValueError malformed files used to raise keeps
    working."""
    pass


def _read_sep_values(line, expected: int = -1, default: str = ''):
    values = tuple(map(lambda cell: cell.strip(), line.split(_SEPARATOR)))
    if expected == -1 or len(values) == expected:
        return values
    return [values[i] if i < len(values) else default
            for i in range(expected)]


def _preallocate_values(array_type, size, use_numpy_arrays):
    type_mapping_numpy = {"f": "float32", "d": "float64", "i": "int32", "l": "int64"}
    if _HAS_NUMPY and use_numpy_arrays:
        return numpy.zeros(size, dtype=type_mapping_numpy[array_type])
    return array.array(array_type, [0]) * size


def _as_values(values: array.array, use_numpy_arrays: bool):
    """Return the array values as a numpy array of the same type, if numpy
    arrays are used."""
    if _HAS_NUMPY and use_numpy_arrays:
        return numpy.array(values, dtype=values.typecode)
    return values


def _copy_values(target, start: int, values):
    """Copy values into a preallocated values array, from the start index."""
    if isinstance(target, array.array):
        values = array.array(target.typecode, values)
    target[start:start + len(values)] = values


def _unpack_column(data, row_size: int, offset: int, typecode: str,
                   first_row: int = 0, rows: int = -1) -> array.array:
    """Unpack the little-endian field of typecode at the offset (in bytes) of
    rows (all whole rows, if negative) of row_size bytes in data, starting at
    the row first_row."""
    if rows < 0:
        rows = len(data) // row_size - first_row
    size = array.array(typecode).itemsize
    column = bytearray(rows * size)
    start = first_row * row_size + offset
    end = (first_row + rows) * row_size
    # gather each byte of the field from all rows at once
    for k in range(size):
        column[k::size] = data[start + k:end:row_size]
    values = array.array(typecode, column)
    if sys.byteorder == "big":
        values.byteswap()
    return values


def _prevent_null(str_value: str, value_type: type, default_value):
    if len(str_value.strip()) == 0:
        return default_value
    else:
        return value_type(str_value)


def _expand_year(year_str: str) -> int:
    """Return the year of a date field as int. Two-digit years, as written in
    the 1991 revision format (mm/dd/yy), are expanded: 70 to 99 are 1970 to
    1999, the others are 2000 to 2069."""
    year = int(year_str)
    if len(year_str) == 2:
        return year + (2000 if year < 70 else 1900)
    return year


def _get_date(date_str: str) -> tuple:
    """Return the day, month and year of a date field, which may be shorter
    than expected. Returns zeros for an invalid field."""
    m = _re_date.match(date_str)
    if m is not None:
        day = int(m.group(1))
        month = int(m.group(2))
        year = _expand_year(m.group(3))
        return day, month, year
    return 0, 0, 0


def _parse_time(time_str: str, ignore_warnings: bool = False) -> tuple:
    """Return the hour, minute, second, nanosecond and whether the fraction of
    seconds has nanoseconds resolution (more than 6 digits) of a time string.
    Digits beyond nanoseconds are ignored."""
    m = _re_time.match(time_str.strip())
    if m is None:
        if not ignore_warnings:
            warnings.warn(Warning(_WARNING_INVALID_TIME.format(time_str)))
        return 0, 0, 0, 0, False
    hour = int(m.group(1))
    minute = int(m.group(2))
    second = int(m.group(3))
    frac_sec_str = m.group(5) or ""
    in_nanoseconds = len(frac_sec_str) > 6
    nanosecond = int(fill_with_zeros_to_the_right(frac_sec_str[:9], 9))
    return hour, minute, second, nanosecond, in_nanoseconds


def _get_time(time_str: str, ignore_warnings: bool = False) -> tuple:
    """Return the hour, minute, second, microsecond (truncated) and whether
    the fraction of seconds has nanoseconds resolution of a time string."""
    hour, minute, second, nanosecond, in_nanoseconds = _parse_time(
        time_str, ignore_warnings)
    if in_nanoseconds and not ignore_warnings:
        # Nanoseconds resolution is not supported by datetime module
        warnings.warn(Warning(_WARNING_DATETIME_NANO))
    return hour, minute, second, nanosecond // 1000, in_nanoseconds


def fill_with_zeros_to_the_right(number_str: str, width: int):
    actual_len = len(number_str)
    if actual_len < width:
        difference = width - actual_len
        fill_chars = "0" * difference
        return number_str + fill_chars
    return number_str


def _get_same_case(original_ext: str, other_ext: str) -> str:
    """Returns each other_ext character with the same case as original_ext's."""
    same_case = ""
    for i in range(len(original_ext)):
        if i < len(other_ext):
            if original_ext[i].isupper():
                same_case += other_ext[i].upper()
            else:
                same_case += other_ext[i].lower()
        else:
            break
    return same_case


def _read_timestamp(timestamp_line: str, rev_year: str, ignore_warnings: bool = False) -> tuple:
    """Process comma separated fields and returns a tuple containing the timestamp,
    a boolean value indicating whether nanoseconds are used, and the nanoseconds
    truncated from the timestamp (0 to 999).
    Can possibly return the timestamp 00/00/0000 00:00:00.000 for empty strings
    or empty pairs."""
    day, month, year, hour, minute, second, nanosecond = (0,) * 7
    nano_sec = False
    if len(timestamp_line.strip()) > 0:
        values = _read_sep_values(timestamp_line, 2)
        if len(values) >= 2:
            date_str, time_str = values[0:2]
            if len(date_str.strip()) > 0:
                # 1991 Format Uses mm/dd/yy format
                if rev_year == REV_1991:
                    month, day, year = _get_date(date_str)
                # Modern Formats Use dd/mm/yyyy format
                else:
                    day, month, year = _get_date(date_str)
            if len(time_str.strip()) > 0:
                hour, minute, second, nanosecond, \
                    nano_sec = _parse_time(time_str, ignore_warnings)
                if nano_sec and not ignore_warnings:
                    warnings.warn(Warning(_WARNING_DATETIME_NANO))

    using_min_data = False
    if year <= 0:
        year = dt.MINYEAR
        using_min_data = True
    if month <= 0:
        month = 1
        using_min_data = True
    if day <= 0:
        day = 1
        using_min_data = True
    # Timezone info unsupported
    tzinfo = None
    timestamp = dt.datetime(year, month, day, hour, minute, second,
                            nanosecond // 1000, tzinfo)
    if not ignore_warnings and using_min_data:
        warnings.warn(Warning(_WARNING_MIN_DATE.format(str(timestamp))))
    return timestamp, nano_sec, nanosecond % 1000


def _timestamp_ns(timestamp: dt.datetime, nanosecond: int) -> int:
    """Return a naive timestamp, plus nanoseconds, as an integer number of
    nanoseconds since 1970-01-01 00:00:00 (the same time zone)."""
    microseconds = (timestamp - _EPOCH) // dt.timedelta(microseconds=1)
    return microseconds * 1000 + nanosecond


def _parse_time_code(time_code: str, ignore_warnings: bool = False) -> Union[dt.timedelta, None]:
    """Convert an IEEE C37.232 time code (such as "-5h30", "+10" or "0") to the
    time difference to UTC. Returns None for empty or "x" (not applicable) codes,
    and for invalid ones (warning the user)."""
    time_code = time_code.strip()
    if time_code == "" or time_code.lower() == "x":
        return None
    m = _re_time_code.match(time_code)
    if m is not None:
        hours = int(m.group(2))
        minutes = int(m.group(3)) if m.group(3) is not None else 0
        if hours < 24 and minutes < 60:
            offset = dt.timedelta(hours=hours, minutes=minutes)
            return -offset if m.group(1) == "-" else offset
    if not ignore_warnings:
        warnings.warn(Warning(_WARNING_INVALID_TIME_CODE.format(time_code)))
    return None


def _parse_tmq_code(tmq_code: str, ignore_warnings: bool = False) -> Union[int, None]:
    """Convert the time quality code (an hexadecimal digit, IEEE C37.118) to
    int. Returns None for empty or invalid codes (warning the user)."""
    tmq_code = tmq_code.strip()
    if tmq_code == "":
        return None
    if len(tmq_code) == 1 and tmq_code in "0123456789abcdefABCDEF":
        return int(tmq_code, 16)
    if not ignore_warnings:
        warnings.warn(Warning(_WARNING_INVALID_TMQ_CODE.format(tmq_code)))
    return None


def _parse_leap_second(leap_second: str, ignore_warnings: bool = False) -> Union[int, None]:
    """Convert the leap second indicator (0 to 3) to int. Returns None for
    empty or invalid values (warning the user)."""
    leap_second = leap_second.strip()
    if leap_second == "":
        return None
    if leap_second in ("0", "1", "2", "3"):
        return int(leap_second)
    if not ignore_warnings:
        warnings.warn(Warning(_WARNING_INVALID_LEAP_SECOND.format(leap_second)))
    return None


def _to_utc(timestamp: dt.datetime, offset: Union[dt.timedelta, None]) -> Union[dt.datetime, None]:
    """Convert a naive timestamp, in the time zone offset from UTC, to a timezone
    aware datetime in UTC. Returns None when the offset is unknown."""
    if offset is None:
        return None
    try:
        return timestamp.replace(tzinfo=dt.timezone(offset)).astimezone(dt.timezone.utc)
    except OverflowError:
        # placeholder timestamps (missing dates) near datetime.min
        return None


class _LazyChannels(collections.abc.Sequence):
    """Sequence of channel values decoded when first accessed."""

    def __init__(self, count: int, decode):
        self._decode = decode
        self._values = [None] * count

    def __len__(self):
        return len(self._values)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        values = self._values[index]
        if values is None:
            index = range(len(self))[index]
            values = self._decode(index)
            self._values[index] = values
        return values

    def __add__(self, other):
        # concatenation as lists, such as analog + status
        return list(self) + list(other)

    def __radd__(self, other):
        return list(other) + list(self)

    def __repr__(self):
        return "<{} channels, decoded when first accessed>".format(len(self))


def _scale_values(values, factor: float):
    """Return the values (array.array or numpy array) multiplied by factor."""
    if factor == 1.0:
        return values
    if _HAS_NUMPY and isinstance(values, numpy.ndarray):
        return values * factor
    return array.array(values.typecode, [v * factor for v in values])


def _eof_strip(line: str) -> str:
    """Strip line of whitespace and <sub> (0x1A) control character that may appear
     appended to the end of text files on some platforms."""
    return _replace_sub(line).strip()


def _replace_sub(line: str) -> str:
    """Replace <sub> (0x1A) control character that may appear appended to the end
    of text files on some platforms."""
    return line.replace(chr(0x1A), "")


def _strip_bom(text: str) -> str:
    """Remove the UTF-8 byte order mark (BOM) from the start of a decoded
    text, which is left there when a file with a BOM is decoded as UTF-8
    instead of UTF-8-SIG."""
    return text[1:] if text.startswith("\ufeff") else text


def _values_list(values) -> list:
    """Return channel values (array.array, numpy array or list) as a list."""
    return values.tolist() if hasattr(values, "tolist") else list(values)


def _format_number(value) -> str:
    """Format a number for CFG files, without a fractional part if integer,
    otherwise with the shortest representation that reads back the same."""
    value = float(value)
    if value.is_integer() and abs(value) < 1E15:
        return str(int(value))
    return repr(value)


def _check_field(value, description: str) -> str:
    """Return a CFG text field, which can't contain separators or line breaks."""
    value = str(value)
    if any(char in value for char in (_SEPARATOR, "\r", "\n")):
        raise ComtradeError("{} can't contain commas or line breaks: \"{}\"".format(
            description, value))
    return value


def _format_timestamp(timestamp_ns: int, nanoseconds: bool) -> str:
    """Format a timestamp (nanoseconds since 1970-01-01) as dd/mm/yyyy,hh:mm:ss
    with microseconds or nanoseconds."""
    microseconds, nanosecond = divmod(timestamp_ns, 1000)
    t = _EPOCH + dt.timedelta(microseconds=microseconds)
    text = "{:02d}/{:02d}/{:04d},{:02d}:{:02d}:{:02d}.{:06d}".format(
        t.day, t.month, t.year, t.hour, t.minute, t.second, t.microsecond)
    if nanoseconds:
        text += "{:03d}".format(nanosecond)
    return text


def _format_time_code(offset: Union[dt.timedelta, None]) -> str:
    """Format a time difference to UTC as an IEEE C37.232 time code, such as
    "-5h30", "+10" or "0". Returns an empty string for unknown offsets."""
    if offset is None:
        return ""
    minutes = offset // dt.timedelta(minutes=1)
    if minutes == 0:
        return "0"
    hours, minutes = divmod(abs(minutes), 60)
    sign = "-" if offset < dt.timedelta(0) else "+"
    return sign + str(hours) + ("h{:02d}".format(minutes) if minutes else "")


def _detect_sample_rates(times: list) -> list:
    """Return the sample rates list ([[samp, endsamp]]) of time values: their
    sample rate, if uniformly sampled, otherwise 0 (no fixed sample rate)."""
    count = len(times)
    if count >= 2:
        period = (times[-1] - times[0]) / (count - 1)
        if period > 0:
            # tolerance of time values stored with single precision
            tolerance = period * 1E-3 + \
                max(abs(times[0]), abs(times[-1])) * 2.4E-7
            if all(abs(t1 - t0 - period) <= tolerance
                   for t0, t1 in itertools.pairwise(times)):
                rate = 1.0 / period
                if abs(rate - round(rate)) <= rate * 1E-6:
                    rate = float(round(rate))
                return [[rate, count]]
    return [[0.0, count]]


def _encode_analog(values: list, channel, ft: str, keep_scaling: bool) -> tuple:
    """Return the DAT file raw values of an analog channel and its a, b, min
    and max CFG fields. Missing (NaN) values are None.

    The channel's a and b are kept if keep_scaling is set and the values fit
    the format range with them. Otherwise, they are computed to use the whole
    range of integer formats, or set to a=1 and b=0 for FLOAT32."""
    a, b = channel.a, channel.b
    if ft == _TYPE_FLOAT32:
        if not keep_scaling or a == 0:
            a, b = 1.0, 0.0
        raw = [None if math.isnan(v) else (v - b) / a for v in values]
        finite = [r for r in raw if r is not None and math.isfinite(r)]
        cmin, cmax = (min(finite), max(finite)) if finite else (0.0, 0.0)
        return raw, a, b, cmin, cmax

    limit = _INT_LIMITS[ft]
    cmin, cmax = -limit, limit
    finite = [v for v in values if math.isfinite(v)]
    if finite:
        vmin, vmax = min(finite), max(finite)
        fits = keep_scaling and a != 0 and \
            all(abs(round((v - b) / a)) <= limit for v in (vmin, vmax))
        if fits:
            cmin, cmax = channel.cmin, channel.cmax
        else:
            b = (vmax + vmin) / 2
            a = (vmax - vmin) / (2 * limit)
            if a == 0:
                a = 1.0
    elif not keep_scaling:
        a, b = 1.0, 0.0
    raw = [max(-limit, min(limit, round((v - b) / a))) if math.isfinite(v)
           else None for v in values]
    return raw, a, b, cmin, cmax


def _to_crlf(text: str) -> str:
    """Return text with CRLF line endings."""
    return text.replace("\r\n", "\n").replace("\n", _NEWLINE)


def _is_status_series(series) -> bool:
    """Return whether a pandas Series has status values: booleans, or integers
    with only 0 and 1 values."""
    if pd.api.types.is_bool_dtype(series):
        return True
    return pd.api.types.is_integer_dtype(series) and \
        bool(series.isin([0, 1]).all())


def _to_timestamp_ns(value) -> tuple:
    """Return a timestamp (datetime, pandas Timestamp or string) as
    nanoseconds since 1970-01-01, in its own time zone, and its time difference
    to UTC (None for naive timestamps). Requires pandas."""
    stamp = pd.Timestamp(value)
    offset = stamp.utcoffset()
    if offset is not None:
        stamp = stamp.tz_localize(None)
    return stamp.value, offset


class Cfg:
    """Parses and stores Comtrade's CFG data."""
    # time base units
    TIME_BASE_NANO_SEC = 1E-9
    TIME_BASE_MICRO_SEC = 1E-6

    def __init__(self, **kwargs):
        """
        Cfg object constructor.

        Keyword arguments:
        ignore_warnings -- whether warnings are displayed in stdout 
            (default: False)
        """
        self._file_path = None
        # implicit data
        self._time_base = self.TIME_BASE_MICRO_SEC

        # Default CFG data
        self._station_name = ""
        self._rec_dev_id = ""
        self._rev_year = REV_2013
        self._channels_count = 0
        self._analog_channels = []
        self._status_channels = []
        self._analog_count = 0
        self._status_count = 0
        self._frequency = 0.0
        self._nrates = 1
        self._sample_rates = []
        self._timestamp_critical = False
        self._start_timestamp = dt.datetime(1900, 1, 1)
        self._trigger_timestamp = dt.datetime(1900, 1, 1)
        # nanoseconds truncated from the timestamps above (0 to 999)
        self._start_nanosecond = 0
        self._trigger_nanosecond = 0
        self._ft = _TYPE_ASCII
        self._time_multiplier = 1.0
        # 2013 standard revision information (empty strings or None when
        # not available)
        # time_code: time difference to UTC of the file timestamps
        # local_code: time difference to UTC of the recording location
        self._time_code = ""
        self._local_code = ""
        self._time_offset = None
        self._local_offset = None
        # tmq_code,leapsec
        self._tmq_code = None
        self._leap_second = None

        self._ignore_warnings = kwargs.get("ignore_warnings", False)

    @property
    def file_path(self) -> Union[str, None]:
        """Return the CFG file path."""
        return self._file_path

    @property
    def station_name(self) -> str:
        """Return the recording device's station name."""
        return self._station_name

    @property
    def rec_dev_id(self) -> str:
        """Return the recording device id."""
        return self._rec_dev_id

    @property
    def rev_year(self) -> str:
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
    def start_timestamp_ns(self) -> int:
        """Return the recording start time stamp, with nanoseconds resolution,
        as the number of nanoseconds since 1970-01-01 00:00:00 (in the time
        zone of the file timestamps). It can be converted with
        numpy.datetime64(value, "ns") or pandas.Timestamp(value)."""
        return _timestamp_ns(self._start_timestamp, self._start_nanosecond)

    @property
    def trigger_timestamp_ns(self) -> int:
        """Return the trigger time stamp, with nanoseconds resolution, as the
        number of nanoseconds since 1970-01-01 00:00:00 (in the time zone of
        the file timestamps)."""
        return _timestamp_ns(self._trigger_timestamp, self._trigger_nanosecond)

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

    @property
    def time_code(self) -> str:
        """Return the time code (IEEE C37.232) of the file timestamps, such as
        "-5h30", as written in the CFG file (2013 revision). Empty if absent."""
        return self._time_code

    @property
    def local_code(self) -> str:
        """Return the time code (IEEE C37.232) of the recording location's
        local time, such as "-5h30", as written in the CFG file (2013 revision).
        Empty if absent."""
        return self._local_code

    @property
    def time_offset(self) -> Union[dt.timedelta, None]:
        """Return the time difference to UTC of the file timestamps (from
        time_code), or None if unknown."""
        return self._time_offset

    @property
    def local_offset(self) -> Union[dt.timedelta, None]:
        """Return the time difference to UTC of the recording location's local
        time (from local_code), or None if unknown."""
        return self._local_offset

    @property
    def tmq_code(self) -> Union[int, None]:
        """Return the time quality code (IEEE C37.118) of the recording device
        clock, from 0 (locked) to 15 (clock failure), or None if absent."""
        return self._tmq_code

    @property
    def leap_second(self) -> Union[int, None]:
        """Return the leap second indicator: 0 (no leap second), 1 (added),
        2 (subtracted), 3 (clock source unable to provide leap second
        information), or None if absent."""
        return self._leap_second

    @property
    def start_timestamp_utc(self) -> Union[dt.datetime, None]:
        """Return the recording start time stamp as a timezone aware datetime
        in UTC, or None if the time code is unknown."""
        return _to_utc(self._start_timestamp, self._time_offset)

    @property
    def trigger_timestamp_utc(self) -> Union[dt.datetime, None]:
        """Return the trigger time stamp as a timezone aware datetime in UTC,
        or None if the time code is unknown."""
        return _to_utc(self._trigger_timestamp, self._time_offset)

    # Deprecated properties - Changed "Digital" for "Status"
    @property
    def digital_channels(self) -> list:
        """Returns the status channels bidimensional values list."""
        if not self._ignore_warnings:
            warnings.warn(FutureWarning("digital_channels is deprecated, "
                                        "use status_channels instead."))
        return self._status_channels

    @property
    def digital_count(self) -> int:
        """Returns the number of status channels."""
        if not self._ignore_warnings:
            warnings.warn(FutureWarning("digital_count is deprecated, "
                                        "use status_count instead."))
        return self._status_count

    def load(self, filepath, **kwargs):
        """Load and read a CFG file contents."""
        self._file_path = filepath

        if os.path.isfile(self._file_path):
            filtered_kwargs = {
                "encoding": kwargs.get("encoding", "utf-8")
            }
            with open(self._file_path, "r", **filtered_kwargs) as cfg:
                self._read_io(cfg)
        else:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    self._file_path)

    def read(self, cfg_lines):
        """Read CFG-format data of a FileIO or StringIO object."""
        if type(cfg_lines) is str:
            self._read_io(io.StringIO(cfg_lines))
        else:
            self._read_io(cfg_lines)

    def _read_io(self, cfg):
        """Read CFG-format lines and stores its data. Malformed lines raise
        ComtradeError."""
        try:
            self._parse_io(cfg)
        except ComtradeError:
            raise
        except (ValueError, IndexError, TypeError) as error:
            raise ComtradeError("Invalid CFG file: {}".format(error)) from error

    @staticmethod
    def _read_channel_line(cfg, kind: str, ichn: int) -> str:
        """Read the description line of a channel. A file declaring more
        channels than it describes is invalid (giving each missing channel
        default values would let a short file claim any number of
        channels)."""
        line = cfg.readline()
        if not line:
            raise ComtradeError("Missing the description line of {} channel "
                                "#{}.".format(kind, ichn + 1))
        return line

    def _parse_io(self, cfg):
        """Parse CFG-format lines and stores its data."""
        line_count = 0
        self._nrates = 1
        self._sample_rates = []
        self._analog_channels = []
        self._status_channels = []
        self._time_code = ""
        self._local_code = ""
        self._time_offset = None
        self._local_offset = None
        self._tmq_code = None
        self._leap_second = None

        # First line
        line = _strip_bom(cfg.readline())
        # station, device, and comtrade standard revision information
        packed = _read_sep_values(line)
        if 3 == len(packed):
            # only 1999 revision and above has the standard revision year
            self._station_name, self._rec_dev_id, self._rev_year = packed
            self._rev_year = self._rev_year.strip()

            if self._rev_year not in (REV_1991, REV_1999, REV_2001, REV_2013):
                if not self._ignore_warnings:
                    msg = _WARNING_UNKNOWN_REVISION.format(self._rev_year)
                    warnings.warn(Warning(msg))
        else:
            self._station_name, self._rec_dev_id = packed
            self._rev_year = REV_1991
        line_count = line_count + 1

        # Second line
        line = cfg.readline()
        # number of channels and its type
        totchn, achn, schn = _read_sep_values(line, 3, '0')
        self._channels_count = int(totchn)
        self._analog_count = int(achn[:-1])
        self._status_count = int(schn[:-1])
        self._analog_channels = [None] * self._analog_count
        self._status_channels = [None] * self._status_count
        line_count = line_count + 1

        # Analog channel description lines
        for ichn in range(self._analog_count):
            line = self._read_channel_line(cfg, "analog", ichn)
            packed = _read_sep_values(line, 10, '0')
            # unpack values
            n, name, ph, ccbm, uu, a, b, skew, cmin, cmax = packed[:10]
            # primary, secondary and PS fields (1999 revision and later)
            primary, secondary, pors = \
                (list(_read_sep_values(line)) + [''] * 3)[10:13]
            # type conversion
            n = int(n)
            a = float(a)
            b = _prevent_null(b, float, 0.0)
            skew = _prevent_null(skew, float, 0.0)
            cmin = float(cmin)
            cmax = float(cmax)
            primary = _prevent_null(primary, float, 1.0)
            secondary = _prevent_null(secondary, float, 1.0)
            pors = pors if pors else 'P'
            self.analog_channels[ichn] = AnalogChannel(n, a, b, skew,
                                                       cmin, cmax, name, uu, ph, ccbm, primary, secondary, pors)
            line_count = line_count + 1

        # Status channel description lines
        for ichn in range(self._status_count):
            line = self._read_channel_line(cfg, "status", ichn)
            # unpack values
            values = _read_sep_values(line)
            if len(values) == 3:
                # 1991 revision: n,ch_id,y
                n, name, y = values
                ph, ccbm = '', ''
            else:
                n, name, ph, ccbm, y = _read_sep_values(line, 5, '')
            # type conversion
            n = int(n)
            if len(y) == 0 and not self._ignore_warnings:
                warnings.warn(Warning(_WARNING_MISSING_NORMAL_STATE.format(n)))
            y = _prevent_null(y, int, 0)
            self.status_channels[ichn] = StatusChannel(n, name, ph, ccbm, y)
            line_count = line_count + 1

        # Frequency line
        line = cfg.readline()
        if len(line.strip()) > 0:
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
            self._sample_rates.append([samp, endsamp])
            line_count = line_count + 1

        # First data point time and time base
        line = cfg.readline()
        ts_str = line.strip()
        self._start_timestamp, nanosec, self._start_nanosecond = _read_timestamp(
            ts_str,
            self.rev_year,
            self._ignore_warnings
        )
        self._time_base = self._get_time_base(nanosec)
        line_count = line_count + 1

        # Event data point and time base
        line = cfg.readline()
        ts_str = line.strip()
        self._trigger_timestamp, nanosec, self._trigger_nanosecond = _read_timestamp(
            ts_str,
            self.rev_year,
            self._ignore_warnings
        )
        self._time_base = min([self.time_base, self._get_time_base(nanosec)])
        line_count = line_count + 1

        # DAT file type
        line = cfg.readline()
        self._ft = line.strip()
        line_count = line_count + 1

        # Timestamp multiplication factor
        if self._rev_year in (REV_1999, REV_2001, REV_2013):
            line = _eof_strip(cfg.readline())
            if len(line) > 0:
                self._time_multiplier = float(line)
            else:
                self._time_multiplier = 1.0
            line_count = line_count + 1

        # time_code and local_code
        if self._rev_year == REV_2013:
            line = _eof_strip(cfg.readline())

            if line:
                self._time_code, self._local_code = _read_sep_values(line, 2)
                self._time_offset = _parse_time_code(self._time_code,
                                                     self._ignore_warnings)
                self._local_offset = _parse_time_code(self._local_code,
                                                      self._ignore_warnings)
                line_count = line_count + 1

            # tmq_code and leapsec, which follow the time code line even when
            # that line is empty
            line = _eof_strip(cfg.readline())
            if line:
                tmq_code, leap_second = _read_sep_values(line, 2)
                self._tmq_code = _parse_tmq_code(tmq_code,
                                                 self._ignore_warnings)
                self._leap_second = _parse_leap_second(leap_second,
                                                       self._ignore_warnings)

    def _get_time_base(self, using_nanoseconds: bool):
        """
        Return the time base, which is based on the fractionary part of the 
        seconds in a timestamp (00.XXXXX).
        """
        if using_nanoseconds:
            return self.TIME_BASE_NANO_SEC
        else:
            return self.TIME_BASE_MICRO_SEC


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
        self.file_path = ""

        self._cfg = Cfg(**kwargs)

        # Default CFG data
        self._analog_channel_ids = []
        self._analog_phases = []
        self._status_channel_ids = []
        self._status_phases = []
        self._timestamp_critical = False

        # Data types
        self._use_numpy_arrays = kwargs.get("use_numpy_arrays", False)
        self._use_double_precision = kwargs.get("use_double_precision", False)

        # DAT file data
        self._time_values = _preallocate_values(
            "d" if self._use_double_precision else "f",
            0,
            self._use_numpy_arrays,
        )
        self._analog_values = []
        self._status_values = []
        self._total_samples = 0
        # whether the analog channels a and b fields came from a DAT file
        # (to keep them when saving in the same format)
        self._scaling_from_file = False
        # time values of each analog channel, with the channel time skew
        # (computed when first accessed)
        self._analog_time_values = None
        # analog values in primary and secondary units (computed when first
        # accessed)
        self._analog_scaled_values = {}

        # Additional CFF data (or additional comtrade files)
        self._hdr = None
        self._inf = None

        # DAT reader of lazy loaded data
        self._dat_reader = None

        if "ignore_warnings" in kwargs:
            self.ignore_warnings = kwargs["ignore_warnings"]
        else:
            self.ignore_warnings = False

    def close(self) -> None:
        """Close the DAT file of lazy loaded data. Channels not accessed
        before closing can't be read anymore."""
        if self._dat_reader is not None:
            self._dat_reader.close()
            self._dat_reader = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def station_name(self) -> str:
        """Return the recording device's station name."""
        return self._cfg.station_name

    @property
    def rec_dev_id(self) -> str:
        """Return the recording device id."""
        return self._cfg.rec_dev_id

    @property
    def rev_year(self) -> str:
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

    def inf_sections(self) -> Union[configparser.ConfigParser, None]:
        """Parse the INF file contents (1999 revision and later) and return
        them as a configparser.ConfigParser object, or None if there is no
        INF data.

        Section and key names keep their original case, such as
        "Public Record_Information". Values are strings. Duplicate sections
        and keys are allowed, the last value prevails. Raises
        configparser.Error if the contents are not in the INF (INI) format.
        """
        if not self._inf:
            return None
        parser = configparser.ConfigParser(
            delimiters=("=",),
            comment_prefixes=(";",),
            strict=False,
            interpolation=None,
        )
        parser.optionxform = str
        parser.read_string(self._inf)
        return parser

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
    def analog_time(self) -> list:
        """Return the time values list of each analog channel, i.e., the
        sample time plus the channel time skew."""
        if self._analog_time_values is None:
            self._analog_time_values = [self._get_skewed_time(channel.skew)
                                        for channel in self._cfg.analog_channels]
        return self._analog_time_values

    @property
    def analog_primary(self) -> list:
        """Return the analog channel values in primary units (such as the
        power system voltages and currents), using each channel's primary
        and secondary ratio information."""
        return self._get_analog_scaled("P")

    @property
    def analog_secondary(self) -> list:
        """Return the analog channel values in secondary units (such as the
        VT and CT outputs), using each channel's primary and secondary ratio
        information."""
        return self._get_analog_scaled("S")

    def _get_analog_scaled(self, side: str) -> list:
        if side not in self._analog_scaled_values:
            self._analog_scaled_values[side] = [
                _scale_values(values, self._get_ratio_factor(channel, side))
                for channel, values in zip(self._cfg.analog_channels,
                                           self._analog_values)]
        return self._analog_scaled_values[side]

    def _get_ratio_factor(self, channel, side: str) -> float:
        """Return the factor to convert the channel values to the side ("P"
        or "S") units."""
        pors = channel.pors.strip().upper()
        if pors == side:
            return 1.0
        if pors in ("P", "S") and channel.primary > 0 and channel.secondary > 0:
            if side == "P":
                return channel.primary / channel.secondary
            return channel.secondary / channel.primary
        if not self.ignore_warnings:
            warnings.warn(Warning(_WARNING_INVALID_RATIO.format(
                channel.n, channel.primary, channel.secondary, channel.pors)))
        return 1.0

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
    def start_timestamp_utc(self):
        """Return the recording start time stamp as a timezone aware datetime
        in UTC, or None if the time code is unknown (2013 revision)."""
        return self._cfg.start_timestamp_utc

    @property
    def trigger_timestamp_utc(self):
        """Return the trigger time stamp as a timezone aware datetime in UTC,
        or None if the time code is unknown (2013 revision)."""
        return self._cfg.trigger_timestamp_utc

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
    def start_timestamp_ns(self) -> int:
        """Return the recording start time stamp, with nanoseconds resolution,
        as the number of nanoseconds since 1970-01-01 00:00:00."""
        return self._cfg.start_timestamp_ns

    @property
    def trigger_timestamp_ns(self) -> int:
        """Return the trigger time stamp, with nanoseconds resolution, as the
        number of nanoseconds since 1970-01-01 00:00:00."""
        return self._cfg.trigger_timestamp_ns

    @property
    def trigger_time(self) -> float:
        """Return relative trigger time in seconds."""
        return (self._cfg.trigger_timestamp_ns - self._cfg.start_timestamp_ns) * 1E-9

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

    def _get_dat_reader(self, **kwargs):
        # case-insensitive comparison of file format
        ft_upper = self.ft.upper()
        dat_kwargs = {"use_numpy_arrays": self._use_numpy_arrays,
                      "use_double_precision": self._use_double_precision,
                      "rev_year": self.rev_year}
        dat_kwargs.update({key: kwargs[key] for key in _DAT_OPTIONS
                           if key in kwargs})
        if ft_upper == _TYPE_ASCII:
            dat = _AsciiDatReader(**dat_kwargs)
        elif ft_upper == _TYPE_BINARY:
            dat = _BinaryDatReader(**dat_kwargs)
        elif ft_upper == _TYPE_BINARY32:
            dat = _Binary32DatReader(**dat_kwargs)
        elif ft_upper == _TYPE_FLOAT32:
            dat = _Float32DatReader(**dat_kwargs)
        else:
            raise ComtradeError("Not supported data file format: {}".format(self.ft))
        return dat

    def read(self, cfg_lines, dat_lines_or_bytes, **kwargs) -> None:
        """
        Read CFG and DAT files contents. Expects FileIO or StringIO objects.

        Keyword arguments:
        lazy, start_time, end_time -- DAT loading options, see load().
        """
        self._cfg.read(cfg_lines)

        # channel ids
        self._cfg_extract_channels_ids(self._cfg)

        # channel phases
        self._cfg_extract_phases(self._cfg)

        dat = self._get_dat_reader(**kwargs)
        dat.read(dat_lines_or_bytes, self._cfg)

        # copy .dat object information
        self._dat_extract_data(dat)

    def _cfg_extract_channels_ids(self, cfg) -> None:
        self._analog_channel_ids = [channel.name for channel in cfg.analog_channels]
        self._status_channel_ids = [channel.name for channel in cfg.status_channels]

    def _cfg_extract_phases(self, cfg) -> None:
        self._analog_phases = [channel.ph for channel in cfg.analog_channels]
        self._status_phases = [channel.ph for channel in cfg.status_channels]

    def _dat_extract_data(self, dat) -> None:
        if dat.missing_samples > 0 and not self.ignore_warnings:
            warnings.warn(Warning(_WARNING_MISSING_SAMPLES.format(
                dat.missing_samples, self._cfg.sample_rates[-1][1])))
        self._time_values = dat.time
        self._analog_values = dat.analog
        self._status_values = dat.status
        self._total_samples = dat.total_samples
        self._scaling_from_file = True
        self._analog_time_values = None
        self._analog_scaled_values = {}
        # keep the reader of lazy loaded data, to close its file
        self.close()
        if dat.is_lazy:
            self._dat_reader = dat

    def _get_skewed_time(self, skew: float):
        """Return the time values shifted by a channel time skew (in microseconds)."""
        skew_seconds = skew * 1E-6
        if _HAS_NUMPY and isinstance(self._time_values, numpy.ndarray):
            return self._time_values + skew_seconds
        return array.array(self._time_values.typecode,
                           [t + skew_seconds for t in self._time_values])

    def to_dataframe(self, **kwargs) -> "pd.DataFrame":
        """Return a pandas DataFrame object with comtrade data."""
        if _HAS_PANDAS:
            index_type = kwargs.get("index_type", "time")
            data = {
                "time": self.time,
            }
            data.update({self.analog_channel_ids[i]: self.analog[i] for i in range(self.analog_count)})
            data.update({self.status_channel_ids[i]: self.status[i] for i in range(self.status_count)})
            df = pd.DataFrame(data)

            if index_type == "time":
                df.set_index("time", inplace=True)
            elif index_type == "sample":
                pass
            return df
        raise ComtradeError("pandas package is not installed.")

    @classmethod
    def from_dataframe(cls, df: "pd.DataFrame", **kwargs) -> "Comtrade":
        """
        Create a Comtrade object with the data of a pandas DataFrame, which
        can be saved as COMTRADE files with save(). Each column is a channel
        named after it.

        The time values are the DataFrame index: seconds (numbers), a
        DatetimeIndex or a TimedeltaIndex. A "time" column is used instead of
        a default RangeIndex, such as with to_dataframe(index_type="sample").

        Keyword arguments:
        station_name -- station name (Default: "")
        rec_dev_id -- recording device id (Default: "")
        rev_year -- COMTRADE revision year (Default: "2013")
        ft -- DAT file format saved by default: "ASCII", "BINARY",
            "BINARY32" or "FLOAT32" (Default: "ASCII")
        frequency -- line frequency in Hertz (Default: 0, unknown)
        time_column -- name of the column with the time values, instead of
            the index (Default: None)
        sample_rate -- samples per second of uniformly sampled data, to
            compute the time values instead of reading them (Default: None)
        start_timestamp -- timestamp of the first sample, as a datetime,
            pandas Timestamp or string (Default: the first DatetimeIndex value,
            or 1900-01-01 00:00:00)
        trigger_timestamp -- trigger timestamp (Default: start_timestamp)
        trigger_time -- alternatively, the trigger time in the scale of the
            time values, in seconds
        time_code, local_code -- time codes of the 2013 revision, such as
            "-3" (Default: from timezone aware timestamps, otherwise unknown)
        status_columns -- names of the status channel columns (Default: the
            boolean columns and the integer columns with only 0 and 1 values)
        channels -- dict of channel description fields per column name: uu,
            ph, ccbm, skew, primary, secondary and pors of analog channels; ph,
            ccbm and y of status channels. For instance,
            {"IA": {"uu": "A", "ph": "A", "primary": 600, "secondary": 5}}
            (Default: None)

        Other keyword arguments are passed to the Comtrade constructor. Values
        are stored with double precision, unless use_double_precision=False.
        """
        if not _HAS_PANDAS:
            raise ComtradeError("pandas package is not installed.")
        options = dict(kwargs)
        options.setdefault("use_double_precision", True)
        rec = cls(**options)
        cfg = rec._cfg

        rev_year = str(kwargs.get("rev_year", REV_2013))
        ft = kwargs.get("ft", _TYPE_ASCII).upper()
        count = len(df)

        # time values
        time_column = kwargs.get("time_column", None)
        sample_rate = kwargs.get("sample_rate", None)
        is_range_index = isinstance(df.index, pd.RangeIndex)
        if time_column is None and is_range_index and "time" in df.columns:
            time_column = "time"
        if time_column is not None:
            times_src = df[time_column]
            data = df.drop(columns=[time_column])
        else:
            times_src = df.index
            data = df
            if is_range_index and not sample_rate:
                raise ComtradeError("Missing time values: set the DataFrame "
                                    "index to the time values, or use the "
                                    "time_column or sample_rate arguments.")

        start_ns, offset = _timestamp_ns(dt.datetime(1900, 1, 1), 0), None
        if sample_rate:
            times = [i / sample_rate for i in range(count)]
        elif pd.api.types.is_datetime64_any_dtype(times_src):
            stamps = pd.DatetimeIndex(times_src)
            if count > 0:
                start_ns, offset = _to_timestamp_ns(stamps[0])
            if stamps.tz is not None:
                stamps = stamps.tz_localize(None)
            times = ((stamps - stamps[0]) / pd.Timedelta(seconds=1)).tolist() \
                if count > 0 else []
        elif pd.api.types.is_timedelta64_dtype(times_src):
            times = (pd.TimedeltaIndex(times_src) / pd.Timedelta(seconds=1)).tolist()
        else:
            times = [float(t) for t in times_src]
        if any(t1 < t0 for t0, t1 in itertools.pairwise(times)):
            raise ComtradeError("The time values must be in increasing order.")
        # time relative to the first sample
        first_time = times[0] if times else 0.0
        times = [t - first_time for t in times]

        # start and trigger timestamps
        if kwargs.get("start_timestamp", None) is not None:
            start_ns, offset = _to_timestamp_ns(kwargs["start_timestamp"])
        if kwargs.get("trigger_timestamp", None) is not None:
            trigger_ns, _ = _to_timestamp_ns(kwargs["trigger_timestamp"])
        elif kwargs.get("trigger_time", None) is not None:
            trigger_ns = start_ns + round((kwargs["trigger_time"] - first_time) * 1E9)
        else:
            trigger_ns = start_ns

        # channels
        channel_info = kwargs.get("channels", None) or {}
        status_columns = kwargs.get("status_columns", None)
        if status_columns is None:
            status_columns = [column for column in data.columns
                              if _is_status_series(data[column])]
        status_columns = set(status_columns)
        analog_columns = [c for c in data.columns if c not in status_columns]
        status_columns = [c for c in data.columns if c in status_columns]
        analog_channels = [AnalogChannel(i + 1, 1.0, name=str(column),
                                         **channel_info.get(column, {}))
                           for i, column in enumerate(analog_columns)]
        status_channels = [StatusChannel(i + 1, name=str(column),
                                         **channel_info.get(column, {}))
                           for i, column in enumerate(status_columns)]

        # CFG data
        cfg._station_name = str(kwargs.get("station_name", ""))
        cfg._rec_dev_id = str(kwargs.get("rec_dev_id", ""))
        cfg._rev_year = rev_year
        cfg._analog_channels = analog_channels
        cfg._status_channels = status_channels
        cfg._analog_count = len(analog_channels)
        cfg._status_count = len(status_channels)
        cfg._channels_count = cfg._analog_count + cfg._status_count
        cfg._frequency = float(kwargs.get("frequency", 0.0))
        if sample_rate:
            cfg._sample_rates = [[float(sample_rate), count]]
        else:
            cfg._sample_rates = _detect_sample_rates(times)
        cfg._nrates = 1
        cfg._timestamp_critical = cfg._sample_rates[0][0] == 0
        cfg._start_timestamp = _EPOCH + dt.timedelta(microseconds=start_ns // 1000)
        cfg._start_nanosecond = start_ns % 1000
        cfg._trigger_timestamp = _EPOCH + dt.timedelta(microseconds=trigger_ns // 1000)
        cfg._trigger_nanosecond = trigger_ns % 1000
        cfg._time_base = cfg._get_time_base(
            cfg._start_nanosecond != 0 or cfg._trigger_nanosecond != 0)
        cfg._ft = ft
        cfg._time_multiplier = 1.0
        cfg._time_code = str(kwargs.get("time_code", _format_time_code(offset)))
        cfg._local_code = str(kwargs.get("local_code", cfg._time_code))
        cfg._time_offset = _parse_time_code(cfg._time_code, rec.ignore_warnings)
        cfg._local_offset = _parse_time_code(cfg._local_code, rec.ignore_warnings)

        # channel values
        float_type = "d" if rec._use_double_precision else "f"

        def stored(values, typecode):
            target = _preallocate_values(typecode, count, rec._use_numpy_arrays)
            _copy_values(target, 0, values)
            return target

        rec._time_values = stored(times, float_type)
        rec._analog_values = [
            stored(data[column].to_numpy(dtype=float).tolist(), float_type)
            for column in analog_columns]
        rec._status_values = [
            stored([1 if value else 0 for value in data[column].tolist()], "i")
            for column in status_columns]
        rec._total_samples = count
        rec._cfg_extract_channels_ids(cfg)
        rec._cfg_extract_phases(cfg)
        return rec

    def save(self, cfg_file, dat_file=None, **kwargs) -> None:
        """
        Save the data as COMTRADE files: CFG and DAT files, plus the HDR and
        INF files if there is HDR or INF data, or a single CFF file (2013
        revision) if cfg_file has the CFF extension.

        dat_file is optional, and may be set if the DAT file name differs from
            the CFG file name.

        Analog values are written in the units of the analog property. For
        the integer formats (ASCII, BINARY and BINARY32), each channel's a and
        b fields are computed to use the whole range of the format, unless
        they were loaded from a DAT file of the same format and the values
        still fit (so loaded files are saved unchanged). FLOAT32 files keep the
        values as they are (a=1 and b=0). Missing values (NaN) are written as
        the missing data marker of the format.

        Time values are written as DAT timestamps. If the samples are
        uniformly spaced, the sample rate is written too. If the first time
        value isn't zero (e.g., time window loaded), the start timestamp is
        moved to the first sample.

        Keyword arguments:
        ft -- DAT file format: "ASCII", "BINARY", "BINARY32" or "FLOAT32"
            (Default: the ft property)
        rev_year -- COMTRADE revision year: "1999", "2001" or "2013" (Default:
            the rev_year property, or "2013" if it's "1991")
        encoding -- encoding of the text files (Default: "utf-8")
        """
        rev_year = str(kwargs.get("rev_year", self.rev_year
                                  if self.rev_year in _WRITABLE_REVISIONS
                                  else REV_2013))
        ft = (kwargs.get("ft", None) or self.ft or _TYPE_ASCII).upper()
        encoding = kwargs.get("encoding", "utf-8")
        if rev_year not in _WRITABLE_REVISIONS:
            raise ComtradeError("Can't write COMTRADE files of revision {}. "
                                "Use one of: {}.".format(
                                    rev_year, ", ".join(_WRITABLE_REVISIONS)))
        if ft not in _INT_LIMITS and ft != _TYPE_FLOAT32:
            raise ComtradeError("Not supported data file format: {}".format(ft))
        if ft in _FORMATS_2013 and rev_year != REV_2013:
            raise ComtradeError("{} data files require the 2013 revision.".format(ft))

        cfg_text, dat_data = self._build_files(ft, rev_year)

        file_ext = cfg_file[-3:]
        if file_ext.upper() == "CFF":
            if rev_year != REV_2013:
                raise ComtradeError("CFF files require the 2013 revision.")
            sections = [("CFG", cfg_text), ("INF", self._inf or ""),
                        ("HDR", self._hdr or "")]
            contents = b""
            for name, text in sections:
                text = _to_crlf(text)
                if text and not text.endswith(_NEWLINE):
                    text += _NEWLINE
                contents += "--- file type: {} ---{}{}".format(
                    name, _NEWLINE, text).encode(encoding)
            if ft == _TYPE_ASCII:
                contents += "--- file type: DAT ASCII ---{}".format(
                    _NEWLINE).encode(encoding) + dat_data
            else:
                contents += "--- file type: DAT {}: {} ---{}".format(
                    ft, len(dat_data), _NEWLINE).encode(encoding) + dat_data
            with open(cfg_file, "wb") as file:
                file.write(contents)
            return

        if file_ext.upper() != "CFG":
            raise ComtradeError(r"Expected CFG or CFF file path, instead got \"{}\".".format(cfg_file))
        basename = cfg_file[:-3]
        if dat_file is None:
            dat_file = basename + _get_same_case(file_ext, self.EXT_DAT)
        files = [(cfg_file, cfg_text.encode(encoding)), (dat_file, dat_data)]
        for ext, text in ((self.EXT_INF, self._inf), (self.EXT_HDR, self._hdr)):
            if text:
                files.append((basename + _get_same_case(file_ext, ext),
                              _to_crlf(text).encode(encoding)))
        for path, contents in files:
            with open(path, "wb") as file:
                file.write(contents)

    def _build_files(self, ft: str, rev_year: str) -> tuple:
        """Return the CFG file text and the DAT file contents (bytes)."""
        cfg = self._cfg
        if len(self.analog) != cfg.analog_count or \
                len(self.status) != cfg.status_count:
            raise ComtradeError("The number of channel values differs from the "
                                "number of channels.")
        times = _values_list(self.time)
        count = len(times)
        if any(t1 < t0 for t0, t1 in itertools.pairwise(times)):
            raise ComtradeError("The time values must be in increasing order.")

        # The first sample is at the start timestamp: time values (relative to
        # the start timestamp) not starting at zero move it.
        start_ns = cfg.start_timestamp_ns
        trigger_ns = cfg.trigger_timestamp_ns
        # The 1999 revision time stamps have a resolution of 1 microsecond;
        # the nanoseconds resolution is only available in later revisions.
        nanoseconds = rev_year != REV_1999 and (
            cfg.time_base < Cfg.TIME_BASE_MICRO_SEC or
            start_ns % 1000 != 0 or trigger_ns % 1000 != 0)
        unit_ns = 1 if nanoseconds else 1000
        first_time = times[0] if count else 0.0
        if first_time != 0.0:
            start_ns += round(first_time * 1E9 / unit_ns) * unit_ns
            times = [t - first_time for t in times]

        # sample rates: the CFG ones if they still describe the samples,
        # otherwise detected from the time values
        sample_rates = cfg.sample_rates
        if sample_rates and sample_rates[-1][1] == count and first_time == 0.0:
            nrates = 0 if cfg.timestamp_critical else len(sample_rates)
        else:
            sample_rates = _detect_sample_rates(times)
            nrates = 0 if sample_rates[0][0] == 0 else 1

        # DAT timestamps, in time base units times the time multiplier
        time_unit = unit_ns * 1E-9
        max_timestamp = round(times[-1] / time_unit) if count else 0
        timemult = 1 if max_timestamp <= _MAX_TIMESTAMP else \
            math.ceil(max_timestamp / _MAX_TIMESTAMP)
        timestamps = [round(t / (time_unit * timemult)) for t in times]

        # channels
        keep_scaling = self._scaling_from_file and ft == self.ft.upper()
        analog_lines = []
        analog_raw = []
        for channel, values in zip(cfg.analog_channels, self.analog):
            raw, a, b, cmin, cmax = _encode_analog(_values_list(values), channel,
                                                   ft, keep_scaling)
            analog_raw.append(raw)
            analog_lines.append(_SEPARATOR.join([
                str(channel.n),
                _check_field(channel.name, "Channel names"),
                _check_field(channel.ph, "Channel phases"),
                _check_field(channel.ccbm, "Channel circuit components"),
                _check_field(channel.uu, "Channel units"),
                _format_number(a), _format_number(b),
                _format_number(channel.skew),
                _format_number(cmin), _format_number(cmax),
                _format_number(channel.primary),
                _format_number(channel.secondary),
                _check_field(channel.pors, "Channel PS fields")]))
        status_values = [[1 if value else 0 for value in _values_list(values)]
                         for values in self.status]
        status_lines = [_SEPARATOR.join([
            str(channel.n),
            _check_field(channel.name, "Channel names"),
            _check_field(channel.ph, "Channel phases"),
            _check_field(channel.ccbm, "Channel circuit components"),
            str(channel.y)]) for channel in cfg.status_channels]

        # CFG file
        lines = [_SEPARATOR.join([_check_field(cfg.station_name, "Station name"),
                                  _check_field(cfg.rec_dev_id, "Recording device id"),
                                  rev_year]),
                 "{},{}A,{}D".format(cfg.analog_count + cfg.status_count,
                                     cfg.analog_count, cfg.status_count)]
        lines += analog_lines
        lines += status_lines
        lines.append(_format_number(cfg.frequency))
        lines.append(str(nrates))
        lines += ["{},{}".format(_format_number(samp), int(endsamp))
                  for samp, endsamp in sample_rates]
        lines.append(_format_timestamp(start_ns, nanoseconds))
        lines.append(_format_timestamp(trigger_ns, nanoseconds))
        lines.append(ft)
        lines.append(_format_number(timemult))
        if rev_year == REV_2013:
            lines.append(_SEPARATOR.join([
                _check_field(cfg.time_code, "Time code"),
                _check_field(cfg.local_code, "Local code")]))
            lines.append(_SEPARATOR.join([
                "" if cfg.tmq_code is None else "{:X}".format(cfg.tmq_code),
                "" if cfg.leap_second is None else str(cfg.leap_second)]))
        cfg_text = _NEWLINE.join(lines) + _NEWLINE

        # DAT file
        sample_numbers = range(1, count + 1)
        if ft == _TYPE_ASCII:
            columns = [map(str, sample_numbers), map(str, timestamps)]
            columns += [[_ASCII_MISSING if value is None else str(value)
                         for value in raw] for raw in analog_raw]
            columns += [map(str, values) for values in status_values]
            dat_data = "".join(_SEPARATOR.join(row) + _NEWLINE
                               for row in zip(*columns)).encode("ascii")
        else:
            missing = _BINARY_MISSING[ft]
            # groups of 16 status channels, one bit each
            status_words = []
            for igroup in range(0, len(status_values), 16):
                words = [0] * count
                for bit, values in enumerate(status_values[igroup:igroup + 16]):
                    words = [word | (value << bit) for word, value in zip(words, values)]
                status_words.append(words)
            row_struct = struct.Struct("<II" +
                                       _BINARY_ANALOG_TYPECODE[ft] * len(analog_raw) +
                                       "H" * len(status_words))
            columns = [sample_numbers, timestamps]
            columns += [[missing if value is None else value for value in raw]
                        for raw in analog_raw]
            columns += status_words
            dat_data = b"".join(row_struct.pack(*row) for row in zip(*columns))
        return cfg_text, dat_data

    def load(self, cfg_file, dat_file=None, **kwargs) -> "Comtrade":
        """
        Load CFG, DAT, INF, and HDR files. Each must be a FileIO or StringIO
        object. dat_file, inf_file, and hdr_file are optional (Default: None).

        cfg_file is the cfg file path, including its extension.
        dat_file is optional, and may be set if the DAT file name differs from 
            the CFG file name.

        Keyword arguments:
        inf_file -- optional INF file path (Default = None)
        hdr_file -- optional HDR file path (Default = None)
        start_time -- load only samples at or after this time, in seconds,
            in the same scale of the time property (Default = None)
        end_time -- load only samples at or before this time, in seconds
            (Default = None)
        lazy -- for binary DAT files, keep the file memory mapped and decode
            each channel's values when first accessed. Call close(), or use
            the object as a context manager, to close the file
            (Default = False)
        """
        inf_file = kwargs.get("inf_file", None)
        hdr_file = kwargs.get("hdr_file", None)
        dat_options = {key: kwargs[key] for key in _DAT_OPTIONS if key in kwargs}
        file_kwargs = {}
        if "encoding" in kwargs:
            file_kwargs["encoding"] = kwargs["encoding"]

        # which extension: CFG or CFF?
        file_ext = cfg_file[-3:]
        file_ext_upper = file_ext.upper()
        if file_ext_upper == "CFF":
            # check if the CFF file exists
            self._load_cff(cfg_file, **dat_options, **file_kwargs)

        elif file_ext_upper == "CFG":
            basename = cfg_file[:-3]
            # if not informed, infer dat_file with cfg_file
            if dat_file is None:
                dat_file = cfg_file[:-3] + _get_same_case(file_ext, self.EXT_DAT)

            if inf_file is None:
                inf_file = basename + _get_same_case(file_ext, self.EXT_INF)

            if hdr_file is None:
                hdr_file = basename + _get_same_case(file_ext, self.EXT_HDR)

            # load both cfg and dat
            self._load_cfg(cfg_file, **file_kwargs)
            self._load_dat(dat_file, **dat_options)

            # Load additional inf and hdr files, if they exist.
            self._load_inf(inf_file, **file_kwargs)
            self._load_hdr(hdr_file, **file_kwargs)

        else:
            raise ComtradeError(r"Expected CFG file path, instead got \"{}\".".format(cfg_file))

        return self

    def _load_cfg(self, cfg_filepath, **kwargs):
        self._cfg.load(cfg_filepath, **kwargs)

        # channel ids
        self._cfg_extract_channels_ids(self._cfg)

        # channel phases
        self._cfg_extract_phases(self._cfg)

    def _load_dat(self, dat_filepath, **kwargs):
        dat = self._get_dat_reader(**kwargs)
        dat.load(dat_filepath, self._cfg)

        # copy .dat object information
        self._dat_extract_data(dat)

    def _load_inf(self, inf_file, **kwargs):
        if os.path.exists(inf_file):
            kwargs["encoding"] = kwargs.get("encoding", "utf-8")
            with open(inf_file, 'r', **kwargs) as file:
                self._inf = _replace_sub(_strip_bom(file.read()))
                if len(self._inf) == 0:
                    self._inf = None
        else:
            self._inf = None

    def _load_hdr(self, hdr_file, **kwargs):
        if os.path.exists(hdr_file):
            kwargs["encoding"] = kwargs.get("encoding", "utf-8")
            with open(hdr_file, 'r', **kwargs) as file:
                self._hdr = _replace_sub(_strip_bom(file.read()))
                if len(self._hdr) == 0:
                    self._hdr = None
        else:
            self._hdr = None

    @staticmethod
    def _read_mixed_text_bin_data_as_text(cff_file, encoding: str = "utf-8") -> str:
        chunk_delimiter = b"\n"
        current_chunk = []
        while True:
            current_value = cff_file.read(1)
            if not current_value:
                break
            if current_value != chunk_delimiter:
                current_chunk.append(current_value)
            else:
                line = b"".join(current_chunk).decode(encoding, errors="ignore")
                yield _strip_bom(line).strip()
                current_chunk = []

    def _load_cff(self, cff_file_path: str, **kwargs):
        # stores each file type lines
        cfg_lines = []
        dat_lines = []
        hdr_lines = []
        inf_lines = []
        header_re = re.compile(_CFF_HEADER_REXP)
        # text encoding of the CFG, HDR and INF sections
        encoding = kwargs.get("encoding", "utf-8")

        with open(cff_file_path, "rb") as cff_file:
            # file type: CFG, HDR, INF, DAT
            ftype = None
            # file format: ASCII, BINARY, BINARY32, FLOAT32
            fformat = None

            line_number = 0
            last_match = None
            for current_line in self._read_mixed_text_bin_data_as_text(cff_file,
                                                                       encoding):
                line_number += 1
                mobj = header_re.match(current_line.strip().upper())
                if mobj is not None:
                    last_match = mobj
                    groups = last_match.groups()
                    ftype = groups[0]
                    if groups[1] is not None:
                        fformat = groups[1]
                        if ftype == "DAT" and fformat != _TYPE_ASCII:
                            break

                elif last_match is not None and ftype == "CFG":
                    cfg_lines.append(current_line.strip())

                elif last_match is not None and ftype == "HDR":
                    hdr_lines.append(current_line.strip())

                elif last_match is not None and ftype == "INF":
                    inf_lines.append(current_line.strip())

                elif last_match is not None and ftype == "DAT" and fformat == _TYPE_ASCII:
                    dat_lines.append(current_line.strip())

            if fformat == _TYPE_ASCII:
                # process ASCII CFF data
                self.read("\n".join(cfg_lines), "\n".join(dat_lines), **kwargs)
            else:
                # read remaining data as .dat values.
                dat_bytes = cff_file.read()
                self.read("\n".join(cfg_lines), dat_bytes, **kwargs)

        # stores additional data
        self._hdr = "\n".join(hdr_lines)

        self._inf = "\n".join(inf_lines)

    def cfg_summary(self):
        """Returns the CFG attributes summary string."""
        header_line = "Channels (Analog,Digital,Total): {}A + {}D = {}"
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
        return ','.join(fields)


class AnalogChannel(Channel):
    """Holds analog channel description data."""

    def __init__(self, n: int, a: float, b=0.0, skew=0.0, cmin=-32767.0,
                 cmax=32767.0, name='', uu='', ph='', ccbm='', primary=1.0,
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


class _DatReader:
    """Abstract DatReader class. Used to parse DAT file contents."""
    read_mode = "r"

    def __init__(self, **kwargs):
        """DatReader class constructor."""
        self._use_numpy_arrays = kwargs.get("use_numpy_arrays", False)
        self._use_double_precision = kwargs.get("use_double_precision", False)
        self._rev_year = kwargs.get("rev_year", REV_2013)
        # loading options
        self._lazy = kwargs.get("lazy", False)
        self._start_time = kwargs.get("start_time", None)
        self._end_time = kwargs.get("end_time", None)
        # memory mapped DAT file
        self._mmap = None

        self.file_path = ""
        self._content = None
        self._cfg = None
        self.time = _preallocate_values(
            "d" if self._use_double_precision else "f",
            0,
            self._use_numpy_arrays,
        )
        self.analog = []
        self.status = []
        self._total_samples = 0
        # samples declared in the CFG file, but missing in the DAT file
        self.missing_samples = 0

        # To be replaced by subclasses.
        self.DATA_MISSING = None

    @property
    def total_samples(self):
        """Return the total samples (per channel)."""
        return self._total_samples

    @property
    def is_lazy(self) -> bool:
        """Return whether channel values are decoded when first accessed."""
        return False

    @property
    def _has_time_window(self) -> bool:
        return self._start_time is not None or self._end_time is not None

    def _in_time_window(self, time: float) -> bool:
        return (self._start_time is None or time >= self._start_time) and \
            (self._end_time is None or time <= self._end_time)

    def _as_stored_times(self, times: list) -> list:
        """Return the times rounded to the precision of the time values, so
        that time window limits taken from them select the same samples."""
        return list(array.array("d" if self._use_double_precision else "f",
                                times))

    def close(self):
        """Close the memory mapped DAT file, if any."""
        if self._mmap is not None:
            self._mmap.close()
            self._mmap = None

    def load(self, dat_filepath, cfg, **kwargs):
        """Load a DAT file and parse its contents."""
        self.file_path = dat_filepath
        self._content = None
        if os.path.isfile(self.file_path):
            self._cfg = cfg
            self._preallocate()
            if self.read_mode == "rb":
                # binary files are memory mapped, so only the needed rows
                # and fields are read
                with open(self.file_path, "rb") as file:
                    if os.fstat(file.fileno()).st_size > 0:
                        self._mmap = mmap.mmap(file.fileno(), 0,
                                               access=mmap.ACCESS_READ)
                try:
                    self._checked_parse(self._mmap if self._mmap is not None else b"")
                except BaseException:
                    self.close()
                    raise
                if not self.is_lazy:
                    self.close()
            else:
                if "encoding" not in kwargs:
                    kwargs["encoding"] = "utf-8"
                with open(self.file_path, self.read_mode, **kwargs) as contents:
                    self._checked_parse(contents)
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
        self._checked_parse(dat_lines)

    def _checked_parse(self, contents):
        """Parse the DAT contents. Malformed contents raise ComtradeError."""
        try:
            self.parse(contents)
        except ComtradeError:
            raise
        except (ValueError, IndexError, TypeError, struct.error) as error:
            raise ComtradeError("Invalid DAT file: {}".format(error)) from error

    def _preallocate(self):
        # the number of samples declared in the CFG file. Values are only
        # allocated for the samples actually in the DAT file, so that memory
        # use follows the DAT file size, not the (untrusted) CFG counts.
        self._total_samples = self._cfg.sample_rates[-1][1]  # last samp field
        self.missing_samples = 0

        # first sample number and its time for each sample rate segment.
        # Each sample is 1/samp after the previous one, where samp is the
        # sample rate of the segment the sample belongs to.
        self._rate_segments = []
        start_n, start_time = 1, 0.0
        for samp, endsamp in self._cfg.sample_rates:
            self._rate_segments.append((samp, endsamp, start_n, start_time))
            if samp != 0.0:
                start_time += (endsamp - start_n) / samp
            start_n = endsamp

    def _get_rate_segment(self, n) -> tuple:
        """Get the sampling rate, first sample number and its time for the
        sample rate segment of a sample n (1-based index)."""
        for samp, endsamp, start_n, start_time in self._rate_segments:
            if n <= endsamp:
                return samp, start_n, start_time
        # samples beyond the last endsamp continue at the last sample rate
        samp, _, start_n, start_time = self._rate_segments[-1]
        return samp, start_n, start_time

    def _get_time(self, n: int, ts_value, time_base: float,
                  time_multiplier: float):
        """Return the time of the sample n (1-based index). ts_value is the
        DAT file timestamp, or None if it is missing. Each reader translates
        its own format's missing marker to None, so that every numeric
        value remains a valid timestamp."""
        # TODO: add option to enforce dat file timestamp, when available.
        sample_rate, start_n, start_time = self._get_rate_segment(n)
        if not self._cfg.timestamp_critical or ts_value is None:
            # if the timestamp is missing, use calculated.
            if sample_rate != 0.0:
                return start_time + (n - start_n) / sample_rate
            else:
                raise ComtradeError("Missing timestamp and no sample rate "
                                    "provided.")
        else:
            # Use provided timestamp if it's not missing
            return ts_value * time_base * time_multiplier

    def parse(self, contents):
        """Virtual method, parse DAT file contents."""
        pass


class _AsciiDatReader(_DatReader):
    """ASCII format DatReader subclass."""

    def __init__(self, **kwargs):
        # Call the initialization for the inherited class
        super().__init__(**kwargs)
        self.ASCII_SEPARATOR = _SEPARATOR

        if self._rev_year == REV_1991:
            self.DATA_MISSING = ""
        else:
            self.DATA_MISSING = "99999"

    def parse(self, contents):
        """Parse a ASCII file contents."""
        # Check if contents has been read as an io.BytesIO object, if so, decode into a string.
        contents = contents.decode() if (type(contents) is bytes) else contents

        analog_count = self._cfg.analog_count
        status_count = self._cfg.status_count
        time_mult = self._cfg.timemult
        time_base = self._cfg.time_base
        missing = self.DATA_MISSING
        nan = float('nan')

        # auxiliary vectors (channels gains and offsets)
        a = [x.a for x in self._cfg.analog_channels]
        b = [x.b for x in self._cfg.analog_channels]

        # the values grow as the lines are read
        float_type = "d" if self._use_double_precision else "f"
        time_values = array.array(float_type)
        analog_values = [array.array(float_type) for _ in range(analog_count)]
        status_values = [array.array("i") for _ in range(status_count)]

        # extract lines
        if type(contents) is str:
            lines = contents.splitlines()
        else:
            lines = contents
        lines = iter(lines)
        # a UTF-8 BOM may precede the first sample number
        first_line = next(lines, None)
        if first_line is not None:
            lines = itertools.chain([_strip_bom(first_line)], lines)
        # Blank lines and the <sub> (0x1A) end of file marker, which the 1991
        # and 1999 revisions place after the last data row, are not samples.
        lines = (line for line in map(_eof_strip, lines) if line)

        # Lines are read in blocks and the values of each channel in a block
        # are converted at once, which is much faster than one by one.
        block_size = max(1, _ASCII_BLOCK_VALUES // (analog_count + status_count + 2))
        # rows read (all of them, or up to past the time window end)
        rows_read = 0
        past_window = False
        while rows_read < self._total_samples and not past_window:
            rows = [line.split(self.ASCII_SEPARATOR) for line in
                    itertools.islice(lines, min(block_size, self._total_samples - rows_read))]
            if not rows:
                break
            rows_read += len(rows)

            # Read time. A missing timestamp is a blank field in ASCII files:
            # 0xFFFFFFFF is the missing marker of binary files only, and a
            # valid decimal timestamp here.
            times = [self._get_time(int(values[0]),
                                    float(values[1]) if values[1].strip() else None,
                                    time_base, time_mult)
                     for values in rows]
            if self._has_time_window:
                # samples are in time order: stop after the window end
                past_window = self._end_time is not None and \
                    times[-1] > self._end_time
                times = self._as_stored_times(times)
                selected = [k for k, t in enumerate(times) if self._in_time_window(t)]
                rows = [rows[k] for k in selected]
                times = [times[k] for k in selected]
            time_values.extend(times)

            for i in range(analog_count):
                ai, bi = a[i], b[i]
                # the missing data marker may be surrounded by whitespace
                analog_values[i].extend(
                    [ai * float(value) + bi if value.strip() != missing else nan
                     for value in map(operator.itemgetter(i + 2), rows)])

            # status values are the last ones of each line
            for i in range(status_count):
                status_values[i].extend(
                    map(int, map(operator.itemgetter(i - status_count), rows)))

        if not past_window:
            self.missing_samples = self._total_samples - rows_read
        # only the rows in the DAT file (and in the time window) are loaded
        self._total_samples = len(time_values)
        use_numpy = self._use_numpy_arrays
        self.time = _as_values(time_values, use_numpy)
        self.analog = [_as_values(values, use_numpy) for values in analog_values]
        self.status = [_as_values(values, use_numpy) for values in status_values]


class _BinaryDatReader(_DatReader):
    """16-bit binary format DatReader subclass."""

    def __init__(self, **kwargs):
        # Call the initialization for the inherited class
        super().__init__(**kwargs)
        self.ANALOG_BYTES = 2
        self.STATUS_BYTES = 2
        self.TIME_BYTES = 4
        self.SAMPLE_NUMBER_BYTES = 4

        # array typecodes of the analog and the 16 bits status values
        self.ANALOG_TYPECODE = "h"
        self.STATUS_TYPECODE = "H"

        if self._rev_year == REV_1991:
            self.DATA_MISSING = -1  # 0xFFFF
        else:
            self.DATA_MISSING = -32768  # 0x8000

        self.read_mode = "rb"

    def _get_analog_values(self, yint, a: float, b: float):
        """Return the analog values a * yint + b of the raw values yint,
        with NaN for missing raw values."""
        if _HAS_NUMPY and self._use_numpy_arrays:
            y = numpy.asarray(yint, dtype=numpy.float64)
            is_missing = y == self.DATA_MISSING
            y = a * y + b
            y[is_missing] = numpy.nan
            return y
        missing = self.DATA_MISSING
        nan = float('nan')
        return [a * value + b if value != missing else nan for value in yint]

    def _get_status_values(self, group, chnindex: int):
        """Return the status values of the bit chnindex of a group of 16 bits."""
        if _HAS_NUMPY and self._use_numpy_arrays:
            return (numpy.asarray(group) >> chnindex) & 1
        return [(word >> chnindex) & 1 for word in group]

    @property
    def is_lazy(self) -> bool:
        return self._lazy

    def close(self):
        """Close the DAT file contents. Channel values not decoded yet can't
        be read anymore."""
        self._contents = None
        super().close()

    def parse(self, contents):
        """Parse DAT binary file contents."""
        time_mult = self._cfg.timemult
        time_base = self._cfg.time_base
        achannels = self._cfg.analog_count
        schannels = self._cfg.status_count

        dbytes = self.STATUS_BYTES * math.ceil(schannels / 16.0)

        if isinstance(contents, io.TextIOBase) or \
                isinstance(contents, io.BufferedIOBase):
            # Read all buffer contents
            contents = contents.read()

        # Each row has the sample number, the time stamp, the analog values
        # and the groups of 16 status bits. Only whole rows are read, up to
        # the total samples.
        row_size = self.SAMPLE_NUMBER_BYTES + self.TIME_BYTES + \
            achannels * self.ANALOG_BYTES + dbytes
        rows = min(len(contents) // row_size, self.total_samples)
        self.missing_samples = self.total_samples - rows

        def get_time(n: int, ts_val: int) -> float:
            # 0xFFFFFFFF marks a missing timestamp in binary files
            return self._get_time(n, ts_val if ts_val != _TIMESTAMP_MISSING else None,
                                  time_base, time_mult)

        # rows to decode: the ones within the time window, or all of them
        # (samples missing in the DAT file have zero values)
        first_row = 0
        if self._has_time_window:
            # samples are in time order: binary search the window limits,
            # reading only the time of a few rows
            row_time_struct = struct.Struct("<II")

            def row_time(k: int) -> float:
                return self._as_stored_times(
                    [get_time(*row_time_struct.unpack_from(contents, k * row_size))])[0]

            end_row = rows
            if self._start_time is not None:
                first_row = bisect.bisect_left(range(rows), self._start_time,
                                               key=row_time)
            if self._end_time is not None:
                end_row = bisect.bisect_right(range(rows), self._end_time,
                                              lo=first_row, key=row_time)
            rows = max(0, end_row - first_row)
        # only the rows in the DAT file (and in the time window) are loaded
        self._total_samples = rows

        # Each field is unpacked from all rows at once, which is much faster
        # than unpacking the rows one by one.
        sample_numbers = _unpack_column(contents, row_size, 0, "I", first_row, rows)
        timestamps = _unpack_column(contents, row_size,
                                    self.SAMPLE_NUMBER_BYTES, "I", first_row, rows)
        times = [get_time(n, ts_val) for n, ts_val in zip(sample_numbers, timestamps)]
        self._contents = contents
        self._row_size = row_size
        self._first_row = first_row
        self._rows = rows

        self.time = _preallocate_values(
            "d" if self._use_double_precision else "f",
            self._total_samples,
            self._use_numpy_arrays,
        )
        _copy_values(self.time, 0, times)

        if self._lazy:
            self.analog = _LazyChannels(achannels, self._decode_analog)
            self.status = _LazyChannels(schannels, self._decode_status)
        else:
            self.analog = [self._decode_analog(i) for i in range(achannels)]
            self.status = [self._decode_status(i) for i in range(schannels)]
            self._contents = None

    def _unpack(self, offset: int, typecode: str):
        """Unpack the field at offset of the rows to decode."""
        if self._contents is None:
            raise ComtradeError("The DAT file is closed.")
        return _unpack_column(self._contents, self._row_size, offset,
                              typecode, self._first_row, self._rows)

    def _decode_analog(self, ichannel: int):
        """Return the values of the analog channel ichannel."""
        channel = self._cfg.analog_channels[ichannel]
        offset = self.SAMPLE_NUMBER_BYTES + self.TIME_BYTES + \
            ichannel * self.ANALOG_BYTES
        yint = self._unpack(offset, self.ANALOG_TYPECODE)
        values = _preallocate_values(
            "d" if self._use_double_precision else "f",
            self._total_samples,
            self._use_numpy_arrays,
        )
        _copy_values(values, 0, self._get_analog_values(yint, channel.a, channel.b))
        return values

    def _decode_status(self, ichannel: int):
        """Return the values of the status channel ichannel."""
        igroup, chnindex = divmod(ichannel, 16)
        offset = self.SAMPLE_NUMBER_BYTES + self.TIME_BYTES + \
            self._cfg.analog_count * self.ANALOG_BYTES + \
            igroup * self.STATUS_BYTES
        group = self._unpack(offset, self.STATUS_TYPECODE)
        values = _preallocate_values("i", self._total_samples,
                                     self._use_numpy_arrays)
        _copy_values(values, 0, self._get_status_values(group, chnindex))
        return values


class _Binary32DatReader(_BinaryDatReader):
    """32-bit binary format DatReader subclass."""

    def __init__(self, **kwargs):
        # Call the initialization for the inherited class
        super().__init__(**kwargs)
        self.ANALOG_BYTES = 4
        self.ANALOG_TYPECODE = "i"

        # maximum negative value
        self.DATA_MISSING = -2147483648  # 0x80000000


class _Float32DatReader(_BinaryDatReader):
    """Single precision (float) binary format DatReader subclass."""

    def __init__(self, **kwargs):
        # Call the initialization for the inherited class
        super().__init__(**kwargs)
        self.ANALOG_BYTES = 4
        self.ANALOG_TYPECODE = "f"

        # Most negative single precision value (-3.40282347E+38), the missing
        # data marker of the FLOAT32 format. It has to be the single precision
        # value, since the values are converted to double precision when read.
        self.DATA_MISSING = _FLOAT32_MISSING


def load(cfg_or_cff_file_path, dat_file_path=None, **kwargs) -> Comtrade:
    """Load and read comtrade files contents."""
    return Comtrade(**kwargs).load(cfg_or_cff_file_path, dat_file_path, **kwargs)


def load_as_dataframe(cfg_or_cff_file_path, dat_file_path=None, **kwargs) -> "pd.DataFrame":
    """Load and read comtrade files contents and returns a dataframe."""
    return Comtrade(**kwargs).load(cfg_or_cff_file_path,
                                   dat_file_path,
                                   use_numpy_arrays=True, **kwargs).to_dataframe(**kwargs)


def from_dataframe(df: "pd.DataFrame", **kwargs) -> Comtrade:
    """Create a Comtrade object with the data of a pandas DataFrame, which can
    be saved as COMTRADE files with save(). See Comtrade.from_dataframe()."""
    return Comtrade.from_dataframe(df, **kwargs)

