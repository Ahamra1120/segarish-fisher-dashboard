"""Load cell weight via an HX711 24-bit amplifier, bit-banged over two GPIOs.

Standard HX711 read protocol: wait for DOUT to go low (conversion ready),
clock 24 bits out on SCK, then one extra clock to select gain/channel for
the next conversion (128 gain / channel A here). No third-party HX711
library dependency — the protocol is small enough to implement directly
against RPi.GPIO, which keeps the dependency footprint down.

Calibration caveat: `scale` (counts-per-kg) must be derived by reading
raw counts with a known reference weight on the cell; `offset` is the
raw zero-point and is normally set at runtime via POST /load/tare rather
than hardcoded.
"""
import logging
import time

from drivers.base import LoadReading

log = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO

    _HARDWARE_AVAILABLE = True
except ImportError:
    _HARDWARE_AVAILABLE = False


class HX711Driver:
    def __init__(self, config):
        self.cfg = config
        self._ok = False
        self.offset = config.HX711_OFFSET
        self.scale = config.HX711_SCALE or 1.0
        if not _HARDWARE_AVAILABLE:
            return
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(config.HX711_DT_PIN, GPIO.IN)
            GPIO.setup(config.HX711_SCK_PIN, GPIO.OUT)
            GPIO.output(config.HX711_SCK_PIN, False)
            self._ok = True
        except Exception as e:  # noqa: BLE001
            log.warning("HX711: failed to init GPIO (%s)", e)
            self._ok = False

    @property
    def available(self):
        return self._ok

    def _read_raw(self) -> int:
        dt, sck = self.cfg.HX711_DT_PIN, self.cfg.HX711_SCK_PIN
        deadline = time.time() + 1.0
        while GPIO.input(dt) == 1:
            if time.time() > deadline:
                raise TimeoutError("HX711 not ready (DOUT stayed high)")
            time.sleep(0.001)

        count = 0
        for _ in range(24):
            GPIO.output(sck, True)
            count = (count << 1) | GPIO.input(dt)
            GPIO.output(sck, False)
        # 25th pulse: gain 128 / channel A for the next conversion.
        GPIO.output(sck, True)
        GPIO.output(sck, False)

        if count & 0x800000:  # sign-extend 24-bit two's complement
            count -= 0x1000000
        return count

    def read(self) -> LoadReading:
        raw = self._read_raw()
        kg = (raw - self.offset) / self.scale
        return LoadReading(ts=time.time(), raw=raw, kg=round(kg, 3), tared=self.offset != 0)

    def tare(self, samples=10):
        vals = [self._read_raw() for _ in range(samples)]
        self.offset = sum(vals) / len(vals)
        return self.offset
