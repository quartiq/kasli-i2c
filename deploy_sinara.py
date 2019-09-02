import logging
import sys
import json

from sinara import Sinara
from kasli import Kasli
from chips import EEPROM
from label import get_label

logger = logging.getLogger(__name__)


def parse_rev(v):
    v = v.strip().strip("v").split(".", 2)
    return int(v[0]), int(v[1]), v[2:]


def get_kasli(description, top):
    target = description["target"].capitalize()
    v = parse_rev(description["hw_rev"])
    ee = [Sinara(
        data_rev=Sinara.data_rev,
        name=target,
        board=Sinara.boards.index(target),
        major=v[0],
        minor=v[1],
        variant=description.get("variant", 0),
        port=0,
        vendor=Sinara.vendors.index(description["vendor"]))]
    if "backplane" in description:
        description = description["backplane"]
        name = "Kasli_BP"
        v = parse_rev(description["hw_rev"])
        ee.append(Sinara(
            data_rev=Sinara.data_rev,
            name=name,
            board=Sinara.boards.index(name),
            major=v[0],
            minor=v[1],
            variant=description.get("variant", 0),
            port=0,
            vendor=Sinara.vendors.index(top["vendor"])))
    return ee


def get_eem(description, top):
    v = parse_rev(description["hw_rev"])
    name = description.get("board", description["type"].capitalize())
    variant = Sinara.board_variants.get(name, [None]).index(
        description.get("variant"))
    return [Sinara(
        data_rev=Sinara.data_rev,
        name=name,
        board=Sinara.boards.index(name),
        major=v[0],
        minor=v[1],
        variant=variant,
        port=port,
        vendor=Sinara.vendors.index(top["vendor"]))
        for port in range(len(description["ports"]))]


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser()
    p.add_argument("description")
    args = p.parse_args()

    description = json.load(open(args.description))
    ee = get_kasli(description, description)
    for p in description["peripherals"]:
        ee.extend(get_eem(p, description))
    print(ee)

    ft_serial = "Kasli-v1.1-{}".format(serial)
    url = "ftdi://ftdi:4232h:{}/2".format(ft_serial)
    with Kasli().configure(url) as bus:
        #bus.reset()
        # slot = 3
        # bus.enable(bus.EEM[slot])
        try:
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
            data = ee.dump()
            try:
                logger.info("data readback valid %s", Sinara.unpack(data))
            except:
                logger.error("data readback invalid %r", data, exc_info=True)
        finally:
            bus.enable()
