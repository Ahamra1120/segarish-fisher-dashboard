"""Simulated fallback drivers — same interface as the real hardware ones.

Used automatically whenever a hardware driver's underlying library can't
be imported (e.g. developing on Windows) or its device can't be opened,
and can be forced everywhere via SENSOR_MODE=simulate. Values follow a
mean-reverting random walk, the same technique segarish's
`useLive.js` uses client-side to fake live sensor data — here it runs
server-side so the exact same JSON shape flows to the frontend whether
the data is real or fake.
"""
import io
import logging
import math
import random
import time

from drivers.base import GasReading, GpsReading, LoadReading

log = logging.getLogger(__name__)


def _mean_revert(value, base, amp, lo, hi):
    drift = random.uniform(-amp, amp)
    reverted = value + drift + (base - value) * 0.12
    return max(lo, min(hi, reverted))


class SimGasDriver:
    def __init__(self, config=None):
        self._ppm = 380.0

    @property
    def available(self):
        return True

    def read(self) -> GasReading:
        self._ppm = _mean_revert(self._ppm, 380.0, 25.0, 250.0, 1400.0)
        level = "baik" if self._ppm < 400 else "sedang" if self._ppm < 1000 else "buruk"
        voltage = 0.9 + (self._ppm / 2000.0)
        return GasReading(
            ts=time.time(),
            raw_adc=int(voltage / 3.3 * 1023),
            voltage=round(voltage, 3),
            rs_ratio=round(2.2 - self._ppm / 2000, 3),
            ppm_est=round(self._ppm, 1),
            level=level,
        )


class SimLoadDriver:
    def __init__(self, config=None):
        self._kg = 4.5

    @property
    def available(self):
        return True

    def read(self) -> LoadReading:
        self._kg = max(0.0, _mean_revert(self._kg, 4.5, 0.3, 0.0, 60.0))
        return LoadReading(ts=time.time(), raw=int(self._kg * 1000), kg=round(self._kg, 3), tared=True)

    def tare(self, samples=10):
        self._kg = 0.0
        return 0.0


class SimGpsDriver:
    def __init__(self, config=None):
        # A plausible starting point off the Indonesian coast (Jakarta Bay).
        self._lat = -5.99
        self._lon = 106.75
        self._heading = 45.0
        self._speed = 4.0

    @property
    def available(self):
        return True

    def read(self) -> GpsReading:
        self._heading = _mean_revert(self._heading, self._heading, 8.0, 0.0, 360.0) % 360
        self._speed = max(0.0, _mean_revert(self._speed, 4.0, 0.6, 0.0, 12.0))
        rad = math.radians(self._heading)
        step_deg = (self._speed * 0.00015)  # knots -> a small lat/lon nudge per tick
        self._lat += math.cos(rad) * step_deg
        self._lon += math.sin(rad) * step_deg
        return GpsReading(
            ts=time.time(),
            fix=True,
            lat=round(self._lat, 6),
            lon=round(self._lon, 6),
            alt_m=round(random.uniform(-1, 3), 1),
            speed_kn=round(self._speed, 1),
            heading_deg=round(self._heading, 1),
            heading_source="gps_cog",
            satellites=random.randint(7, 12),
            hdop=round(random.uniform(0.8, 1.6), 1),
        )


class SimCameraDriver:
    def __init__(self, config=None):
        self._frame_no = 0
        self._width = getattr(config, "CAMERA_WIDTH", 640)
        self._height = getattr(config, "CAMERA_HEIGHT", 480)

    @property
    def available(self):
        return True

    def capture_jpeg_bytes(self) -> bytes:
        self._frame_no += 1
        return self._placeholder_jpeg()

    def _placeholder_jpeg(self) -> bytes:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (self._width, self._height), (14, 116, 144))
        draw = ImageDraw.Draw(img)
        ts_label = time.strftime("%Y-%m-%d %H:%M:%S")
        draw.text((24, 24), "SIMULATED CAMERA (no CSI hardware)", fill=(236, 254, 255))
        draw.text((24, 52), f"frame #{self._frame_no}  {ts_label}", fill=(207, 250, 254))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
