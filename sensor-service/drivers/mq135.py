"""MQ135 gas/air-quality sensor, read through an MCP3008 ADC over SPI.

MQ135 is analog-only, so it can't connect straight to the Pi's digital
GPIOs — it goes into one MCP3008 channel, and we bit-bang MCP3008's SPI
protocol to get a 10-bit raw value back.

Calibration caveat: MQ135 readings are only as good as R0 (the sensor's
resistance in clean, calibrated air), which varies per physical unit and
must be measured after a 24-48h burn-in. Until config.MQ135_R0_KOHM is
set to a real measured value, ppm_est/level stay "unknown" rather than
showing a made-up number. See README.md for the calibration procedure.
"""
import logging
import time

from drivers.base import GasReading

log = logging.getLogger(__name__)

try:
    import spidev

    _HARDWARE_AVAILABLE = True
except ImportError:
    _HARDWARE_AVAILABLE = False


class MQ135Driver:
    def __init__(self, config):
        self.cfg = config
        self._spi = None
        if not _HARDWARE_AVAILABLE:
            return
        try:
            self._spi = spidev.SpiDev()
            self._spi.open(config.MCP3008_BUS, config.MCP3008_DEVICE)
            self._spi.max_speed_hz = 1_350_000
        except Exception as e:  # noqa: BLE001 - want any hardware-open failure to fall back
            log.warning("MQ135: failed to open SPI (%s)", e)
            self._spi = None

    @property
    def available(self):
        return self._spi is not None

    def _read_adc(self, channel: int) -> int:
        cmd = [1, (8 + channel) << 4, 0]
        resp = self._spi.xfer2(cmd)
        return ((resp[1] & 3) << 8) | resp[2]

    def read(self) -> GasReading:
        raw = self._read_adc(self.cfg.MQ135_CHANNEL)
        voltage = raw / 1023.0 * self.cfg.ADC_VREF

        rs_ratio = None
        ppm_est = None
        level = "unknown"

        if voltage > 0.01:
            rs_kohm = ((self.cfg.ADC_VREF * self.cfg.MQ135_RL_KOHM) / voltage) - self.cfg.MQ135_RL_KOHM
            if self.cfg.MQ135_R0_KOHM > 0:
                rs_ratio = rs_kohm / self.cfg.MQ135_R0_KOHM
                # Rough log-linear estimate (ppm = a * ratio^b). Datasheet-derived,
                # not lab-accurate — good enough for a relative good/warn/bad band.
                ppm_est = self.cfg.MQ135_CURVE_A * (rs_ratio ** self.cfg.MQ135_CURVE_B)
                if ppm_est < self.cfg.MQ135_GOOD_MAX_PPM:
                    level = "baik"
                elif ppm_est < self.cfg.MQ135_WARN_MAX_PPM:
                    level = "sedang"
                else:
                    level = "buruk"

        return GasReading(
            ts=time.time(),
            raw_adc=raw,
            voltage=round(voltage, 3),
            rs_ratio=round(rs_ratio, 3) if rs_ratio is not None else None,
            ppm_est=round(ppm_est, 1) if ppm_est is not None else None,
            level=level,
        )

    def close(self):
        if self._spi:
            self._spi.close()
