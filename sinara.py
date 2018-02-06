import struct
import zlib
from collections import namedtuple


class Sinara(namedtuple("Sinara", (
        "name",          # 10s, name of the board, human redable, not used
        "id",            # H, board ID
        "data_rev",      # B, EEPROM data format revision
        "major",         # B, board major revision
        "minor",         # B, board minor revision
        "variant",       # B, board variant
        "port",          # B, board port
        "vendor",        # B, manufacturer/vendor
        "serial",        # I, manufacturer-assigned serial number
        "vendor_data",   # 4s, manufacturer data
        "project_data",  # 16s, project reserved
        "user_data",     # 16s, user reserved
        "board_data",    # 64s, board data
        "eui48",         # 6s, EUI-48
        ))):
    _defaults = ("Unknown", 0, 0, 0, 0, 0, 0, 0, 0, b"\x00"*4, b"\x00"*16,
            b"\x00"*16, b"\x00"*64, b"\x00"*6)
    _struct = struct.Struct(">I H 10s HBBBBB BI4s 16s 16s 64s 122s 6s")
    assert _struct.size == 256
    _magic = 0x391e
    _crc = zlib.crc32
    _pad = b"\xff" * 122

    ids = [
        "invalid",
        "VHDCI-Carrier",
        "Sayma-RTM",
        "Sayma-AMC",
        "Metlino",
        "Kasli",
        "DIO-BNC",
        "DIO-SMA",
        "DIO-RJ45",
        "Urukul",
        "Zotino",
        "Novogorny",
        "Sampler",
        "Grabber",
        "Clocker",
        "Booster",
        "BaseMod",
        "MixMod",
        "Baikal",
        "Sayma Clock Mezzanine",
        "Stamper",
        "Shuttler",
        "Thermostat",
        "Mirny",
        # ...
    ]
    vendors = [
        "invalid",
        "Technosystem",
        "Creotech",
        # ...
    ]

    def pack(self):
        data = self._struct.pack(
                0, self._magic, self[0].encode(), *self[1:-1],
                self._pad, self[-1])
        data = struct.pack(">I", self._crc(data[4:])) + data[4:]
        assert len(data) == self._struct.size
        return data

    @classmethod
    def unpack(cls, data, check=True):
        fields = list(cls._struct.unpack(data))
        if check:
            if fields[1] != cls._magic:
                raise ValueError("Invalid magic")
            if fields[-2] != cls._pad:
                raise ValueError("Unexpected read-only pad data")
            if fields[0] != cls._crc(data[4:]):
                raise ValueError("Invalid CRC")
        fields[2] = fields[2].strip(b"\x00").decode()
        return cls(*fields[2:-2], fields[-1])


Sinara.__new__.__defaults__ = Sinara._defaults


if __name__ == "__main__":
    s = Sinara(
            name="DIO-BNC",
            id=Sinara.ids.index("DIO-BNC"),
            data_rev=0, major=1, minor=1, variant=0, port=0,
            vendor=Sinara.vendors.index("Technosystem"),
            serial=0)
    print(s)
    print(s.pack())
    Sinara.unpack(s.pack())
