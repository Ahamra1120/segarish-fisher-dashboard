"""GPS via a Sologood M10 module (u-blox M10 GNSS) over UART, NMEA-0183.

The M10 is GNSS-only — it has no onboard magnetometer/compass — so
`heading_deg` here is the GPS course-over-ground (COG) from RMC
sentences, which is only meaningful while the vessel is actually moving
at a few knots or more; it reads as stale/None at low speed. This is
surfaced to the UI as "Heading (GPS)" rather than "Compass" so it isn't
mistaken for a true magnetic heading. `heading_source` on every reading
exists specifically so a real magnetometer driver can be swapped in
later (e.g. QMC5883L over I2C) without changing anything downstream.
"""
import logging
import time

from drivers.base import GpsReading

log = logging.getLogger(__name__)

try:
    import serial

    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

try:
    import pynmea2

    _NMEA_AVAILABLE = True
except ImportError:
    _NMEA_AVAILABLE = False

_HARDWARE_AVAILABLE = _SERIAL_AVAILABLE and _NMEA_AVAILABLE


class GpsDriver:
    def __init__(self, config):
        self.cfg = config
        self._ser = None
        self._last = GpsReading(
            ts=time.time(), fix=False, lat=None, lon=None, alt_m=None,
            speed_kn=None, heading_deg=None, heading_source="gps_cog",
            satellites=None, hdop=None,
        )
        if not _HARDWARE_AVAILABLE:
            return
        try:
            self._ser = serial.Serial(config.GPS_PORT, config.GPS_BAUD, timeout=1.0)
        except Exception as e:  # noqa: BLE001
            log.warning("GPS: failed to open serial port %s (%s)", config.GPS_PORT, e)
            self._ser = None

    @property
    def available(self):
        return self._ser is not None

    def read(self) -> GpsReading:
        # Drain whatever NMEA sentences arrive during one poll window,
        # keeping the most recent RMC (fix/lat/lon/speed/course) and GGA
        # (altitude/satellites/HDOP) values seen.
        deadline = time.time() + self.cfg.GPS_POLL_INTERVAL_S
        while time.time() < deadline:
            try:
                raw_line = self._ser.readline()
            except Exception:  # noqa: BLE001
                break
            if not raw_line:
                continue
            line = raw_line.decode("ascii", errors="ignore").strip()
            if not line:
                continue
            try:
                msg = pynmea2.parse(line)
            except pynmea2.ParseError:
                continue

            sentence_type = getattr(msg, "sentence_type", "")
            if sentence_type == "RMC":
                self._last.fix = msg.status == "A"
                if self._last.fix:
                    self._last.lat = msg.latitude
                    self._last.lon = msg.longitude
                    self._last.speed_kn = float(msg.spd_over_grnd) if msg.spd_over_grnd not in (None, "") else None
                    if msg.true_course not in (None, ""):
                        self._last.heading_deg = float(msg.true_course)
            elif sentence_type == "GGA":
                self._last.satellites = int(msg.num_sats) if msg.num_sats not in (None, "") else None
                self._last.hdop = float(msg.horizontal_dil) if msg.horizontal_dil not in (None, "") else None
                if msg.altitude not in (None, ""):
                    self._last.alt_m = float(msg.altitude)

        self._last.ts = time.time()
        return self._last
