import struct
from collections import namedtuple


class Sinara(namedtuple("Sinara", "name id major minor variant "
    "port data_rev vendor serial "
    "vendor_data project_data user_data board_data eui48")):
    _struct = struct.Struct("> 6s 10s HBBBBBBI 4s 16s 16s 64s 122x 6s")
    assert _struct.size == 256
    _magic = "Sinara".encode()
    _defaults = (b"", 0, 0, 0, 0, 0, 0, 0, 0, 0, b"", b"", b"", b"", b"")
    _mandatory_size = 6 + 10 + 2 + 6

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
    ]
    vendors = [
        "invalid",
        "Technosystem",
        "Creotech",
        "invalid",
    ]

    def pack(self):
        return self._struct.pack(self._magic, *self)

    def pack_into(self, buffer, offset):
        return self._struct.pack_into(buffer, offset, self._magic, *self)

    @classmethod
    def unpack(cls, data):
        data = cls._struct.unpack(data)
        assert data[0] == cls._magic
        return cls(*data[1:])

    @classmethod
    def unpack_from(self, buffer, offset=0):
        data = cls._struct.unpack_from(buffer, offset)
        assert data[0] == cls._magic
        return cls(*data[1:])

Sinara.__new__.__defaults__ = Sinara._defaults


if __name__ == "__main__":
    s = Sinara(
            name="DIO-BNC".encode(),
            id=Sinara.ids.index("DIO-BNC"),
            major=1, minor=1, variant=0, port=0,
            vendor=Sinara.vendors.index("Technosystem"),
            serial=0)
    print(s)
    print(s.pack())
    Sinara.unpack(s.pack())
