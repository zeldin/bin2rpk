bin2rpk
=======

This is a python script to convert TI-99/4A cartridges in "bin"
format into proper RPK files.

By default it will guess what kind of PCB is needed, but it is also
possible to manually specified a paged variant.

Note that this script is intended for homebrew software.
For officially released cartridges, use of
[zip2rpk](https://github.com/zeldin/zip2rpk)
instead is recommended.


Usage
=====

Convert a BIN to an RPK:

```
bin2rpk.py borzorkc_8.bin
```
