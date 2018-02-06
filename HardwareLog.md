# Hardware Changelog

* When configuring the FTDI EEPROM, do not change the default product ID string,
  just add a serial number "Kasli-v1.0-2" according to the markings and
  stickers on the PCB.

* MAC address generation for devices without EUI-48 EEPROM (42-53-69-30-57-00)
  * OUI:
    * 42: locally administered address (2), unicast (0), otherwise arbitrary
    * 53-69: 'Si' (nara)
  * NIC: zlib.crc32(FPGA DNA) & 0xffff
    * 30-57: zlib.crc32(bytes([0x00, 0x30, 0x9c, 0x40, 0x09,
      0x25, 0x88, 0x5c])) & 0xffff) == 0x3057
    * 00: interface

## EEPROM layout

* 256 Byte (2 kb) EEPROM
* first page (128 Byte) writable
* second page read-only
* Fixed unique EUI-48 in the last 6 Bytes
* Big endian

Memory map:

* 0x00+4: CRC32 of the remaining 256 - 4 Bytes (0x04-0xff)
* 0x04+2: magic, fixed: 0x391e (`zlib.crc32(b"ARTIQ/Sinara") >> 16`)
* 0x06+10: board, human readable: `DIO-BNC`
* 0x10+2: board ID:
  * 0x0000: invalid
  * 0x0001: VHDCI-Carrier
  * 0x0002: Sayma-RTM
  * 0x0003: Sayma-AMC
  * 0x0004: Metlino
  * 0x0005: Kasli
  * 0x0006: DIO-BNC
  * 0x0007: DIO-SMA
  * 0x0008: DIO-RJ45
  * 0x0009: Urukul
  * 0x000a: Zotino
  * 0x000b: Novogorny
  * 0x000c: Sampler
  * 0x000d: Grabber
  * 0x000e: Clocker
  * 0x000f: Booster
  * 0x0010: BaseMod
  * 0x0011: MixMod
  * 0x0012: Baikal
  * 0x0013: Sayma Clock Mezzanine
  * 0x0014: Stamper
  * 0x0015: Shuttler
  * 0x0016: Thermostat
  * 0x0017: Mirny
  * 0xff00-0xfffe: testing, locally administered
  * 0xffff: reserved/invalid
* 0x12+1: EE-PROM data revision: 0x00
* 0x13+1: board major: 0x01
  * 0xff: reserved/invalid
* 0x14+1: board minor: 0x02
  * 0xff: reserved/invalid
* 0x15+1: board specific variant: 0x00
  * 0x00: Urukul-AD9912
  * 0x01: Urukul-AD9910
  * 0xff: reserved/invalid
* 0x16+1: board specific port/section: 0x00
  * 0x00: EEM0 on Urukul/Sampler/DIO-RJ45
  * 0x01: EEM1 on Urukul/Sampler/DIO-RJ45
  * 0xff: reserved/invalid
* 0x17+1: manufacturer ID:
  * 0x00: unknown
  * 0x01: Technosystem
  * 0x02: Creotech
  * 0xf0-0xfe: locally administered
  * 0xff: reserved/invalid
* 0x18+4: manufacturer-specific unique Batch/Serial
* 0x1c+4: manufacturer reserved
* 0x20+16: project reserved
* 0x30+16: user reserved
* 0x40+64: board-specific data
* 0x80-0xfa: 0xff, read-only
* 0xfa+6: EUI-48, read-only

## Kasli

### '#2'

* Kasli v1.0
* #2 sticker
* Missing front panel barrel connector nut
* IC19 removed
* IC19 8-5: 1k
* IC19 9-4: shorted
* C49: removed, shorted
* EEM1 I2C SDA shorted to ground (~300R), presumably ESD
* R57: 300R
* DNA: 0x00689c400925885c
* MAC: 42-53-69-97-87-00

### '#8'

* Kasli v1.0
* #8 sticker
* IC19 removed
* IC19 8-5: 1k
* IC19 9-4: shorted
* C49: removed, shorted
* R57: 300R
* DNA: 0x00309c400925885c
* MAC: 42-53-69-30-57-00

## Urukul

### 54-10-ec-32-bc-d8/54-10-ec-33-10-56

* Urukul v1.0 AD9912
* ID from EEM0
* IC11, IC7: BIAS to P5V0 + bypass cap
* modify R118/R119 and R23/R80 - add 820R in parallel or replace
* L9: disconnected
* R47, R52: 50R
* R1A, R14A, R1B, R14B: shorted
* R117: removed

###

* Urukul v1.0 AD9910
* ID from EEM0
* IC11, IC7: BIAS to P5V0
* modify R118/R119 and R23/R80 - add 820R in parallel or replace
* L9: disconnected
* R1A, R14A, R1B, R14B: shorted
* R117: removed
