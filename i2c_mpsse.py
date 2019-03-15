import logging
from array import array

from pyftdi.ftdi import Ftdi
from pyftdi.i2c import I2cController

logger = logging.getLogger(__name__)


class I2C(I2cController):
    EN = 1 << 4
    RESET_B = 1 << 5

    def __init__(self):
        super().__init__()
        self.log.setLevel(logging.ERROR)  # suppress NACK warnings on poll()
        self._direction |= self.EN | self.RESET_B
        self._idle = (Ftdi.SET_BITS_LOW, self.IDLE, self._direction)
        self._data_lo = (Ftdi.SET_BITS_LOW,
                         self.IDLE & ~self.SDA_O_BIT, self._direction)
        self._clk_lo_data_lo = (Ftdi.SET_BITS_LOW,
                                self.IDLE & ~(self.SDA_O_BIT | self.SCL_BIT),
                                self._direction)
        self._clk_lo_data_hi = (Ftdi.SET_BITS_LOW,
                                self.IDLE & ~self.SCL_BIT,
                                self._direction)

    def configure(self, url, **kwargs):
        super().configure(url, **kwargs)
        if self._tristate:
            self._tristate = (Ftdi.SET_BITS_LOW, self.EN | self.RESET_B,
                              self.SCL_BIT | self.EN | self.RESET_B)
        # self.set_retry_count(1)
        return self

    def reset_switch(self):
        cmd = array("B")
        cmd.extend((Ftdi.SET_BITS_LOW, self.IDLE & ~self.RESET_B,
                    self._direction) * 100)
        cmd.extend((Ftdi.SET_BITS_LOW, self.IDLE,
                    self._direction) * 100)
        self._ftdi.write_data(cmd)

    def acquire(self):
        cmd = array("B")
        cmd.extend((Ftdi.SET_BITS_LOW, self.IDLE, self._direction))
        self._ftdi.write_data(cmd)
        return self

    def release(self):
        cmd = array("B")
        cmd.extend((Ftdi.SET_BITS_LOW, self.IDLE & ~self.EN,
                    self._direction))
        self._ftdi.write_data(cmd)
        self.terminate()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()

    def write_single(self, addr, data):
        self.write(addr, bytes([data]), relax=True)

    def read_single(self, addr):
        return self.read(addr, readlen=1, relax=True)

    def write_many(self, addr, reg, data):
        self.write(addr, bytes([reg]) + bytes(data), relax=True)

    def read_many(self, addr, reg, length=1):
        return bytes(self.exchange(addr, bytes([reg]), readlen=length,
                                   relax=True))

    def read_stream(self, addr, length=1):
        return bytes(self.read(addr, readlen=length, relax=True))
