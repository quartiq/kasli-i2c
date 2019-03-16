import time
import logging
from contextlib import contextmanager
import struct

from sinara import Sinara

logger = logging.getLogger(__name__)


class ScanI2C:
    def scan(self, addrs=None):
        for addr in addrs or range(0x08, 0x78):
            if self.poll(addr, write=True):
                yield addr

    def scan_tree(self, addr_mask=(0x70, 0x78), addrs=None, skip=[]):
        found = [addr for addr in self.scan(addrs) if addr not in skip]
        for addr in found:
            if (addr ^ addr_mask[0]) & addr_mask[1]:
                # leaf, not switch
                yield [], addr
                continue
            # scan each switch port
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

    @contextmanager
    def enabled(self, ports):
        self.set(ports)
        try:
            yield
        finally:
            self.set(0)


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
        # except I2cNackError:
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
        while not self.bus.poll(self.addr, write=True):
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
                    data[i:i + self.pagesize])
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
        self.addr = 0x50
        self.addr1 = 0x51

    def dump(self):
        c = self.bus.read_many(self.addr, 0, 256)
        d = self.bus.read_many(self.addr1, 0, 256)
        return c, d

    def print_dump(self, dump):
        logger.warning("        " + " %2i"*16, *range(16))
        logger.warning("        " + " %02x"*16, *range(16))
        for j in range(16):
            logger.warning("%3i, %2x:" + " %2x"*16, j*16, j*16,
                    *dump[j*16:(j + 1)*16])

    def watch(self, n=10):
        b = self.dump()
        for i in b:
            self.print_dump(i)
        for i in range(n):
            b, b0 = self.dump(), b
            for j, (c0, c) in enumerate(zip(b0, b)):
                for k, (a0, a) in enumerate(zip(c0, c)):
                    if a0 == a:
                        continue
                    logger.warning("run % 2i, idx %i/%#02x(%3i): "
                                   "%#02x != %#02x", i, j, k, k, a0, a)

    def report(self):
        if self.bus.read_many(self.addr, 63, 1) in b"\x00\xff":
            logger.debug("invalid SFF CC_BASE, ignoring")
            return
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


class SPI:
    """I2C to SPI converter, SC18IS602B"""
    def __init__(self, bus, addr=0x40):
        self.bus = bus
        self.addr = addr
        self.max_buffer = 200

    def poll(self, timeout=.1):
        t = time.monotonic()
        while not self.clear_interrupt():
            if time.monotonic() - t > timeout:
                raise ValueError("poll timeout")
        logger.debug("polling took %g s", time.monotonic() - t)

    def spi_write(self, ss, data, read=False):
        assert len(data) <= self.max_buffer
        self.bus.write_many(self.addr, ss, data)

    def buffer_read(self, length):
        return self.bus.read_stream(self.addr, length)

    def configure(self, order=0, mode=0, f=0):
        self.bus.write_many(self.addr, 0xf0, [(order << 5) | (mode << 2) | f])

    def clear_interrupt(self):
        try:
            self.bus.write_single(self.addr, 0xf1)
            return True
        except I2cNackError:
            return False

    def idle(self):
        self.bus.write_single(self.addr, 0xf2)

    def gpio_write(self, gpio):
        self.bus.write_many(self.addr, 0xf4, [gpio])

    def gpio_read(self):
        self.bus.write_many(self.addr, 0xf5, [0])
        return self.buffer_read(1)[0]

    def gpio_enable(self, gpio):
        self.bus.write_many(self.addr, 0xf6, [gpio])

    def gpio_config(self, *ss):
        """quasi-bidir, push-pull, input, open-drain"""
        cfg = sum((ssi << (2*i) for i, ssi in enumerate(ss)), 0)
        self.bus.write_many(self.addr, 0xf7, [cfg])


class SPIFlash:
    def __init__(self, bus, ss, sector=0x10000):
        self.ss = ss  # slave select bit mask
        self.bus = bus
        self.sector = sector

    def xfer(self, data, read=False):
        self.bus.spi_write(self.ss, data)
        self.bus.poll()
        if read:
            return self.bus.buffer_read(len(data))

    def cmd(self, cmd, offset=0):
        return bytes([cmd, offset >> 16, (offset >> 8) & 0xff, offset & 0xff])

    def read_identification(self):
        return self.xfer(self.cmd(0x9f), read=True)[1:]

    def read_status(self):
        return self.xfer([0x05, 0xff], read=True)[1]

    def write_enable(self):
        self.xfer([0x06])
        assert self.read_status() & 2  # WE

    def write_disable(self):
        self.xfer([0x04])
        assert not self.read_status() & 2  # WE

    def poll(self, timeout=4.):
        t = time.monotonic()
        while self.read_status() & 1:  # write in progress
            if time.monotonic() - t > timeout:
                raise ValueError("write timeout")
        logger.debug("write took %g s", time.monotonic() - t)

    def read_data_bytes(self, offset, length):
        return self.xfer(self.cmd(0x03, offset) + bytes(length), read=True)[4:]

    def sector_erase(self, offset):
        self.xfer(self.cmd(0xd8, offset))
        self.poll()

    def page_program(self, offset, data):
        self.xfer(self.cmd(0x02, offset) + data)
        self.poll()

    def flash(self, offset, data):
        n = 128  # self.bus.max_buffer - 4 will cross page boundary
        assert offset & (self.sector - 1) == 0
        for addr in range(offset, offset + len(data), n):
            if not addr & (self.sector - 1):
                self.write_enable()
                self.sector_erase(addr)
            write = data[addr - offset:addr - offset + n]
            self.write_enable()
            self.page_program(addr, write)
            read = self.read_data_bytes(addr, len(write))
            logger.info("%#06x / %#06x", addr, offset + len(data))
            if write != read:
                raise RuntimeError("verify failed at %#06x: "
                                   "write %r != read %r",
                                    hex(addr), write, read)


class SinaraEEPROM(EEPROM):
    def report(self):
        super().report()
        try:
            logger.info("Sinara: %s", Sinara.unpack(self.dump()))
        except:
            logger.info("Sinara data invalid")


