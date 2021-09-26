# Python Comtrade

__Python Comtrade__ is a module for Python 3 designed to read _Common Format for Transient Data Exchange_ (COMTRADE) files. These consists of oscillography data recorded during power system outages, control systems tests, validation and tests of field equipment, protective relaying logs, etc. The COMTRADE format is defined by IEEE Standards, summarized in the table below. Some equipment vendors put additional information in proprietary versions of it. This module aims IEEE definitions but may support those proprietary versions.


| Standard                               | Revision |
|:---------------------------------------|:--------:|
| IEEE C37.111(TM)-1991                  |  1991    |
| IEEE C37.111(TM)-1999                  |  1999    |
| IEEE C37.111(TM)-2013 / IEC 60255-24   |  2013    |


## Installation

```
pip install comtrade
```

Or just copy `comtrade.py` from this repository.


## How to Use

The examples below shows how to open both CFG and DAT files or the new CFF file to plot (using `pyplot`) analog channel oscillography.



### CFG and DAT files (all revisions)

Comtrade files separated in CFG and DAT formats can also be read with `Comtrade.load`. A `CFG` file path must be passed as an argument and, optionaly, a `DAT` file path too (if the file name is not equal of the CFG file).

```py
import matplotlib.pyplot as plt
from comtrade import Comtrade

rec = Comtrade()
rec.load("sample_files/sample_ascii.cfg", "sample_files/sample_ascii.dat")
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

```py
import matplotlib.pyplot as plt
from comtrade import Comtrade

rec = Comtrade()
rec.load("sample_files/sample_ascii.cff")
print("Trigger time = {}s".format(rec.trigger_time))

plt.figure()
plt.plot(rec.time, rec.analog[0])
plt.plot(rec.time, rec.analog[1])
plt.legend([rec.analog_channel_ids[0], rec.analog_channel_ids[1]])
plt.show()
```

A `Comtrade` class must be instantiated and the method `load` called with the `CFF` file path.

`Comtrade.analog` and `Comtrade.status` lists stores analog and status channel sample lists respectively. These can be accessed through zero-based indexes, i.e., `Comtrade.analog[0]`. The list `Comtrade.time` stores each sample time in seconds.

More information can be accessed through `Comtrade.cfg` object, which stores data such as detailed channel information.

Data of additional sections, such as HDR and INF, can be accessed through `hdr` and `inf` properties, respectively.


## Features

This module implements some of the functionality described in each of the Standard revisions. The tables below lists some features and file formats and which revision supports it. It also shows whether this module support the feature or the format.

Feel free to pull requests implementing one of these unsupported features or fixing bugs.

| Formats                                               | 1991 |  1999 | 2013 | Module Support  |
|:------------------------------------------------------|:----:|:-----:|:----:|:---------------:|
| CFG file format                                       | x    | x     | x    | x               |
| DAT file format                                       | x    | x     | x    | x               |
| HDR file format                                       | x    | x     | x    | no              |
| INF file format                                       |      | x     | x    | no              |
| CFF file format                                       |      |       | x    | x               |
| ASCII data file format                                | x    | x     | x    | x               |
| Binary data file format                               | x    | x     | x    | x               |
| Binary32 data file format                             |      |       | x    | x               |
| Float32 data file format                              |      |       | x    | x               |
| Schema for phasor data                                |      |       | x    | no              |


| Features                                              | 1991 |  1999 | 2013 | Module Support  |
|:------------------------------------------------------|:----:|:-----:|:----:|:---------------:|
| COMTRADE standard revision                            |      | x     | x    | x               |
| Timestamp multiplication factor                       |      | x     | x    | x               |
| Time code and local code                              |      |       | x    | x               |
| Time quality of the samples                           |      |       | x    | x               |
| Analog channel time skew                              |      | x     | x    | Partial         |
| Analog channel primary and secondary VT or CT ratio   |      | x     | x    | x               |
| Status channel phase and monitored circuit            |      | x     | x    | x               |
| Multiple sample rates                                 | x    | x     | x    | Partial         |
| Nanoseconds scale                                     |      |       | x    | x               |


### Unsupported features

* Nanoseconds time base within Python's `datetime` objects (such as `start_timestamp` and `trigger_timestamp` properties). It warns the user but doesn't use it, truncating the numbers.
* Use of multiple sample rates in time calculations for binary data.
* Null fields in ASCII data (blank columns).
* Missing data fields in binary data (`0xFFFF...`) are treated as any other value.


### Additional settings

#### Numpy arrays as data structures

The use of `numpy.array` as a data structure to hold time, analog and status data can be enforced
in `Comtrade` object constructor:

```python
obj = Comtrade(use_numpy_arrays=True)
```

It may improve performance for computations after loading data.


#### File encodings

Specify the `encoding` as a keyword argument on all load methods as you'd specify for common file loading:

```python
rec = Comtrade()
rec.load("sample_files/sample_ascii.cff", encoding="iso-8859-1")
```


## Documentation

https://github.com/dparrini/python-comtrade

## Support

Feel free to report any bugs you find. You are welcome to fork and submit pull requests.

## Development

To run tests, use Python's `unittest`. From a clone of the GitHub repository, run the command:

#### On Windows
```
python -m unittest tests\tests.py
```

#### On Linux:
```
python3 -m unittest ./tests/tests.py
```

## License

The module is available at [GitHub](https://github.com/dparrini/python-comtrade) under the MIT license.

