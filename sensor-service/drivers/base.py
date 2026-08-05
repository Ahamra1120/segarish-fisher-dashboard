"""Shared reading types for every sensor driver (real or simulated).

Every driver — hardware or `simulate.py` fallback — returns one of these
dataclasses from `.read()`, so the rest of the service (storage, API,
uplink payload builder) never needs to know whether the data came off a
real MCP3008/HX711/GPS/camera or a random-walk fake.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class GasReading:
    ts: float
    raw_adc: int
    voltage: float
    rs_ratio: Optional[float]
    ppm_est: Optional[float]
    level: str  # "baik" | "sedang" | "buruk" | "unknown"


@dataclass
class LoadReading:
    ts: float
    raw: int
    kg: float
    tared: bool


@dataclass
class GpsReading:
    ts: float
    fix: bool
    lat: Optional[float]
    lon: Optional[float]
    alt_m: Optional[float]
    speed_kn: Optional[float]
    heading_deg: Optional[float]
    heading_source: str  # "gps_cog" (course-over-ground; no magnetometer on this node)
    satellites: Optional[int]
    hdop: Optional[float]


class SensorDriver:
    """Common interface every driver implements (duck-typed, not enforced)."""

    @property
    def available(self) -> bool:
        """True if this driver is backed by real hardware that initialized OK."""
        raise NotImplementedError

    def read(self):
        raise NotImplementedError
