"""Env-driven configuration for lora-uplink. Overridable via env vars /
.env (see deploy/.env.example)."""
import os
from pathlib import Path


def _env_str(name, default):
    return os.environ.get(name, default)


def _env_int(name, default):
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default


def _env_float(name, default):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


NODE_ID = _env_str("NODE_ID", "fisher-01")
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")

_BASE_DIR = Path(__file__).resolve().parent
# Shares the same SQLite file sensor-service writes uplink_queue rows
# into — this process never touches sensor hardware directly.
DB_PATH = _env_str("DB_PATH", str(_BASE_DIR.parent / "sensor-service" / "data" / "readings.db"))

# "auto" (default): use the real RFM9x radio if the Blinka/adafruit_rfm9x
# libraries import and the radio initializes; simulate otherwise.
# "simulate": always use the simulated radio (dev, or to force test
# failures via SIMULATE_FAIL_RATE below).
LORA_MODE = _env_str("LORA_MODE", "auto")

# --- radio parameters ------------------------------------------------------
# Default centers on Indonesia's unlicensed LPWAN allocation (~920-923 MHz
# per Kominfo) -- CONFIRM against the actual gateway/local regulations
# before field use. Many hobbyist SX1276 boards are silkscreened
# 433/868/915 MHz, but the frequency is a software-tunable radio
# parameter on the chip, not fixed by the board.
LORA_FREQ_MHZ = _env_float("LORA_FREQ_MHZ", 923.0)
LORA_TX_POWER_DBM = _env_int("LORA_TX_POWER_DBM", 17)
LORA_SPREADING_FACTOR = _env_int("LORA_SPREADING_FACTOR", 7)
LORA_BANDWIDTH_HZ = _env_int("LORA_BANDWIDTH_HZ", 125000)
LORA_CODING_RATE = _env_int("LORA_CODING_RATE", 5)

# SPI/GPIO wiring, as Blinka `board.*` pin names (BCM-style labels on a
# Pi, e.g. "D25"); see README.md wiring table.
LORA_CS_PIN = _env_str("LORA_CS_PIN", "D25")
LORA_RESET_PIN = _env_str("LORA_RESET_PIN", "D22")

# --- send loop / buffering --------------------------------------------------
SEND_RETRY_INTERVAL_S = _env_float("SEND_RETRY_INTERVAL_S", 60.0)
DRAIN_THROTTLE_S = _env_float("DRAIN_THROTTLE_S", 3.0)
# Safety net only (see queue_store.evict_oldest_pending). Default is
# generous -- tens of thousands of rows, at the sensor-service default
# 45s sample interval that's many days of outage -- so "hold until
# success" holds in any realistic scenario before this ever bites.
BUFFER_CAP_ROWS = _env_int("BUFFER_CAP_ROWS", 50000)

# No gateway exists yet to ACK with, so this defaults off; flip on once a
# gateway that replies with a short ack packet exists.
LORA_WAIT_ACK = _env_str("LORA_WAIT_ACK", "false").lower() == "true"
LORA_ACK_TIMEOUT_S = _env_float("LORA_ACK_TIMEOUT_S", 2.0)

# Dev/test only: force the simulated radio to "fail" this fraction of
# sends, to exercise the retry/backlog path without real hardware.
SIMULATE_FAIL_RATE = _env_float("SIMULATE_FAIL_RATE", 0.0)
