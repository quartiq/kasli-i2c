import logging
import sys

from pyftdi.ftdi import Ftdi

from sinara import Sinara
from i2c import Kasli, EEPROM


logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    serial = int(sys.argv[1])
    logger.info("serial: %s", serial)

    ee_data = Sinara(
        name="Kasli",
        id=Sinara.ids.index("Kasli"),
        data_rev=0, major=1, minor=1, variant=0, port=0,
        vendor=Sinara.vendors.index("Technosystem"),
        serial=serial.to_bytes(8, "big"))

    ft_serial = "Kasli-v1.1-{}".format(serial)
    dev = Ftdi()
    dev.open_bitbang_from_url("ftdi://ftdi:4232h:{}/2".format(ft_serial))
    try:
        bus = Kasli(dev)
        with bus:
            #bus.reset()
            # slot = 3
            # bus.enable(bus.EEM[slot])
            bus.enable("LOC0")
            ee = EEPROM(bus)
            try:
                logger.info("valid data %s", Sinara.unpack(ee.dump()))
            except:
                logger.info("invalid data")  # , exc_info=True)
            eui48 = ee.eui48()
            print(ee.fmt_eui48())
            data = ee_data._replace(eui48=eui48)
            ee.write(0, data.pack()[:128])
            open("data/{}.bin".format(ee.fmt_eui48(eui48)), "wb").write(data.pack())
            try:
                logger.info("data readback valid %s", Sinara.unpack(ee.dump()))
            except:
                logger.error("data readback invalid", exc_info=True)
            bus.enable()
    finally:
        dev.close()
