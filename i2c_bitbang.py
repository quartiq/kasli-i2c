import time
import logging
from contextlib import contextmanager

from pyftdi.ftdi import Ftdi
from pyftdi.i2c import I2cNackError

logger = logging.getLogger(__name__)

I2CNACK = I2cNackError


class I2C:
    SCL = 1 << 0
    SDAO = 1 << 1
    SDAI = 1 << 2
    EN = (1 << 4) | (1 << 6)  # 4 on <=v2.0, 6 on >v2.0
    RESET = 1 << 5  # >=v2.0, <v2.0 has it on CDBUS4
    max_clock_stretch = 100

    def __init__(self):
        self.dev = Ftdi()
        self._time = 0
        self._direction = 0

    def configure(self, url, **kwargs):
        self.dev.open_bitbang_from_url(url, **kwargs)
        return self

    def tick(self):
        self._time += 1

    def reset(self):
        self.write(self.EN | self.RESET)
        self.tick()
        self.write(self.EN)
        self.tick()
        time.sleep(.01)

    def set_direction(self, direction):
        self._direction = direction
        self.dev.set_bitmode(direction, Ftdi.BitMode.BITBANG)

    def write(self, data):
        self.dev.write_data(bytes([data]))

    def read(self):
        return self.dev.read_pins()

    def scl_oe(self, oe):
        d = self._direction & ~self.SCL
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
        # EN, !SCL, !SDA
        self.write(self.EN)
        # enable USB-I2C
        self.set_direction(self.EN | self.RESET)
        self.tick()
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
        return self

    def release(self):
        self.set_direction(self.EN | self.RESET)
        self.write(0)
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
        logger.debug("S")
        assert self.scl_i()
        if not self.sda_i():
            raise ValueError("Arbitration lost")
        self.sda_oe(True)
        self.tick()
        self.scl_oe(True)
        # SCL low, SDA low

    def stop(self):
        logger.debug("P")
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
        logger.debug("R")
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
        logger.debug("W %#02x %s", data, "A" if ack else "N")
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
        logger.debug("R %#02x %s", data, "A" if ack else "N")
        return data

    @contextmanager
    def xfer(self):
        self.start()
        try:
            yield
        finally:
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

    def poll(self, addr, write=False):
        with self.xfer():
            return self.write_data((addr << 1) | int(not write))
