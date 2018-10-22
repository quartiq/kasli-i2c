from contextlib import contextmanager
import logging
import time
import struct

from pyftdi.ftdi import Ftdi
from sinara import Sinara


logger = logging.getLogger(__name__)


class I2C:
    SCL = 1 << 0
    SDAO = 1 << 1
    SDAI = 1 << 2
    EN = 1 << 4
    RESET_B = 1 << 5
    max_clock_stretch = 100

    def __init__(self, dev):
        self.dev = dev
        self._time = 0
        self._direction = 0

    def tick(self):
        self._time += 1

    def reset_switch(self):
        self.write(self.EN)
        self.tick()
        self.write(self.EN | self.RESET_B)
        self.tick()
        time.sleep(.01)

    def set_direction(self, direction):
        self._direction = direction
        self.dev.set_bitmode(direction, Ftdi.BITMODE_BITBANG)

    def write(self, data):
        self.dev.write_data(bytes([data]))

    def read(self):
        return self.dev.read_pins()

    def scl_oe(self, oe):
        d = (self._direction & ~self.SCL)
        if oe:
            d |= self.SCL
        self.set_direction(d)

    def sda_oe(self, oe):
        d = self._direction & ~self.SDAO
        if oe:
            d |= self.SDAO
        self.set_direction(d)

    def scl_i(self):
        return bool(self.read() & self.SCL)

    def sda_i(self):
        return bool(self.read() & self.SDAI)

    def clock_stretch(self):
        for i in range(self.max_clock_stretch):
            r = self.read()
            if r & self.SCL:
                return bool(r & self.SDAI)
        raise ValueError("SCL low exceeded clock stretch limit")

    def acquire(self):
        self.write(self.EN | self.RESET_B)  # RESET_B, EN, !SCL, !SDA
        self.set_direction(self.EN | self.RESET_B)  # enable USB-I2C
        self.tick()
        # self.reset_switch()
        time.sleep(.1)
        i = self.read()
        if not i & self.EN:
            raise ValueError("EN low despite enable")
        if not i & self.SCL:
            raise ValueError("SCL stuck low")
        if not i & self.SDAI:
            raise ValueError("SDAI stuck low")
        if not i & self.SDAO:
            raise ValueError("SDAO stuck low")

    def release(self):
        # self.reset_switch()
        self.set_direction(self.EN | self.RESET_B)
        self.write(self.RESET_B)
        self.tick()
        i = self.read()
        if i & self.EN:
            raise ValueError("EN high despite disable")
        if not i & self.SCL:
            raise ValueError("SCL low despite disable")
        if not i & self.SDAI:
            raise ValueError("SDAI low despite disable")
        if not i & self.SDAO:
            raise ValueError("SDAO low despite disable")

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def clear(self):
        self.tick()
        self.scl_oe(False)
        self.tick()
        self.sda_oe(False)
        self.tick()
        for i in range(9):
            if self.clock_stretch():
                break
            self.scl_oe(True)
            self.tick()
            self.scl_oe(False)
            self.tick()

    def start(self):
        assert self.scl_i()
        if not self.sda_i():
            raise ValueError("Arbitration lost")
        self.sda_oe(True)
        self.tick()
        self.scl_oe(True)
        # SCL low, SDA low

    def stop(self):
        # SCL low, SDA low
        self.tick()
        self.scl_oe(False)
        self.tick()
        self.clock_stretch()
        self.sda_oe(False)
        self.tick()
        if not self.sda_i():
            raise ValueError("Arbitration lost")

    def restart(self):
        # SCL low, SDA low
        self.sda_oe(False)
        self.tick()
        self.scl_oe(False)
        self.tick()
        assert self.clock_stretch()
        self.start()

    def write_data(self, data):
        for i in range(8):
            bit = bool(data & (1 << 7 - i))
            self.sda_oe(not bit)
            self.tick()
            self.scl_oe(False)
            self.tick()
            if self.clock_stretch() != bit:
                raise ValueError("Arbitration lost")
            self.scl_oe(True)
        # check ACK
        self.sda_oe(False)
        self.tick()
        self.scl_oe(False)
        self.tick()
        ack = not self.clock_stretch()
        self.scl_oe(True)
        self.sda_oe(True)
        # SCL low, SDA low
        return ack

    def read_data(self, ack=True):
        self.sda_oe(False)
        data = 0
        for i in range(8):
            self.tick()
            self.scl_oe(False)
            self.tick()
            if self.clock_stretch():
                data |= 1 << 7 - i
            self.scl_oe(True)
        # send ACK
        self.sda_oe(ack)
        self.tick()
        self.scl_oe(False)
        self.tick()
        if self.clock_stretch() == ack:
            raise ValueError("Arbitration lost")
        self.scl_oe(True)
        self.sda_oe(True)
        # SCL low, SDA low
        return data

    @contextmanager
    def xfer(self):
        self.start()
        yield
        self.stop()

    def write_single(self, addr, data, ack=True):
        with self.xfer():
            if not self.write_data(addr << 1):
                raise I2CNACK("Address Write NACK", addr)
            if not self.write_data(data) and ack:
                raise I2CNACK("Data NACK", addr, data)

    def read_single(self, addr):
        with self.xfer():
            if not self.write_data((addr << 1) | 1):
                raise I2CNACK("Address Read NACK", addr)
            return self.read_data(ack=False)

    def write_many(self, addr, reg, data, ack=True):
        with self.xfer():
            if not self.write_data(addr << 1):
                raise I2CNACK("Address Write NACK", addr)
            if not self.write_data(reg):
                raise I2CNACK("Reg NACK", reg)
            for i, byte in enumerate(data):
                if not self.write_data(byte) and (ack or i < len(data) - 1):
                    raise I2CNACK("Data NACK", data)

    def read_many(self, addr, reg, length=1):
        with self.xfer():
            if not self.write_data(addr << 1):
                raise I2CNACK("Address Write NACK", addr)
            if not self.write_data(reg):
                raise I2CNACK("Reg NACK", reg)
            self.restart()
            if not self.write_data((addr << 1) | 1):
                raise I2CNACK("Address Read NACK", addr)
            return bytes(self.read_data(ack=i < length - 1)
                         for i in range(length))

    def read_stream(self, addr, length=1):
        with self.xfer():
            if not self.write_data((addr << 1) | 1):
                raise I2CNACK("Address Read NACK", addr)
            return bytes(self.read_data(ack=i < length - 1)
                         for i in range(length))

    def poll(self, addr):
        with self.xfer():
            return self.write_data(addr << 1)

    def scan(self, addrs=None):
        for addr in addrs or range(1 << 7):
            if self.poll(addr):
                yield addr

    def scan_tree(self, addr_mask=(0x70, 0x78), addrs=None, skip=[]):
        found = [addr for addr in self.scan(addrs) if addr not in skip]
        for addr in found:
            if (addr ^ addr_mask[0]) & addr_mask[1]:
                yield [], addr
                continue
            for port in range(8):
                self.write_single(addr, 1 << port)
                for path, sub in self.scan_tree(
                    addr_mask, addrs, skip + found):
                    yield [(addr, port)] + path, sub
            self.write_single(addr, 0)

    def make_graph(self, it):
        root = {}
        for path, addr in it:
            scope = root
            for sw, port in path:
                if sw not in scope:
                    scope[sw] = [{} for _ in range(8)]
                scope = scope[sw][port]
            scope[addr] = None
        return root

    def test_speed(self):
        t = self._time
        t0 = time.monotonic()
        for _ in self.scan_tree():
            pass
        clock = (self._time - t)/2/(time.monotonic() - t0)
        logger.info("I2C speed ~%s Hz", clock)
        return clock


class I2CNACK(Exception):
    pass


class PCA9548:
    def __init__(self, bus, addr=0x70):
        self.bus = bus
        self.addr = addr

    def set(self, ports):
        self.bus.write_single(self.addr, ports)

    def get(self):
        return self.bus.read_single(self.addr)

    def report(self):
        logger.info("PCA9548(switch): %#04x", self.get())


class Si5324:
    class FrequencySettings:
        n31 = None
        n32 = None
        n1_hs = None
        nc1_ls = None
        nc2_ls = None
        n2_hs = None
        n2_ls = None
        bwsel = None

        def map(self, settings):
            if settings.nc1_ls != 0 and (settings.nc1_ls % 2) == 1:
                raise ValueError("NC1_LS must be 0 or even")
            if settings.nc1_ls > (1 << 20):
                raise ValueError("NC1_LS is too high")
            if settings.nc2_ls != 0 and (settings.nc2_ls % 2) == 1:
                raise ValueError("NC2_LS must be 0 or even")
            if settings.nc2_ls > (1 << 20):
                raise ValueError("NC2_LS is too high")
            if (settings.n2_ls % 2) == 1:
                raise ValueError("N2_LS must be even")
            if settings.n2_ls > (1 << 20):
                raise ValueError("N2_LS is too high")
            if settings.n31 > (1 << 19):
                raise ValueError("N31 is too high")
            if settings.n32 > (1 << 19):
                raise ValueError("N32 is too high")
            if not 4 <= settings.n1_hs <= 11:
                raise ValueError("N1_HS is invalid")
            if not 4 <= settings.n2_hs <= 11:
                raise ValueError("N2_HS is invalid")
            self.n1_hs = settings.n1_hs - 4
            self.nc1_ls = settings.nc1_ls - 1
            self.nc2_ls = settings.nc2_ls - 1
            self.n2_hs = settings.n2_hs - 4
            self.n2_ls = settings.n2_ls - 1
            self.n31 = settings.n31 - 1
            self.n32 = settings.n32 - 1
            self.bwsel = settings.bwsel
            return self

    def __init__(self, bus, addr=0x68):
        self.bus = bus
        self.addr = addr

    def write(self, addr, data):
        self.bus.write_many(self.addr, addr, [data])

    def read(self, addr):
        return self.bus.read_many(self.addr, addr, 1)[0]

    def ident(self):
        return self.bus.read_many(self.addr, 134, 2)

    def has_xtal(self):
        return self.read(129) & 0x01 == 0  # LOSX_INT=0

    def has_clkin1(self):
        return self.read(129) & 0x02 == 0  # LOS1_INT=0

    def has_clkin2(self):
        return self.read(129) & 0x04 == 0  # LOS2_INT=0

    def locked(self):
        return self.read(130) & 0x01 == 0  # LOL_INT=0

    def wait_lock(self, timeout=20):
        t = time.monotonic()
        while not self.locked():
            if time.monotonic() - t > timeout:
                raise ValueError("lock timeout")
        logger.info("locking took %g s", time.monotonic() - t)

    def select_input(self, inp):
        self.write(3, self.read(3) & 0x3f | (inp << 6))
        self.wait_lock()

    def setup(self, s):
        s = self.FrequencySettings().map(s)
        assert self.ident() == bytes([0x01, 0x82])

        # try:
        #     self.write(136, 0x80)  # RST_REG
        # except I2CNACK:
        #     pass
        # time.sleep(.01)
        self.write(136, 0x00)
        time.sleep(.01)

        self.write(0,   self.read(0) | 0x40)  # FREE_RUN=1
        # self.write(0,   self.read(0) & ~0x40)  # FREE_RUN=0
        self.write(2,   (self.read(2) & 0x0f) | (s.bwsel << 4))
        self.write(21,  self.read(21) & 0xfe)  # CKSEL_PIN=0
        self.write(22,  self.read(22) & 0xfd)  # LOL_POL=0
        self.write(19,  self.read(19) & 0xf7)  # LOCKT=0
        self.write(3,   (self.read(3) & 0x3f) | (0b01 << 6) | 0x10)  # CKSEL_REG=b01 SQ_ICAL=1
        self.write(4,   (self.read(4) & 0x3f) | (0b00 << 6))  # AUTOSEL_REG=b00
        self.write(6,   (self.read(6) & 0xc0) | 0b101101)  # SFOUT2_REG=b101 SFOUT1_REG=b101
        self.write(25,  (s.n1_hs  << 5 ))
        self.write(31,  (s.nc1_ls >> 16))
        self.write(32,  (s.nc1_ls >> 8 ))
        self.write(33,  (s.nc1_ls)      )
        self.write(34,  (s.nc2_ls >> 16))
        self.write(35,  (s.nc2_ls >> 8 ))
        self.write(36,  (s.nc2_ls)      )
        self.write(40,  (s.n2_hs  << 5 ) | (s.n2_ls  >> 16))
        self.write(41,  (s.n2_ls  >> 8 ))
        self.write(42,  (s.n2_ls)       )
        self.write(43,  (s.n31    >> 16))
        self.write(44,  (s.n31    >> 8) )
        self.write(45,  (s.n31)         )
        self.write(46,  (s.n32    >> 16))
        self.write(47,  (s.n32    >> 8) )
        self.write(48,  (s.n32)         )
        self.write(137, self.read(137) | 0x01)  # FASTLOCK=1
        self.write(136, self.read(136) | 0x40)  # ICAL=1

        if not self.has_xtal():
            raise ValueError("Si5324 misses XA/XB oscillator signal")
        if not self.has_clkin2():
            raise ValueError("Si5324 misses CLKIN2 signal")
        self.wait_lock()

    def dump(self):
        for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 19, 20, 21, 22, 23, 24,
                25, 31, 32, 33, 34, 35, 36, 40, 41, 42, 43, 44, 45, 46, 47, 48,
                55, 131, 132, 137, 138, 139, 142, 143, 136):
            print("{: 4d}, {:02X}h".format(i, self.read(i)))

    def report(self):
        logger.info("SI5324(DCXO): has_xtal: %s, has_clkin1: %s, "
                    "has_clkin2: %s, locked: %s",
                    self.has_xtal(), self.has_clkin1(),
                    self.has_clkin2(), self.locked())


class EEPROM:
    def __init__(self, bus, addr=0x50, pagesize=8):
        self.bus = bus
        self.addr = addr
        self.pagesize = pagesize

    def dump(self):
        return bytes(self.bus.read_many(self.addr, 0, 1 << 8))

    def poll(self, timeout=1.):
        t = time.monotonic()
        while not self.bus.poll(self.addr):
            if time.monotonic() - t > timeout:
                raise ValueError("poll timeout")
        logger.debug("polling took %g s", time.monotonic() - t)

    def eui48(self):
        return self.bus.read_many(self.addr, 0xfa, 6)

    def eui64(self):
        return self.bus.read_many(self.addr, 0xf8, 8)

    def fmt_eui48(self, eui48=None):
        if eui48 is None:
            eui48 = self.eui48()
        return "{:02x}-{:02x}-{:02x}-{:02x}-{:02x}-{:02x}".format(*eui48)

    def write(self, addr, data):
        assert addr & (self.pagesize - 1) == 0
        for i in range(0, len(data), self.pagesize):
            self.bus.write_many(self.addr, addr + i,
                    data[i:i + self.pagesize], ack=False)
            self.poll()

    def report(self):
        logger.info("24C0x(EEPROM): EUI48: %s", self.fmt_eui48())


class PCF8574:
    """Octal I/O extender, 100 µA pullups, strong rising pulse, open-drain"""
    def __init__(self, bus, addr=0x70):
        self.bus = bus
        self.addr = addr

    def write(self, data):
        self.bus.write_single(self.addr, data)

    def read(self):
        return self.bus.read_single(self.addr)

    def report(self):
        logger.info("PCF8574(IO): %#04x", self.read())


class SFF8472:
    def __init__(self, bus):
        self.bus = bus
        self.addr = 0x50, 0x51

    def read_many(self, addr, reg, length=1, ack=True):
        with self.bus.xfer():
            if not self.bus.write_data(addr << 1) and ack:
                raise I2CNACK("Address Write NACK", addr)
            if not self.bus.write_data(reg) and ack:
                raise I2CNACK("Reg NACK", reg)
            self.bus.restart()
            if not self.bus.write_data((addr << 1) | 1) and ack:
                raise I2CNACK("Address Read NACK", addr)
            return bytes(self.bus.read_data(ack=i < length - 1)
                    for i in range(length))

    def select_page(self, page):
        with self.bus.xfer():
            for val in [0x00, 0x04, 0x02*page]:
                if not self.bus.write_data(val):
                    raise I2CNACK("NACK", val)

    def dump(self):
        # self.select_page(0)
        # c = self.bus.read_stream(self.addr[0], 256)
        # if c[92] & 0x04:
        #     self.select_page(1)
        # d = self.bus.read_stream(self.addr[1], 256)
        # if c[92] & 0x04:
        #     self.select_page(0)
        c = self.read_many(self.addr[0], 0, 256, ack=False)
        d = self.read_many(self.addr[1], 0, 256, ack=False)
        return c, d

    def print_dump(self):
        for i in self.dump():
            logger.warning("        " + " %2i"*16, *range(16))
            logger.warning("        " + " %02x"*16, *range(16))
            for j in range(16):
                logger.warning("%3i, %2x:" + " %2x"*16, j*16, j*16,
                        *i[j*16:(j + 1)*16])

    def watch(self, n=10):
        self.print_dump()
        b = self.dump()
        for i in range(n):
            b, b0 = self.dump(), b
            for j, (c0, c) in enumerate(zip(b0, b)):
                for k, (a0, a) in enumerate(zip(c0, c)):
                    if a0 == a:
                        continue
                    logger.warning("run % 2i, idx %i/%#02x(%3i): "
                                   "%#02x != %#02x", i, j, k, k, a0, a)

    def report(self):
        c, d = self.dump()
        logger.info("SFF8472(SFP): vendor: %s, part: %s, serial: %s",
                c[20:35].strip(), c[40:40+16].strip(), c[68:68+16].strip())
        logger.info("OUI: %s", c[37:40])
        if c[92] & 0x40:
            logger.info("Digital diagnostics implemented")
        if c[92] & 0x04:
            logger.info("Address change sequence required")
        if c[92] & 0x08:
            logger.info("Received power is average power")
        if c[92] & 0x10:
            logger.info("Externally calibrated")
        if c[92] & 0x20:
            logger.info("Internally calibrated")
            t, vcc, tx_bias, tx_pwr, rx_pwr = struct.unpack(
                    ">hHHHH", d[96:106])
            logger.info("Temperature %s C", t/256)
            logger.info("VCC %s V", vcc*100e-6/256)
            logger.info("TX %s mA, %s µW", tx_bias*2e-3/256, tx_pwr*.1/256)
            logger.info("RX %s µW", rx_pwr*.1/256)


class LM75:
    """Temperature sensor with overtemp shutdown output"""
    def __init__(self, bus, addr=0x48):
        self.bus = bus
        self.addr = addr

    def get_temperature(self):
        return self.mu_to_temp(self.bus.read_many(self.addr, 0x00, 2))

    def get_hysteresis(self):
        return self.mu_to_temp(self.bus.read_many(self.addr, 0x02, 2))

    def get_shutdown(self):
        return self.mu_to_temp(self.bus.read_many(self.addr, 0x03, 2))

    def set_hysteresis(self, t):
        self.bus.write_many(self.addr, 0x02, self.temp_to_mu(t))

    def set_shutdown(self, t):
        self.bus.write_many(self.addr, 0x03, self.temp_to_mu(t))

    def mu_to_temp(self, t):
        return t[0] + t[1]/(1 << 8)

    def temp_to_mu(self, t):
        a, b = divmod(t, 1)
        return [int(a), int(b*(1 << 8))]

    def set_config(self, fault_queue=0, os_polarity=0,
            interrupt=0, shutdown=0):
        cfg = ((fault_queue << 3) | (os_polarity << 2) |
                (interrupt << 1) | (shutdown << 0))
        self.bus.write_many(self.addr, 0x01, [cfg])

    def get_config(self):
        cfg = self.bus.read_many(self.addr, 0x01, 1)[0]
        return dict(fault_queue=cfg >> 3, os_polarity=(cfg >> 2) & 1,
                    interrupt=(cfg >> 1) & 1, shutdown=cfg & 1)

    def report(self):
        logger.info("LM75: config: %s, T=%.1f C, H=%.1f C, S=%.1f C",
                    self.get_config(), self.get_temperature(),
                    self.get_hysteresis(), self.get_shutdown())


class SinaraEEPROM(EEPROM):
    def report(self):
        super().report()
        try:
            logger.info("Sinara: %s", Sinara.unpack(self.dump()))
        except:
            logger.info("Sinara data invalid")


class Kasli(I2C):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def select(self, port):
        assert port not in self.skip
        self.enable(self.ports[port])

    def enable(self, *ports):
        assert not any(port in self.skip for port in ports)
        bits = {0x70: 0, 0x71: 0}
        for port in ports:
            assert port not in self.skip
            for addr, p in self.ports[port]:
                bits[addr] |= (1 << p)
        for addr in sorted(bits):
            self.write_single(addr, bits[addr])

    def names(self, paths):
        rev = dict((v, k) for k, v in self.ports)
        return ", ".join(rev[path] for path in paths)

    def scan_devices(self):
        devs = [SinaraEEPROM(self, addr=0x57),
                LM75(self), PCF8574(self, addr=0x3e),
                Si5324(self), SFF8472(self)]
        devs = {dev.addr: dev for dev in devs}

        for port in sorted(self.ports):
            logger.debug("Scanning port %s", port)
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
        ee = EEPROM(self, **kwargs)
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
    p.add_argument("-i", "--index", default=0, type=int)
    p.add_argument("-s", "--serial", default=None)
    p.add_argument("-p", "--port", default=2, type=int)
    p.add_argument("-k", "--skip", action="append", default=[], type=int)
    p.add_argument("-e", "--eem", default=None, type=int)
    p.add_argument("-v", "--verbose", default=0, action="count")

    p.add_argument("action", nargs="*")
    args = p.parse_args()

    logging.basicConfig(
        level=[logging.WARNING, logging.INFO, logging.DEBUG][args.verbose])

    idx = args.serial if args.serial else args.index
    # port 2 for Kasli v1.1
    # port 3 for Kasli v1.0
    dev = Ftdi()
    dev.open_bitbang_from_url("ftdi://ftdi:4232h:{}/{}".format(idx, args.port))
    try:
        bus = Kasli(dev)
        bus.skip = args.skip
        # EEM1 (port 5) SDA shorted on Kasli-v1.0-2

        if not args.action:
            args.action.extend(["scan"])

        with bus:
            bus.clear()
            for action in args.action:
                if action == "speed":
                    bus.test_speed()
                elif action == "scan_tree":
                    logger.warning("%s", bus.make_graph(bus.scan_tree()))
                elif action == "scan":
                    bus.scan_devices()
                elif action == "dump_eeproms":
                    bus.dump_eeproms()
                elif action == "lm75":
                    bus.enable(bus.EEM[args.eem])
                    lm75 = LM75(bus)
                    lm75.report()
                elif action == "si5324":
                    bus.enable(bus.SI5324)
                    si = Si5324(bus)
                    s = Si5324.FrequencySettings()
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
                    bus.enable(bus.SFP[args.eem])
                    sfp0 = SFF8472(bus)
                    sfp0.report()
                    sfp0.watch(n=0)
                elif action == "ee":
                    bus.enable(bus.EEM[args.eem])
                    ee = EEPROM(bus)
                    logger.warning(ee.fmt_eui48())
                    logger.warning(ee.dump())
                    io = PCF8574(bus, addr=0x3e)
                    # io.write(0xff)
                    # logger.warning(hex(io.read()))
                else:
                    raise ValueError("unknown action", action)
            bus.enable()
            # would like to reattach the console port as pyftdi detaches all
            # interfaces indiscriminately. but since it also doesn't claim the
            # serial port interface, we can only release the i2c interface...
            #dev.usb_dev.attach_kernel_driver(2)
    finally:
        dev.close()
