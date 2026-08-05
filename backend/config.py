"""Env-driven configuration for backend. Overridable via env vars / .env
(see deploy/.env.example)."""
import os
from pathlib import Path


def _env_str(name, default):
    return os.environ.get(name, default)


def _env_float(name, default):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else default


HTTP_HOST = _env_str("BACKEND_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("BACKEND_PORT", "8000"))

SENSOR_SERVICE_URL = _env_str("SENSOR_SERVICE_URL", "http://localhost:8100")

# How often the backend polls sensor-service and pushes to connected
# browsers over /ws.
WS_PUSH_INTERVAL_S = _env_float("WS_PUSH_INTERVAL_S", 1.0)

# If the last successful poll of sensor-service is older than this, /api
# and /ws responses are flagged "stale": true so the UI can show a clear
# disconnected state instead of silently showing old numbers.
STALE_AFTER_S = _env_float("STALE_AFTER_S", 8.0)

LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")

_BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = Path(_env_str("FRONTEND_DIST", str(_BASE_DIR.parent / "frontend" / "dist")))
CONFIG_PATH = Path(_env_str("BACKEND_CONFIG_PATH", str(_BASE_DIR / "data" / "config.json")))
