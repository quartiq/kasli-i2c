from contextlib import contextmanager
import logging

from sinara import Sinara
from i2c_mpsse import I2C as I2C
from i2c_bitbang import I2C as I2CBB
import chips

logger = logging.getLogger(__name__)


class Kasli(I2C, chips.ScanI2C):
    ports = {
        "ROOT": [],
        "EEM0": [(0x70, 7)],
        "EEM1": [(0x70, 5)],
        "EEM2": [(0x70, 4)],
        "EEM3": [(0x70, 3)],
        "EEM4": [(0x70, 2)],
        "EEM5": [(0x70, 1)],
        "EEM6": [(0x70, 0)],
        "EEM7": [(0x70, 6)],
        "EEM8": [(0x71, 4)],
        "EEM9": [(0x71, 5)],
        "EEM10": [(0x71, 7)],
        "EEM11": [(0x71, 6)],
        "SFP0": [(0x71, 0)],
        "SFP1": [(0x71, 1)],
        "SFP2": [(0x71, 2)],
        "LOC0": [(0x71, 3)],
    }
    skip = []

    def enable(self, *ports):
        bits = {0x70: 0, 0x71: 0}
        for port in ports:
            assert port not in self.skip
            for addr, p in self.ports[port]:
                bits[addr] |= (1 << p)
        for addr in sorted(bits):
            self.write_single(addr, bits[addr])

    @contextmanager
    def enabled(self, *ports):
        self.enable(*ports)
        try:
            yield self
        finally:
            self.enable()

    def names(self, paths):
        rev = dict((v, k) for k, v in self.ports)
        return ", ".join(rev[path] for path in paths)

    def scan_devices(self):
        devs = [chips.SinaraEEPROM(self, addr=0x57),
                chips.LM75(self), chips.PCF8574(self, addr=0x3e),
                chips.Si5324(self), chips.SFF8472(self)]
        devs = {dev.addr: dev for dev in devs}

        for port in sorted(self.ports):
            if port in self.skip:
                continue
            self.enable(port)
            logger.info("%s: ...", port)
            for addr in self.scan():
                if addr in devs:
                    devs[addr].report()
                else:
                    logger.debug("ignoring addr %#02x", addr)

    def dump_eeproms(self, **kwargs):
        ee = chips.EEPROM(self, **kwargs)
        for port in sorted(self.ports):
            if port in self.skip:
                continue
            self.enable(port)
            if self.poll(ee.addr):
                eui48 = ee.fmt_eui48()
                logger.info("Port %s: found %s", port, eui48)
                open("data/{}.bin".format(eui48), "wb").write(ee.dump())


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("-s", "--serial", default="0")
    # port 2 for Kasli v1.1
    # port 3 for Kasli v1.0
    p.add_argument("-p", "--port", default=2, type=int)
    # EEM1 (port 5) SDA shorted on Kasli-v1.0-2
    p.add_argument("-k", "--skip", action="append", default=[])
    p.add_argument("-e", "--eem", default=None)
    p.add_argument("-v", "--verbose", default=0, action="count")

    p.add_argument("action", nargs="*")
    args = p.parse_args()
    if not args.action:
        args.action.append("scan")

    logging.basicConfig(
        level=[logging.WARNING, logging.INFO, logging.DEBUG][args.verbose])

    url = "ftdi://ftdi:4232h:{}/{}".format(args.serial, args.port)
    with Kasli().configure(url) as bus:
        bus.skip = args.skip
        bus.reset_switch()
        # bus.clear()
        try:
            for action in args.action:
                if action == "scan_tree":
                    t = list(bus.scan_tree())
                    logger.warning("%s", t)
                    logger.warning("%s", bus.make_graph(t))
                elif action == "scan":
                    bus.scan_devices()
                elif action == "dump_eeproms":
                    bus.dump_eeproms()
                elif action == "lm75":
                    bus.enable(args.eem)
                    lm75 = chips.LM75(bus)
                    lm75.report()
                elif action == "si5324":
                    bus.enable("LOC0")
                    si = chips.Si5324(bus)
                    s = chips.Si5324.FrequencySettings()
                    if True:
                        s.n31 = 4993  # 100 MHz CKIN1
                        s.n32 = 4565  # 114.285 MHz CKIN2 XTAL
                        s.n1_hs = 10
                        s.nc1_ls = 4
                        s.nc2_ls = 4
                        s.n2_hs = 10
                        s.n2_ls = 19972  # 125MHz CKOUT
                        s.bwsel = 4
                    else:
                        s.n31 = 65  # 125 MHz CKIN1
                        s.n32 = 52  # 100 MHz CKIN2 (not free run)
                        s.n1_hs = 10
                        s.nc1_ls = 4
                        s.nc2_ls = 4
                        s.n2_hs = 10
                        s.n2_ls = 260  # 125MHz CKOUT
                        s.bwsel = 10
                    si.setup(s)
                    logger.warning("flags %s %s %s", si.has_xtal(),
                                   si.has_clkin2(), si.locked())
                elif action == "sfp":
                    bus.enable(args.eem)
                    sfp0 = chips.SFF8472(bus)
                    sfp0.report()
                    # for i in 0x50, 0x51, 0x56:
                    #     sfp0.print_dump(bus.read_many(i, 0, 256))
                    # sfp0.watch(n=0)
                elif action == "ee":
                    bus.enable(args.eem)
                    ee = chips.EEPROM(bus)
                    logger.warning(ee.fmt_eui48())
                    logger.warning(ee.dump())
                    io = chips.PCF8574(bus, addr=0x3e)
                    # io.write(0xff)
                    # logger.warning(hex(io.read()))
                else:
                    raise ValueError("unknown action", action)
        finally:
            bus.enable()
