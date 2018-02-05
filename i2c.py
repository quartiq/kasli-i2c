from contextlib import contextmanager
import logging
import time

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

    def write_single(self, addr, data):
        with self.xfer():
            if not self.write_data(addr << 1):
                raise I2CNACK("Address Write NACK", addr)
            if not self.write_data(data):
                raise I2CNACK("Data NACK", reg)

    def read_single(self, addr):
        with self.xfer():
            if not self.write_data((addr << 1) | 1):
                raise I2CNACK("Address Read NACK", addr)
            return self.read_data(ack=False)

    def write_many(self, addr, reg, data):
        with self.xfer():
            if not self.write_data(addr << 1):
                raise I2CNACK("Address Write NACK", addr)
            if not self.write_data(reg):
                raise I2CNACK("Reg NACK", reg)
            for i in data:
                if not self.write_data(i):
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
            return [self.read_data(ack=i < length - 1) for i in range(length)]

    def read_stream(self, addr, length=1):
        with self.xfer():
            if not self.write_data((addr << 1) | 1):
                raise I2CNACK("Address Read NACK", addr)
            return [self.read_data(ack=i < length - 1) for i in range(length)]

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
        logging.info("locking took %g s", time.monotonic() - t)

    def select_input(self, inp):
        self.write(3, self.read(3) & 0x3f | (inp << 6))
        self.wait_lock()

    def setup(self, s):
        s = self.FrequencySettings().map(s)
        assert self.ident() == [0x01, 0x82]

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
    def __init__(self, bus, addr=0x50):
        self.bus = bus
        self.addr = addr

    def dump(self):
        return self.bus.read_many(self.addr, 0, 1 << 8)

    def poll(self, timeout=1.):
        t = time.monotonic()
        while not self.bus.poll(self.addr):
            if time.monotonic() - t > timeout:
                raise ValueError("poll timeout")
        logging.info("polling took %g s", time.monotonic() - t)

    def eui48(self):
        return self.bus.read_many(self.addr, 0xfa, 6)

    def eui64(self):
        return self.bus.read_many(self.addr, 0xf8, 8)

    def fmt_eui48(self):
        return "{:02x}-{:02x}-{:02x}-{:02x}-{:02x}-{:02x}".format(
                *self.eui48())


class SFF8472:
    def __init__(self, bus):
        self.bus = bus
        self.addr = 0x50

    def ident(self):
        return self.bus.read_stream(self.addr, 1)[0]

    def dump(self):
        return self.bus.read_stream(self.addr, 256)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    EEM = [1 << i for i in (7, 5, 4, 3, 2, 1, 0, 6, 12, 13, 15, 14)]
    SFP = [1 << i for i in (8, 9, 10)]
    SI5324 = 1 << 11

    bus = I2C()
    bus.configure("ftdi://ftdi:4232h:Kasli-v1.0-2/3")

    with bus:
        sw0 = PCA9548(bus, 0x70)
        sw1 = PCA9548(bus, 0x71)
        sw0.get()
        sw1.get()

        ee = EEPROM(bus)

        if False:
            t = bus._time
            t0 = time.monotonic()
            for port in range(16):
                print(port)
                if port in ():  # SDA shorted to ground
                    continue
                sw0.set((1 << port) & 0xff)
                sw1.set((1 << port) >> 8)
                for addr in bus.scan():
                    if addr not in (sw0.addr, sw1.addr):
                        print(port, hex(addr))
                    if addr == ee.addr and (1 << port) in EEM:
                        print("EEM", EEM.index(1 << port), ee.fmt_eui48())
            print((bus._time - t)/2/(time.monotonic() - t0), "Hz ~ I2C clock")

        sel = SI5324 | SFP[0] # | EEM[0]
        sw0.set(sel & 0xff)
        assert sw0.get() == sel & 0xff
        sw1.set(sel >> 8)
        assert sw1.get() == sel >> 8

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

        print(si.has_xtal(), si.has_clkin2(), si.locked())

        sfp0 = SFF8472(bus)
        # print(sfp0.ident())
        print(sfp0.dump())

        #ee = EEPROM(bus)
        #print(ee.fmt_eui48())
