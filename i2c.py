from contextlib import contextmanager
import logging
import time
import struct

import pyftdi.gpio


logger = logging.getLogger(__name__)


class I2C(pyftdi.gpio.GpioController):
    SCL = 1 << 0
    SDAO = 1 << 1
    SDAI = 1 << 2
    EN = 1 << 4

    def configure(self, url, **kwargs):
        super().configure(url, direction=0, **kwargs)
        self._time = 0

    def tick(self):
        self._time += 1

    def scl_oe(self, oe):
        self.set_direction(self.SCL, bool(oe)*0xff)

    def sda_oe(self, oe):
        self.set_direction(self.SDAO, bool(oe)*0xff)

    def scl_i(self):
        return bool(self.read() & self.SCL)

    def sda_i(self):
        return bool(self.read() & self.SDAI)

    def acquire(self):
        self.write(self.EN)  # EN, !SCL, !SDA
        self.set_direction(self.EN, 0xff)  # enable USB-I2C
        self.tick()
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
        self.write(0)
        self.set_direction(0xff, 0x00)  # all high-Z
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

    def reset(self):
        self.tick()
        self.scl_oe(False)
        self.tick()
        self.sda_oe(False)
        self.tick()
        for i in range(9):
            if self.sda_i():
                break
            self.scl_oe(True)
            self.tick()
            self.scl_oe(False)
            self.tick()
        assert self.scl_i()
        assert self.sda_i()

    def start(self):
        assert self.scl_i()
        assert self.sda_i()
        self.sda_oe(True)
        self.tick()
        self.scl_oe(True)
        # SCL low, SDA low

    def stop(self):
        # SCL low, SDA low
        self.tick()
        self.scl_oe(False)
        self.tick()
        self.sda_oe(False)
        self.tick()
        assert self.scl_i()
        assert self.sda_i()

    def restart(self):
        # SCL low, SDA low
        self.sda_oe(False)
        self.tick()
        self.scl_oe(False)
        self.tick()
        self.start()

    def write_data(self, data):
        for i in range(8):
            bit = bool(data & (1 << 7 - i))
            self.sda_oe(not bit)
            self.tick()
            self.scl_oe(False)
            self.tick()
            self.scl_oe(True)
        # check ACK
        self.sda_oe(False)
        self.tick()
        self.scl_oe(False)
        self.tick()
        ack = not self.sda_i()
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
            bit = self.sda_i()
            if bit:
                data |= 1 << 7 - i
            self.scl_oe(True)
        # send ACK
        self.sda_oe(ack)
        self.tick()
        self.scl_oe(False)
        self.tick()
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
                raise I2CNACK("Data NACK", reg)

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
            return bytes(self.read_data(ack=i < length - 1) for i in range(length))

    def read_stream(self, addr, length=1):
        with self.xfer():
            if not self.write_data((addr << 1) | 1):
                raise I2CNACK("Address Read NACK", addr)
            return bytes(self.read_data(ack=i < length - 1) for i in range(length))

    def poll(self, addr):
        with self.xfer():
            return self.write_data(addr << 1)

    def scan(self):
        for addr in range(1 << 7):
            if self.poll(addr):
                    yield addr


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

    def fmt_eui48(self):
        return "{:02x}-{:02x}-{:02x}-{:02x}-{:02x}-{:02x}".format(
                *self.eui48())

    def write(self, addr, data):
        for i in range(0, len(data), self.pagesize):
            self.bus.write_many(self.addr, addr + i,
                    data[i:i + self.pagesize], ack=False)
            self.poll()


class PCF8574:
    """Octal I/O extender, 100 µA pullups, strong rising pulse, open-drain"""
    def __init__(self, bus, addr=0x70):
        self.bus = bus
        self.addr = addr

    def write(self, data):
        self.bus.write_single(self.addr, data)

    def read(self):
        return self.bus.read_single(self.addr)


class SFF8472:
    def __init__(self, bus):
        self.bus = bus
        self.addr = 0x50, 0x51

    def select_page(self, page):
        with self.bus.xfer():
            for val in [0x00, 0x04, 0x02*page]:
                if not self.bus.write_data(val):
                    raise I2CNACK("NACK", val)

    def dump(self):
        # self.select_page(0)
        c = self.bus.read_stream(self.addr[0], 256)
        # if c[92] & 0x04:
        #     self.select_page(1)
        d = self.bus.read_stream(self.addr[1], 256)
        # if c[92] & 0x04:
        #     self.select_page(0)
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
                    logger.warning("run % 2i, idx %i/%#02x(%3i): %#02x != %#02x",
                            i, j, k, k, a0, a)

    def report(self):
        c, d = self.dump()
        #logger.info("Part: %s, Serial: %s", c[40:40+16], c[68:68+16])
        #logger.info("Vendor: %s", c[20:35])
        #logger.info("OUI: %s", c[37:40])
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


class Kasli10(I2C):
    EEM = [1 << i for i in (7, 5, 4, 3, 2, 1, 0, 6, 12, 13, 15, 14)]
    SFP = [1 << i for i in (8, 9, 10)]
    SI5324 = 1 << 11
    skip = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.sw0 = PCA9548(self, 0x70)
        self.sw1 = PCA9548(self, 0x71)

    def select(self, port):
        self.enable(1 << port)

    def enable(self, ports):
        assert not any(ports & (1 << i) for i in self.skip)
        self.sw0.set(ports & 0xff)
        self.sw1.set(ports >> 8)

    def test_speed(self):
        t = self._time
        t0 = time.monotonic()
        for port in range(16):
            if port in self.skip:
                continue
            self.select(port)
            assert self.sw0.get() == (1 << port) & 0xff
            assert self.sw1.get() == (1 << port) >> 8
            for addr in self.scan():
                pass
        clock = (self._time - t)/2/(time.monotonic() - t0)
        logger.info("I2C speed ~%s Hz", clock)

    def scan_eui48(self):
        self.sw0.get()
        self.sw1.get()

        ee = EEPROM(self)

        for port in range(16):
            logger.info("Scanning port %i", port)
            if port in self.skip:
                continue
            self.select(port)
            for addr in self.scan():
                if addr not in (self.sw0.addr, self.sw1.addr):
                    logger.info("Port %i: found %#02x", port, addr)
                if addr == ee.addr and (1 << port) in self.EEM:
                    logger.warning("EEM %i: %s", self.EEM.index(1 << port), ee.fmt_eui48())

    def dump_eeproms(self, **kwargs):
        ee = EEPROM(self, **kwargs)
        for port in range(16):
            logger.info("Scanning port %i", port)
            if port in self.skip:
                continue
            self.select(port)
            if self.poll(ee.addr):
                eui48 = ee.fmt_eui48()
                logger.info("Port %i: found %s", port, eui48)
                open("data/{}.bin".format(eui48), "wb").write(ee.dump())

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    p = argparse.ArgumentParser()
    p.add_argument("-i", "--index", default=0, type=int)
    p.add_argument("-s", "--serial", default=None)
    p.add_argument("-k", "--skip", action="append", default=[], type=int)
    p.add_argument("-e", "--eem", default=None, type=int)
    p.add_argument("action", nargs="*")
    args = p.parse_args()

    bus = Kasli10()
    idx = args.serial if args.serial else args.index
    bus.configure("ftdi://ftdi:4232h:{}/3".format(idx))
    bus.skip = args.skip
    # EEM1 (port 5) SDA shorted on Kasli-v1.0-2

    if not args.action:
        args.action.extend(["scan", "si5324"])

    with bus:
        bus.reset()
        for action in args.action:
            if action == "speed":
                bus.test_speed()
            elif action == "scan":
                bus.scan_eui48()
            elif action == "dump_eeproms":
                bus.dump_eeproms()
            elif action == "si5324":
                bus.enable(bus.SI5324)
                si = Si5324(bus)
                s = Si5324.FrequencySettings()
                if True:
                    s.n31 = 9370  # 100 MHz CKIN1
                    s.n32 = 7139  # 114.285 MHz CKIN2 XTAL
                    s.n1_hs = 9
                    s.nc1_ls = 4
                    s.nc2_ls = 4
                    s.n2_hs = 10
                    s.n2_ls = 33732 # 150MHz CKOUT
                    s.bwsel = 3
                else:
                    s.n31 = 75  # 125 MHz CKIN1
                    s.n32 = 6   # 10 MHz CKIN2
                    s.n1_hs = 10
                    s.nc1_ls = 4
                    s.nc2_ls = 4
                    s.n2_hs = 10
                    s.n2_ls = 300  # 125MHz CKOUT
                    s.bwsel = 10
                si.setup(s)
                logger.warning("flags %s %s %s", si.has_xtal(),
                        si.has_clkin2(), si.locked())
            elif action == "sfp":
                bus.enable(bus.SFP[args.eem])
                sfp0 = SFF8472(bus)
                sfp0.report()
                sfp0.watch()
            elif action == "ee":
                bus.enable(bus.EEM[args.eem])
                ee = EEPROM(bus)
                logger.warning(ee.fmt_eui48())
                logger.warning(ee.dump())
                io = PCF8574(bus, addr=0x3e)
                #io.write(0xff)
                #logger.warning(hex(io.read()))
            else:
                raise ValueError("unknown action", action)
