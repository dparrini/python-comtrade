# Python Comtrade

__Python Comtrade__ is a module for Python 3 designed to read and write _Common Format for Transient Data Exchange_ (COMTRADE) files. These consists of oscillography data recorded during power system outages, control systems tests, validation and tests of field equipment, protective relaying logs, etc. The COMTRADE format is defined by IEEE Standards, summarized in the table below. Some equipment vendors put additional information in proprietary versions of it. This module aims IEEE definitions but may support those proprietary versions.


| Standard                                  | Revision |
|:------------------------------------------|:--------:|
| IEEE C37.111(TM)-1991                     |   1991   |
| IEEE C37.111(TM)-1999                     |   1999   |
| IEC 60255-24:2001                         |   2001   |
| IEEE C37.111(TM)-2013 / IEC 60255-24:2013 |   2013   |


## Installation

```
pip install comtrade
```

Or just copy `comtrade.py` from this repository.

### Requirements

- Python 3.11 or newer
- (optional) numpy for speed improvement: `pip install "comtrade[numpy]"`
- (optional) pandas for data frame support: `pip install "comtrade[pandas]"`


## How to Use

The examples below shows how to open both CFG and DAT files or the new CFF file to plot (using `pyplot`) analog channel oscillography.


### CFG and DAT files (all revisions)

Comtrade files separated in CFG and DAT formats can also be read with `load` function. A `CFG` file path must be passed as an argument and, optionally, a `DAT` file path too (if the file name is not equal of the CFG file).

```python
import matplotlib.pyplot as plt
import comtrade

rec = comtrade.load("sample_files/sample_ascii.cfg", "sample_files/sample_ascii.dat")
print("Trigger time = {}s".format(rec.trigger_time))

plt.figure()
plt.plot(rec.time, rec.analog[0])
plt.plot(rec.time, rec.analog[1])
plt.legend([rec.analog_channel_ids[0], rec.analog_channel_ids[1]])
plt.show()
```

It will read the contents of additional header (`*.hdr`) and information (`*.inf`) files. 
Their contents are available through `Comtrade.hdr` and `Comtrade.inf` properties.


### CFF files (2013 revision)

```python
import matplotlib.pyplot as plt
import comtrade

rec = comtrade.load("sample_files/sample_ascii.cff")
print("Trigger time = {}s".format(rec.trigger_time))

plt.figure()
plt.plot(rec.time, rec.analog[0])
plt.plot(rec.time, rec.analog[1])
plt.legend([rec.analog_channel_ids[0], rec.analog_channel_ids[1]])
plt.show()
```

The module function `load` must be called with the `CFF` file path specified.

`Comtrade.analog` and `Comtrade.status` lists stores analog and status channel sample lists respectively. These can be accessed through zero-based indexes, i.e., `Comtrade.analog[0]`. The list `Comtrade.time` stores each sample time in seconds.

Analog channels may have a time skew (in microseconds) from the start of the sample period, which is not included in `Comtrade.time`. The list `Comtrade.analog_time` stores the time values of each analog channel, with its skew, in seconds, i.e., `Comtrade.analog_time[0]` for `Comtrade.analog[0]`.

`Comtrade.analog` values are in the units recorded in the file, which may be primary (power system)
or secondary (VT and CT outputs) values, as indicated by each analog channel's `pors` field.
`Comtrade.analog_primary` and `Comtrade.analog_secondary` lists store the analog values converted
to primary or secondary units, respectively, using each channel's `primary` and `secondary` ratio
information. Channels with invalid ratio information are not converted (with a warning).

More information can be accessed through `Comtrade.cfg` object, which stores data such as detailed channel information.

Data of additional sections, such as HDR and INF, can be accessed through `hdr` and `inf` properties, respectively.


### Data frames

The module supports the use of `pandas.DataFrame` as a data structure. Use the conveninent function `load_as_dataframe` or call
`Comtrade.to_dataframe()` function after loading the data.

```python
import comtrade
df = comtrade.load_as_dataframe("sample_files/sample_ascii.cfg")
print(df.head())

# Or, alternatively
rec = comtrade.load("sample_files/sample_ascii.cfg")
df = rec.to_dataframe()
print(df.head())
```


### Writing COMTRADE files

`Comtrade.save()` writes the CFG and DAT files (plus HDR and INF files, if there is HDR or INF
data), or a single CFF file if the path has the `.cff` extension. Choose the DAT file format with
`ft` (`"ASCII"`, `"BINARY"`, `"BINARY32"` or `"FLOAT32"`) and the revision with `rev_year`
(`"1999"`, `"2001"` or `"2013"`). Both default to the loaded file's ones.

```python
import comtrade
rec = comtrade.load("sample_files/sample_ascii.cfg", start_time=0.0, end_time=0.1)
rec.save("excerpt.cfg", ft="BINARY")  # excerpt.cfg and excerpt.dat
rec.save("excerpt.cff", ft="FLOAT32", rev_year="2013")
```

`comtrade.from_dataframe()` creates a recording from a `pandas.DataFrame`, with one channel per
column. The index holds the time values: seconds, a `DatetimeIndex` or a `TimedeltaIndex`
(or use `time_column` or `sample_rate`). Boolean columns, and integer columns with only 0 and 1
values, are status channels (or set `status_columns`).

```python
import comtrade
rec = comtrade.from_dataframe(
    df,
    station_name="SUBSTATION",
    rec_dev_id="RELAY 1",
    frequency=60,
    start_timestamp="2024-03-05 10:00:00",  # default: the first DatetimeIndex value
    trigger_time=0.1,  # or trigger_timestamp
    channels={"IA": {"uu": "A", "ph": "A", "primary": 600, "secondary": 5, "pors": "P"},
              "TRIP": {"y": 0}},
)
rec.save("record.cfg", ft="FLOAT32")
```

For the integer formats (ASCII, BINARY and BINARY32), each analog channel's `a` and `b` fields
are computed to use the whole format range, so values are rounded to `(max - min) / 65534` in
BINARY files, for instance. FLOAT32 files keep the values as they are. Files loaded and saved in
the same format keep their `a` and `b` fields. Missing values (NaN) are written as the format's
missing data marker. Uniformly sampled data are saved with their sample rate. Other data are
saved with timestamps only (`nrates=0`).


## Features

This module implements some of the functionality described in each of the Standard revisions. The tables below lists some features and file formats and which revision supports it. It also shows whether this module support the feature or the format.

Feel free to pull requests implementing one of these unsupported features or fixing bugs.

| Formats                                               | 1991 | 1999  | 2001 | 2013 | Module Support  |
|:------------------------------------------------------|:----:|:-----:|:----:|:----:|:---------------:|
| CFG file format                                       | x    | x     | x    | x    | x               |
| DAT file format                                       | x    | x     | x    | x    | x               |
| HDR file format                                       | x    | x     | x    | x    | text (1)        |
| INF file format                                       |      | x     | x    | x    | x (2)           |
| CFF file format                                       |      |       |      | x    | x               |
| ASCII data file format                                | x    | x     | x    | x    | x               |
| Binary data file format                               | x    | x     | x    | x    | x               |
| Binary32 data file format                             |      |       |      | x    | x               |
| Float32 data file format                              |      |       |      | x    | x               |
| Writing files (CFG, DAT, HDR, INF and CFF)            |      | x     | x    | x    | x               |
| Schema for phasor data                                |      |       |      | x    | no              |

(1) HDR files are free text, available as a string in `Comtrade.hdr`.
(2) INF files are available as a string in `Comtrade.inf` and can be parsed with
`Comtrade.inf_sections()`. See [INF files](#inf-files).


| Features                                              | 1991 | 1999 | 2001 | 2013 | Module Support  |
|:------------------------------------------------------|:----:|:----:|------|:----:|:---------------:|
| COMTRADE standard revision                            |      |  x   | x    | x    | x               |
| Timestamp multiplication factor                       |      |  x   | x    | x    | x               |
| Time code and local code                              |      |      |      | x    | x               |
| Time quality of the samples                           |      |      |      | x    | x               |
| Analog channel time skew                              |      |  x   | x    | x    | x               |
| Analog channel primary and secondary VT or CT ratio   |      |  x   | x    | x    | x               |
| Status channel phase and monitored circuit            |      |  x   | x    | x    | x               |
| Multiple sample rates                                 | x    |  x   | x    | x    | x               |
| Nanoseconds scale                                     |      |      | x    | x    | x               |


### Nanoseconds timestamps

Python's `datetime` objects don't support nanoseconds, so `start_timestamp` and `trigger_timestamp`
are truncated to microseconds (with a warning) when the CFG file uses a nanoseconds time base.
`start_timestamp_ns` and `trigger_timestamp_ns` hold the full resolution timestamps as the integer
number of nanoseconds since `1970-01-01 00:00:00` (in the time zone of the file timestamps), which
can be converted to `numpy` or `pandas` types. `trigger_time` uses them.

```python
import numpy as np
import pandas as pd
np.datetime64(rec.trigger_timestamp_ns, "ns")
pd.Timestamp(rec.trigger_timestamp_ns)
```


### Additional settings and features

#### Numpy arrays as data structures

The use of `numpy.array` as a data structure to hold time, analog and status data can be enforced
in `Comtrade` object constructor:

```python
obj = Comtrade(use_numpy_arrays=True)
```

It may improve performance for computations after loading data. It also speeds up loading binary
DAT files (`BINARY`, `BINARY32` and `FLOAT32` formats), which are converted with vectorized numpy
operations.


#### Loading a time window

Large records can be partially loaded, with only the samples within a time window, in seconds,
in the same scale of `Comtrade.time` (`start_time` and `end_time` limits are inclusive and
both are optional):

```python
import comtrade
rec = comtrade.load("my_record.cfg", start_time=0.1, end_time=0.3)
rec.time[0]          # 0.1 (or the first sample after it)
rec.total_samples    # number of samples within the window
```

`Comtrade.time` values keep their scale, i.e., the first sample of the window is not at zero.
Binary DAT files are memory mapped and the window is found with a binary search, so only the
window's rows are read. ASCII DAT files are read up to the window end. Samples are expected
to be in time order.


#### Lazy loading of binary files

With `lazy=True`, binary DAT files (`BINARY`, `BINARY32` and `FLOAT32` formats, including CFF
files) are kept memory mapped and the values of each channel are decoded when first accessed.
This saves time and memory when only some channels of a record with many channels are used.
Time values are loaded right away. ASCII DAT files are loaded completely, as usual.

```python
import comtrade
with comtrade.load("my_record.cfg", lazy=True) as rec:
    ia = rec.analog[0]   # decoded here
    trip = rec.status[3]
```

`Comtrade.analog` and `Comtrade.status` are then sequences (not lists) of channel values. The DAT
file stays open until `Comtrade.close()` is called, the `with` block ends, or another record is
loaded into the object. Channels not accessed before closing can't be read anymore. It can be
combined with `start_time` and `end_time`.


#### Replace missing data with `float('nan')`

Missing analog values are replaced with `float('nan')`. The value used to represent missing data varies with the 
Comtrade dat format and revision year. These are listed in the table next.

|  revision  |  format  | Missing Data Value            |
|:----------:|:--------:|:------------------------------|
|    1991    |  ascii   | `""` (empty string)           |
| 1999, 2013 |  ascii   | `99999`                       |
|    1991    |  binary  | `0xFFFF`                      |
| 1999, 2013 |  binary  | `0x8000` or `-32768`          |
|    2013    | binary32 | `0x80000000` or `-2147483648` |
|    2013    | float32  | minimum negative float value (`0xFF7FFFFF`) |


#### Time code, local code and time quality (2013 revision)

The 2013 revision CFG files may describe the time zone of the timestamps
(`time_code`), the time zone of the recording location (`local_code`), the
quality of the recording device clock (`tmq_code`) and leap second information
(`leapsec`). These are available through the `Comtrade.cfg` object:

```python
import comtrade
rec = comtrade.load("sample_files/sample_ascii.cfg")
rec.cfg.time_code      # "-5h30", as written in the file ("" if absent)
rec.cfg.time_offset    # datetime.timedelta(hours=-5, minutes=-30) (None if unknown)
rec.cfg.local_code     # "-5h30"
rec.cfg.local_offset   # datetime.timedelta(hours=-5, minutes=-30)
rec.cfg.tmq_code       # 11 (0xB)
rec.cfg.leap_second    # 3
```

`Comtrade.start_timestamp` and `Comtrade.trigger_timestamp` are naive `datetime` objects,
as written in the file. When the time code is known, `Comtrade.start_timestamp_utc` and
`Comtrade.trigger_timestamp_utc` return them as timezone-aware `datetime` objects in UTC,
which is useful to align records from different devices. Otherwise, they return `None`.

The time quality code (IEEE C37.118) is the maximum clock error of the recording device:

| `tmq_code` | Clock error                          |
|:----------:|:-------------------------------------|
| 0          | clock locked to an UTC traceable source |
| 1 to 11    | within 10^(n - 10) s: from 1 ns (1) to 10 s (11, `0xB`) |
| 12 to 14   | reserved                             |
| 15 (`0xF`) | clock failure, time not reliable     |

The `leap_second` values are: 0 (no leap second adjustment), 1 (leap second added),
2 (leap second subtracted), and 3 (the clock source cannot provide leap second information).


#### INF files

INF files use an INI-like format with public sections defined by the standard (such as
`[Public Record_Information]` and `[Public Analog_Channel_#1]`) and vendor-specific private
sections. `Comtrade.inf_sections()` parses them into a
[`configparser.ConfigParser`](https://docs.python.org/3/library/configparser.html) object,
keeping the case of section and key names (it returns `None` if there's no INF data):

```python
import comtrade
rec = comtrade.load("my_record.cfg")  # also reads my_record.inf, if it exists
inf = rec.inf_sections()
if inf is not None:
    for section in inf.sections():
        print(section, dict(inf[section]))
    print(inf["Public Record_Information"].get("Source"))
```

Values are strings. Duplicate sections and keys are allowed (the last value prevails).


#### File encodings

Specify the `encoding` as a keyword argument on all load methods as you'd specify for common file loading:

```python
import comtrade
comtrade.load("sample_files/sample_ascii.cff", encoding="iso-8859-1")
```


## Documentation

https://github.com/dparrini/python-comtrade

## Support

Feel free to report any bugs you find. You are welcome to fork and submit pull requests.

## Development

From a clone of the GitHub repository, run the tests and the linter with [uv](https://docs.astral.sh/uv/):

```sh
uv run pytest
uv run --extra numpy pytest  # also runs the numpy array tests
uv run ruff check
```

Or, with pip 25.1 or newer:

```sh
python -m pip install -e . --group dev
python -m pytest
```

### Releasing

1. Update `__version__` in `comtrade.py` and push the commit to `master`.
2. Publish a GitHub release tagged with that same version, e.g. `gh release create 0.1.3 --generate-notes`.

The `Release` workflow then runs CI and uploads the sdist and wheel to PyPI using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so no API token is needed.

## License

The module is available at [GitHub](https://github.com/dparrini/python-comtrade) under the MIT license.

