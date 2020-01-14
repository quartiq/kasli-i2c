import logging
import sys
import time
from contextlib import contextmanager

from sinara import Sinara
from kasli import Kasli
import chips

logger = logging.getLogger(__name__)


class Fastino:
    def __init__(self, bus):
        self.bus = bus
        self.eeprom = chips.EEPROM(bus)
        self.temp1 = chips.LM75(bus, 0x48)
        self.spi = chips.SPI(bus, 0x2a)
        self.flash = chips.SPIFlash(self.spi, 0b0001)

    def init(self):
        self.spi.gpio_write(0b1000)  # GPIO output values
        # ssel bidir (ignored), spi_en: push-pull, cdone: input, creset: bidir
        self.spi.gpio_config(0b00, 0b01, 0b10, 0b00)
        self.spi.gpio_enable(0b1110)  # use as GPIO
        i = self.spi.gpio_read()
        assert not i & 0b0010  # SPI disable
        assert i & 0b0001  # SS deassert
        assert i & 0b1000  # CRESET deassert
        # MSB-first, CPOL/CPHA=00, 1.8 MHz
        self.spi.configure(order=0, mode=0, f=0)

    def report(self):
        ee = self.eeprom.dump()
        try:
            logger.info("Sinara eeprom valid %s", Sinara.unpack(ee))
        except:
            logger.error("eeprom data invalid %r", ee)
        self.temp1.report()
        logging.info("gpio: %#02x", self.spi.gpio_read())

    def report_flash(self):
        logging.info("ident: %r", self.flash.read_identification())
        logging.info("status: %#02x", self.flash.read_status())

    def creload(self, timeout=.5):
        self.spi.gpio_write(0b0000)  # CRESET
        assert not self.spi.gpio_read() & 0b1000  # CRESET assert
        assert not self.spi.gpio_read() & 0b0100  # not CDONE
        self.spi.gpio_write(0b1000)  # no CRESET
        assert self.spi.gpio_read() & 0b1000  # CRESET deassert
        t = time.monotonic()
        while not self.spi.gpio_read() & 0b0100:  # not CDONE
            if time.monotonic() - t > timeout:
                raise ValueError("cdone timeout")
        logger.info("creload took %g s", time.monotonic() - t)

    @contextmanager
    def flash_upd(self):
        # freeze it while loading
        self.spi.gpio_write(0b0000)  # assert CRESET
        self.spi.gpio_write(0b1000)  # deassert CRESET
        self.spi.gpio_write(0b0000)  # assert CRESET
        self.spi.gpio_write(0b0010)  # assert FLASH_UPD_EN
        try:
            self.flash.wakeup()
            yield
            self.flash.write_disable()
            self.flash.power_down()
        finally:
            self.spi.gpio_write(0b1000)
            self.spi.idle()

    def dump(self, fil, length=0x22000, offset=0):
        with open(fil, "wb") as fil:
            for i in range(offset, offset + length, 196):
                logger.info("read %s/%s", i, length)
                fil.write(self.flash.read_data_bytes(i, 196))

    def eeprom_update(self, **kwargs):
        eui48 = self.eeprom.eui48()
        logger.info("eui48 %s", self.eeprom.fmt_eui48())
        ee_data = Sinara(
            name="Fastino",
            board=Sinara.boards.index("Fastino"),
            major=1, minor=0, variant=0, port=0,
            vendor=Sinara.vendors.index("QUARTIQ"),
            vendor_data=Sinara._defaults.vendor_data)
        kwargs["eui48"] = eui48
        data = ee_data._replace(**kwargs)
        self.eeprom.write(0, data.pack()[:128])
        open("data/{}.bin".format(self.eeprom.fmt_eui48(eui48)),
             "wb").write(data.pack())
        try:
            logger.info("data readback valid %s",
                        Sinara.unpack(self.eeprom.dump()))
        except:
            logger.error("data readback invalid", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serial = sys.argv[1]
    logger.info("serial: %s", serial)

    url = "ftdi://ftdi:4232h:{}/2".format(serial)
    with Kasli().configure(url) as bus, bus.enabled(sys.argv[2]):
        b = Fastino(bus)
        b.report()
        b.init()
        action = sys.argv[3]
        if action == "eeprom":
            b.eeprom_update()
        with b.flash_upd():
            b.report_flash()
            if action == "read":
                b.dump(sys.argv[4])
            elif action == "write":
                with open(sys.argv[4], "rb") as fil:
                    b.flash.flash(0, fil.read(), verify=False)
        b.creload()
