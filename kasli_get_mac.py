import logging

from kasli import Kasli
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
        # bus.reset()
        ee = EEPROM(bus)
        try:
            bus.enable("LOC0")
            print(ee.fmt_eui48())
        finally:
            bus.enable()
