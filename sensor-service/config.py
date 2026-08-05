"""Env-driven configuration for sensor-service.

Every value here can be overridden by an environment variable of the same
name (see deploy/.env.example). Defaults are safe for local/simulate-mode
development; hardware pin/calibration values must be confirmed on the
actual Raspberry Pi before field use.
"""
import os


def _env_str(name, default):
    return os.environ.get(name, default)


def _env_int(name, default):
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default


def _env_float(name, default):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


# --- overall mode ------------------------------------------------------
# "auto" (default): try real hardware drivers, fall back to simulate per
# sensor if the driver's hardware library can't be imported/opened.
# "simulate": force every driver to the simulated fallback (useful for
# dev on a non-Pi machine, or a demo without hardware wired up).
# "hardware": do not fall back — a driver failing to init leaves that
# sensor reporting "unavailable" in /latest rather than switching to fake data.
SENSOR_MODE = _env_str("SENSOR_MODE", "auto")

NODE_ID = _env_str("NODE_ID", "fisher-01")
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")

DATA_DIR = _env_str("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = _env_str("DB_PATH", os.path.join(DATA_DIR, "readings.db"))

HTTP_HOST = _env_str("SENSOR_SERVICE_HOST", "0.0.0.0")
HTTP_PORT = _env_int("SENSOR_SERVICE_PORT", 8100)

# --- poll intervals (seconds) -------------------------------------------
GAS_POLL_INTERVAL_S = _env_float("GAS_POLL_INTERVAL_S", 3.0)
LOAD_POLL_INTERVAL_S = _env_float("LOAD_POLL_INTERVAL_S", 3.0)
GPS_POLL_INTERVAL_S = _env_float("GPS_POLL_INTERVAL_S", 2.0)
CAMERA_SNAPSHOT_INTERVAL_S = _env_float("CAMERA_SNAPSHOT_INTERVAL_S", 5.0)

# How often a combined reading is queued for LoRa uplink. Decoupled from
# the display-poll rates above since LoRa airtime/duty-cycle is precious.
UPLINK_SAMPLE_INTERVAL_S = _env_float("UPLINK_SAMPLE_INTERVAL_S", 45.0)

# History rows older than this are pruned on a slow housekeeping tick, so
# readings.db's per-sensor history tables (used for /history charts) don't
# grow unbounded. Does NOT apply to uplink_queue rows (those are only
# removed once actually sent, per the "hold until success" requirement).
HISTORY_RETENTION_MINUTES = _env_int("HISTORY_RETENTION_MINUTES", 1440)

# --- MQ135 (gas) over MCP3008 (SPI ADC) ---------------------------------
MCP3008_BUS = _env_int("MCP3008_BUS", 0)
MCP3008_DEVICE = _env_int("MCP3008_DEVICE", 0)
MQ135_CHANNEL = _env_int("MQ135_CHANNEL", 0)
ADC_VREF = _env_float("ADC_VREF", 3.3)
# Load resistor on the MQ135 breakout board, typically 10k-22k depending
# on the module; check the board silkscreen/datasheet.
MQ135_RL_KOHM = _env_float("MQ135_RL_KOHM", 10.0)
# Sensor resistance in clean, fresh air — THIS MUST BE CALIBRATED per unit
# (burn the sensor in for 24-48h, then measure Rs outdoors in clean air).
# Left uncalibrated here (None-ish via 0) means ppm_est/level stay
# "unknown" until a real R0 is set, rather than reporting a fake-looking
# number.
MQ135_R0_KOHM = _env_float("MQ135_R0_KOHM", 0.0)
# Rough log-linear curve constants (ppm = a * ratio^b) — approximate,
# datasheet-derived, NOT a lab-grade calibration. Good enough for a
# relative "baik/sedang/buruk" indicator, not for regulatory PPM readings.
MQ135_CURVE_A = _env_float("MQ135_CURVE_A", 116.6020682)
MQ135_CURVE_B = _env_float("MQ135_CURVE_B", -2.769034857)
MQ135_GOOD_MAX_PPM = _env_float("MQ135_GOOD_MAX_PPM", 400.0)
MQ135_WARN_MAX_PPM = _env_float("MQ135_WARN_MAX_PPM", 1000.0)

# --- HX711 (load cell) ---------------------------------------------------
HX711_DT_PIN = _env_int("HX711_DT_PIN", 5)   # BCM numbering
HX711_SCK_PIN = _env_int("HX711_SCK_PIN", 6)
# Zero-offset raw reading (set via /load/tare at runtime; this is just the
# boot default) and counts-per-kg scale factor — both must be calibrated
# per load cell using a known reference weight.
HX711_OFFSET = _env_float("HX711_OFFSET", 0.0)
HX711_SCALE = _env_float("HX711_SCALE", 1.0)

# --- GPS (Sologood M10, UART/NMEA) --------------------------------------
# Default UART device on Raspberry Pi OS (Bookworm) with the mini-UART
# freed up for GPIO14/15; confirm with `raspi-config` serial port setup.
GPS_PORT = _env_str("GPS_PORT", "/dev/serial0")
GPS_BAUD = _env_int("GPS_BAUD", 9600)

# --- Camera (IMX135, CSI via libcamera/picamera2) -----------------------
CAMERA_WIDTH = _env_int("CAMERA_WIDTH", 1024)
CAMERA_HEIGHT = _env_int("CAMERA_HEIGHT", 768)
