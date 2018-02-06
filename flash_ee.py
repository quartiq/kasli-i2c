import logging

from sinara import Sinara
from i2c import Kasli10, EEPROM

    
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    serial = "Kasli-v1.0-8"
    eem = 3
    ee_data = Sinara(
        name="DIO-BNC",
        id=Sinara.ids.index("DIO-BNC"),
        major=1, minor=1, variant=0, port=0,
        vendor=Sinara.vendors.index("Technosystem"),
        serial=0)

    bus = Kasli10()
    bus.configure("ftdi://ftdi:4232h:{}/3".format(serial))
    with bus:
        bus.reset()
        bus.enable(bus.EEM[eem])
        ee = EEPROM(bus)
        d = ee.dump()
        try:
            logger.warning("valid data %s", Sinara.unpack(d))
        except:
            logger.warning(ee.fmt_eui48())
            logger.warning("invalid data", exc_info=True)
        ee.write(0, ee_data._replace(eui48=ee.eui48()).pack()[:128])
        logger.warning(Sinara.unpack(ee.dump()))
