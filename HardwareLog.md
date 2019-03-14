# Hardware Changelog

* When configuring the FTDI EEPROM, do not change the default product ID string,
  just add a serial number "Kasli-v1.0-2" according to the markings and
  stickers on the PCB and on the device.

## EEPROM layout

* 256 Byte (2 kb) EEPROM
* first page (128 Byte) writable
* second page read-only
* Fixed unique EUI-48 in the last 6 Bytes
* Big endian

Memory map: see [sinara.py](sinara.py)
