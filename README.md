# Python Comtrade

__Python Comtrade__ is a module for Python 3 designed to read _Common Format for Transient Data Exchange_ (COMTRADE) files. These consists of oscillography data recorded during power system outages, control systems tests, validation and tests of field equipment, protective relaying logs, etc. The COMTRADE format is defined by IEEE Standards, summarized in the table below. Some equipment vendors put additional information in proprietary versions of it. This module aims IEEE definitions but may support those proprietary versions.


| Standard                            | Revision |
|:------------------------------------|:--------:|
| IEEE C37.111™-1991                  |  1991    |
| IEEE C37.111™-1999                  |  1999    |
| IEEE C37.111™-2013 / IEC 60255-24   |  2013    |


## How to Use

The examples below shows how to open a CFF file or both CFG and DAT files to plot (using `pyplot`) analog channel oscillography.

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

`Comtrade.analog` and `Comtrade.digital` lists stores analog and digital channel sample lists respectively. These can be accessed through zero-based indexes, i.e., `Comtrade.analog[0]`. The list `Comtrade.time` stores each sample time in seconds.

More information can be accessed through `Comtrade.cfg` object, which stores data such as detailed channel information.

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

## Features

This module implements some of the functionality described in each of the Standard revisions. The tables below lists some features and file formats and which revision supports it. It also shows whether this module support the feature or the format.

Feel free to pull requests implementing one of these unsupported features or fixing bugs.

| Formats                                               | 1991 |  1999 | 2013 | Module Support  |
|:------------------------------------------------------|:----:|:-----:|:----:|:---------------:|
| CFG file format                                       | x    | x     | x    | ✔              |
| DAT file format                                       | x    | x     | x    | ✔              |
| HDR file format                                       | x    | x     | x    | ❌              |
| INF file format                                       |      | x     | x    | ❌              |
| CFF file format                                       |      |       | x    | ✔              |
| ASCII data file format                                | x    | x     | x    | ✔              |
| Binary data file format                               | x    | x     | x    | ✔              |
| Binary32 data file format                             |      |       | x    | ✔              |
| Float32 data file format                              |      |       | x    | ✔              |
| Schema for phasor data                                |      |       | x    | ❌              |


| Features                                              | 1991 |  1999 | 2013 | Module Support  |
|:------------------------------------------------------|:----:|:-----:|:----:|:---------------:|
| COMTRADE standard revision                            |      | x     | x    | ✔              |
| Timestamp multiplication factor                       |      | x     | x    | ✔              |
| Time code and local code                              |      |       | x    | ✔              |
| Time quality of the samples                           |      |       | x    | ✔              |
| Analog channel time skew                              |      | x     | x    | Partial         |
| Analog channel primary and secondary VT or CT ratio   |      | x     | x    | ✔              |
| Digital channel phase and monitored circuit           |      | x     | x    | ✔              |
| Multiple sample rates                                 | x    | x     | x    | Partial         |
| Nanoseconds scale                                     |      |       | x    | ✔              |


### Unsupported features

* Nanoseconds time base within Python's `datetime` objects (such as `start_timestamp` and `trigger_timestamp` properties). It warns the user but doesn't use it, truncating the numbers.
* Use of multiple sample rates in time calculations for binary data.
* Null fields in ASCII data (blank columns).
* Missing data fields in binary data (`0xFFFF...`) are treated as any other value.


## Documentation

https://github.com/dparrini/python-comtrade

## Support

Feel free to report any bugs you find. You are welcome to fork and submit pull requests.

## License

The module is available at [GitHub](https://github.com/dparrini/python-comtrade) under the MIT license.

