import logging
import json
import datetime
from collections import OrderedDict
import socket
# OrderedDict = dict

from sinara import Sinara

logger = logging.getLogger(__name__)


__vendor__ = "QUARTIQ"

today = datetime.date.today().isoformat()


def get_kasli(description):
    target = description["target"].capitalize()
    v = Sinara.parse_hw_rev(description["hw_rev"])
    port = 0
    if "eui48" in description:
        eui48 = Sinara.parse_eui48(description["eui48"][port])
    else:
        eui48 = Sinara._defaults.eui48
    ee = [Sinara(
        name=target,
        board=Sinara.boards.index(target),
        major=v[0],
        minor=v[1],
        variant=description.get("hw_variant", 0),
        port=port,
        eui48=eui48,
        vendor=Sinara.vendors.index(description["vendor"]))]
    return ee


def get_eem(description):
    v = Sinara.parse_hw_rev(description["hw_rev"])
    name = description.get("board", description["type"].capitalize())
    if "variant" in description:
        variant = Sinara.variants.get(name, [None]).index(
            description["variant"])
    else:
        variant = 0
    if "eui48" in description:
        eui48 = [Sinara.parse_eui48(_) for _ in description["eui48"]]
    else:
        eui48 = [Sinara._defaults.eui48]*len(description["ports"])
    return [Sinara(
        name=name,
        board=Sinara.boards.index(name),
        major=v[0],
        minor=v[1],
        variant=variant,
        port=port,
        eui48=eui48[port],
        vendor=Sinara.vendors.index(__vendor__))
        for port in range(len(description["ports"]))]


def get_sinara_label(s):
    # assert s.vendor_fmt == __vendor__
    return """
^XA
^LH20,10^CFA
^FO0,10^FB140,4^FD{s.name_fmt}\&{s.description}\&{s.eui48_fmt}^FS
^FO0,55^FB140,3^FDQUARTIQ GmbH\&Rudower Chaussee 29\&12489 Berlin, Germany^FS
^FO0,90^FB220,2^FD{s.url}\&{s.license} - {date}^FS
^FO140,0^BQN,2,2^FDQA,https://qr.quartiq.de/sinara/{s.eui48_fmt}^FS
^XZ""".format(s=s, date=today)


def flash(description, ss, ft_serial=None):
    ss_new = []
    url = "ftdi://ftdi:4232h{}/2".format(
            ":" + ft_serial if ft_serial is not None else "")

    from kasli import Kasli
    from chips import EEPROM, PCA9548

    with Kasli().configure(url) as bus:
        # bus.reset_switch()
        bus.reset()
        try:
            for i, s in enumerate(ss):
                ss_new.append([])
                for j, si in enumerate(s):
                    ee = EEPROM(bus)
                    if i == 0:
                        port = "LOC0"
                        if si.hw_rev in ["v2.0",] or si.board_fmt in ["Kasli_soc"]:
                            ee = EEPROM(bus, addr=0x57)  # Kasli v2 and Kasli-SoC have this address
                    else:
                        port = "EEM{:d}".format(
                            description["peripherals"][i - 1]["ports"][j])
                        if description["peripherals"][i - 1]["type"] in "banker humpback".split():
                            continue
                            PCA9548(bus, addr=0x72).set(0b0)  # no eeprom
                    logger.info("%s", port)
                    bus.enable(port)  # TODO: Banker, Humpback switch
                    eui48 = ee.eui48()
                    if si.eui48 not in (eui48, si._defaults.eui48):
                        logger.warning("eui48 mismatch, %s->%s", si.eui48, eui48)
                    new = si._replace(eui48=eui48)
                    old = None
                    try:
                        old = Sinara.unpack(ee.dump())
                        logger.debug("old data: valid data %s", old)
                        # don't touch data fields
                        new = new._replace(
                            project_data=old.project_data,
                            board_data=old.board_data,
                            user_data=old.user_data
                        )
                        # don't touch eeprom if valid other vendor
                        if old.vendor not in (0x00, 0xff, new.vendor):
                            logger.info("old data: existing vendor data, skipping update")
                            new = old
                        if new != old:
                            old_dict = old._asdict()
                            new_dict = new._asdict()
                            logger.info("change data: %s", ", ".join(
                                "{}: {}->{}".format(
                                    k, old_dict[k], new_dict[k])
                                for k in old._fields
                                if old_dict[k] != new_dict[k]))
                    except:
                        logger.info("old data: invalid", exc_info=True)
                    if new == old:
                        logger.info("new data: unchanged, skipping update")
                    else:
                        logger.info("writing %s", new)
                        ee.write(0, new.pack()[:128])
                        new_readback = ee.dump()
                        try:
                            Sinara.unpack(new_readback)
                            logger.debug("data readback valid")
                        except:
                            logger.error("data readback invalid %r",
                                         new_readback, exc_info=True)
                    open("data/{}.bin".format(new.eui48_fmt), "wb"
                         ).write(new.pack())
                    ss_new[-1].append(new)

        finally:
            bus.enable()
    return ss_new


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser()
    p.add_argument("-p", "--printer")
    p.add_argument("-u", "--update", action="store_true")
    p.add_argument("-s", "--serial")
    p.add_argument("-k", "--kasli", type=int, default=1)
    p.add_argument("-v", "--verbose", default=0, action="count")
    p.add_argument("description")
    args = p.parse_args()

    logging.basicConfig(
        level=[logging.WARNING, logging.INFO, logging.DEBUG][args.verbose])

    with open(args.description) as f:
        description = json.load(f, object_pairs_hook=OrderedDict)
    assert description["vendor"] == __vendor__

    # build a list of Sinara eeprom contents from description
    ss = []
    if "target" in description:
        ss.append(get_kasli(description))
    ss.extend(get_eem(p) for p in description["peripherals"])

    if args.update:
        ss = flash(description, ss, args.serial)
        for i, s in enumerate(ss):
            e = [si.eui48_fmt for si in s]
            if any(ei != Sinara._defaults.eui48_fmt for ei in e):
                if i == 0:
                    description["eui48"] = e
                    description.move_to_end("peripherals")
                else:
                    description["peripherals"][i - 1]["eui48"] = e
    with open("meta/{}.json".format(ss[0][0].eui48_fmt), "w") as f:
        f.write(json.dumps(description, indent=4))

    labels = [get_sinara_label(s[0]) for s in ss]
    for i in range(args.kasli):
        labels.insert(0, labels[0])  # repeat first
    with open("labels/{}.zpl".format(ss[0][0].eui48_fmt), "w") as f:
        f.write("\n".join(labels))
    if args.printer:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.printer, 9100))
        sock.sendall("\n".join(labels).encode())
    else:
        from label import render_zpl
        for s in ss:
            open("labels/{}.png".format(s[0].eui48_fmt), "wb").write(
                    render_zpl(get_sinara_label(s[0])))
