import logging

from kasli import Kasli, I2CNACK
from chips import EEPROM

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser()
    p.add_argument("-s", "--serial")
    args = p.parse_args()

    url = "ftdi://ftdi:4232h{}/2".format(
            ":" + args.serial if args.serial is not None else "")
    with Kasli().configure(url) as bus:
        bus.reset()
        with bus.enabled("LOC0"):
            try:
                print(EEPROM(bus).fmt_eui48())
            except I2CNACK:
                print(EEPROM(bus, addr=0x57).fmt_eui48())  # v2
