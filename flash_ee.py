import logging

from sinara import Sinara
from i2c import Kasli10, EEPROM

    
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    serial = "Kasli-v1.0-8"
    eem = 3
    ee_data = Sinara(
        name="DIO-BNC".encode(),
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
        logger.warning(ee.fmt_eui48())
        logger.warning(ee.dump())
        ee.write(0, ee_data.pack()[:ee_data._mandatory_size])
        logger.warning(ee.dump())
