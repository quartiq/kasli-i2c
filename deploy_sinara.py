import logging
import sys
import json
import datetime

from sinara import Sinara
from kasli import Kasli
from chips import EEPROM
from label import render_zpl

logger = logging.getLogger(__name__)


__vendor__ = "QUARTIQ"

__vendor_description__ = "QUARTIQ GmbH", "Rudower Chaussee 29", "12489 Berlin, Germany"


def parse_rev(v):
    v = v.strip().strip("v").split(".", 2)
    return int(v[0]), int(v[1]), v[2:]


def get_kasli(description):
    target = description["target"].capitalize()
    v = parse_rev(description["hw_rev"])
    ee = [Sinara(
        name=target,
        board=Sinara.boards.index(target),
        major=v[0],
        minor=v[1],
        variant=description.get("hw_variant", 0),
        port=0,
        vendor=Sinara.vendors.index(description["vendor"]))]
    if "backplane" in description:
        description = description["backplane"]
        name = "Kasli_BP"
        v = parse_rev(description["hw_rev"])
        ee.append(Sinara(
            name=name,
            board=Sinara.boards.index(name),
            major=v[0],
            minor=v[1],
            variant=description.get("variant", 0),
            port=0,
            vendor=Sinara.vendors.index(__vendor__)))
    return ee


def get_eem(description):
    v = parse_rev(description["hw_rev"])
    name = description.get("board", description["type"].capitalize())
    if "variant" in description:
        variant = Sinara.variants.get(name, [None]).index(
            description["variant"])
    else:
        variant = 0
    return [Sinara(
        name=name,
        board=Sinara.boards.index(name),
        major=v[0],
        minor=v[1],
        variant=variant,
        port=port,
        vendor=Sinara.vendors.index(__vendor__))
        for port in range(len(description["ports"]))]


def get_label(s):
    return """
^XA
^LH20,10^CFA
^FO0,10^FB140,4^FD{s.name}{variant}/v{s.major:d}.{s.minor:d}\&{description}\&p{s.port}: {s.eui48_fmt}^FS
^FO0,55^FB140,3^FD{vendor}^FS
^FO0,90^FB220,2^FD{s.url}\&{license} - {date}^FS
^FO140,0^BQN,2,2^FDQA,{uri}^FS
^XZ""".format(
        s=s,
        variant="-{}".format(s.variants[s.name][s.variant]) if s.name in s.variants else "",
        description=s.descriptions[s.name],
        vendor="\\&".join(__vendor_description__),
        date=datetime.date.today().isoformat(),
        license=s.licenses.get(s.name, s.licenses[None]),
        uri="https://qr.quartiq.de/sinara/{}".format(s.eui48_fmt))


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser()
    p.add_argument("description")
    args = p.parse_args()

    description = json.load(open(args.description))
    assert description["vendor"] == __vendor__
    ee = get_kasli(description)
    for p in description["peripherals"]:
        # TODO: get eui48, flash
        ee.extend(get_eem(p))
    for s in ee:
        open("data/{}.bin".format(s.eui48_fmt), "wb").write(s.pack())
        z = get_label(s)
        open("labels/{}.zpl".format(s.eui48_fmt), "w").write(z)
        # open("labels/{}.png".format(s.eui48_fmt), "wb").write(render_zpl(z))
        print(z)


def x():
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
            data = ee.dump()
            try:
                logger.info("data readback valid %s", Sinara.unpack(data))
            except:
                logger.error("data readback invalid %r", data, exc_info=True)
        finally:
            bus.enable()
