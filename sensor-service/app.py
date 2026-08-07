"""sensor-service: polls sensor hardware (or simulated fallback) on
background threads, logs history to SQLite, and exposes it all over a
local-only HTTP API for the backend to consume.

Run (dev, from this directory):  uvicorn app:app --port 8100 --reload
"""
import json
import logging
import threading
import time
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

import config
import storage
from drivers import simulate
from drivers.base import GasReading, GpsReading, LoadReading
from drivers.camera import CameraDriver
from drivers.gps import GpsDriver
from drivers.loadcell import HX711Driver
from drivers.mq135 import MQ135Driver

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sensor-service")

storage.init_db(config.DB_PATH)


def _pick(real_cls, sim_cls, name):
    """Real hardware driver if SENSOR_MODE allows it and it initializes
    OK; simulated fallback otherwise. SENSOR_MODE=hardware disables the
    fallback (a failed driver just reports unavailable)."""
    if config.SENSOR_MODE == "simulate":
        log.info("%s: SENSOR_MODE=simulate -> using simulated driver", name)
        return sim_cls(config)
    if config.SENSOR_MODE == "manual":
        log.info("%s: SENSOR_MODE=manual -> no driver, waiting for POST /manual", name)
        return _UnavailableDriver()
    try:
        drv = real_cls(config)
    except Exception as e:  # noqa: BLE001
        log.warning("%s: real driver raised on init (%s)", name, e)
        drv = None
    if drv is not None and drv.available:
        log.info("%s: using real hardware driver", name)
        return drv
    if config.SENSOR_MODE == "hardware":
        log.warning("%s: hardware unavailable and SENSOR_MODE=hardware -> no fallback", name)
        return drv if drv is not None else _UnavailableDriver()
    log.warning("%s: hardware unavailable -> falling back to simulated driver", name)
    return sim_cls(config)


class _UnavailableDriver:
    """Used only when SENSOR_MODE=hardware forbids the simulate fallback
    and the real driver failed to construct at all."""

    available = False

    def read(self):
        raise RuntimeError("sensor unavailable (SENSOR_MODE=hardware, no driver)")


gas_driver = _pick(MQ135Driver, simulate.SimGasDriver, "mq135")
load_driver = _pick(HX711Driver, simulate.SimLoadDriver, "loadcell")
gps_driver = _pick(GpsDriver, simulate.SimGpsDriver, "gps")
camera_driver = _pick(CameraDriver, simulate.SimCameraDriver, "camera")

# --- shared state, updated by the poll threads below, read by the API ----
_lock = threading.Lock()
_state = {"gas": None, "load": None, "gps": None, "camera_ts": None}
_started_at = time.time()

_seq_lock = threading.Lock()
_seq = storage.get_last_seq()  # resume the uplink sequence counter across restarts

_last_frame = {"bytes": None, "ts": 0.0}

_stop = threading.Event()


def _next_seq():
    global _seq
    with _seq_lock:
        _seq += 1
        return _seq


def gas_loop():
    while not _stop.is_set():
        try:
            r = gas_driver.read()
            with _lock:
                _state["gas"] = r
            storage.insert_gas(r)
        except Exception:  # noqa: BLE001
            log.exception("gas_loop error")
        _stop.wait(config.GAS_POLL_INTERVAL_S)


def load_loop():
    while not _stop.is_set():
        try:
            r = load_driver.read()
            with _lock:
                _state["load"] = r
            storage.insert_load(r)
        except Exception:  # noqa: BLE001
            log.exception("load_loop error")
        _stop.wait(config.LOAD_POLL_INTERVAL_S)


def gps_loop():
    while not _stop.is_set():
        try:
            r = gps_driver.read()
            with _lock:
                _state["gps"] = r
            storage.insert_gps(r)
        except Exception:  # noqa: BLE001
            log.exception("gps_loop error")
        _stop.wait(config.GPS_POLL_INTERVAL_S)


def camera_loop():
    while not _stop.is_set():
        try:
            jpeg = camera_driver.capture_jpeg_bytes()
            _last_frame["bytes"] = jpeg
            _last_frame["ts"] = time.time()
            with _lock:
                _state["camera_ts"] = _last_frame["ts"]
        except Exception:  # noqa: BLE001
            log.exception("camera_loop error")
        _stop.wait(config.CAMERA_SNAPSHOT_INTERVAL_S)


def build_uplink_payload(seq, snap):
    """Compact, self-describing JSON — short keys, rounded precision, so
    a future LoRa gateway/admin dashboard can decode it without needing a
    pre-shared binary schema. Kept in sync conceptually with
    lora-uplink/payload.py, which is the module that actually transmits it."""
    gas, load, gps = snap.get("gas"), snap.get("load"), snap.get("gps")
    return {
        "id": config.NODE_ID,
        "seq": seq,
        "ts": int(time.time()),
        "gas": gas.ppm_est if gas else None,
        "gaslvl": gas.level if gas else None,
        "w": load.kg if load else None,
        "lat": round(gps.lat, 5) if gps and gps.lat is not None else None,
        "lon": round(gps.lon, 5) if gps and gps.lon is not None else None,
        "hdg": round(gps.heading_deg, 1) if gps and gps.heading_deg is not None else None,
        "spd": round(gps.speed_kn, 1) if gps and gps.speed_kn is not None else None,
        "fix": bool(gps.fix) if gps else False,
        "sat": gps.satellites if gps else None,
    }


def uplink_sampler_loop():
    while not _stop.is_set():
        _stop.wait(config.UPLINK_SAMPLE_INTERVAL_S)
        with _lock:
            snap = dict(_state)
        if snap["gas"] is None and snap["load"] is None and snap["gps"] is None:
            continue  # nothing sampled yet
        seq = _next_seq()
        payload = build_uplink_payload(seq, snap)
        storage.insert_uplink_row(time.time(), seq, json.dumps(payload, separators=(",", ":")))


def housekeeping_loop():
    while not _stop.is_set():
        _stop.wait(3600)
        try:
            storage.prune_history(config.HISTORY_RETENTION_MINUTES)
        except Exception:  # noqa: BLE001
            log.exception("housekeeping_loop error")


# SENSOR_MODE=manual runs with no pollers at all -- state only changes
# when POST /manual is called, so gas/load/gps/camera/uplink-sampler loops
# would just spin reading from _UnavailableDriver stubs for nothing.
# housekeeping still runs (harmless, keeps history pruned regardless).
_threads = [threading.Thread(target=housekeeping_loop, daemon=True, name="housekeeping_loop")]
if config.SENSOR_MODE != "manual":
    _threads += [
        threading.Thread(target=gas_loop, daemon=True, name="gas_loop"),
        threading.Thread(target=load_loop, daemon=True, name="load_loop"),
        threading.Thread(target=gps_loop, daemon=True, name="gps_loop"),
        threading.Thread(target=camera_loop, daemon=True, name="camera_loop"),
        threading.Thread(target=uplink_sampler_loop, daemon=True, name="uplink_sampler_loop"),
    ]
for t in _threads:
    t.start()


app = FastAPI(title="segarish-fisher sensor-service")


@app.get("/health")
def health():
    return {
        "ok": True,
        "uptime_s": round(time.time() - _started_at, 1),
        "mode": config.SENSOR_MODE,
        "node_id": config.NODE_ID,
        "drivers": {
            "gas": {"class": gas_driver.__class__.__name__, "available": gas_driver.available},
            "load": {"class": load_driver.__class__.__name__, "available": load_driver.available},
            "gps": {"class": gps_driver.__class__.__name__, "available": gps_driver.available},
            "camera": {"class": camera_driver.__class__.__name__, "available": camera_driver.available},
        },
        "uplink_pending": storage.count_uplink_rows("pending"),
    }


@app.get("/latest")
def latest():
    with _lock:
        gas, load, gps, cam_ts = _state["gas"], _state["load"], _state["gps"], _state["camera_ts"]
    return {
        "ts": time.time(),
        "gas": asdict(gas) if gas else None,
        "load": asdict(load) if load else None,
        "gps": asdict(gps) if gps else None,
        "camera": {"last_capture_ts": cam_ts, "available": camera_driver.available},
    }


@app.get("/history")
def history(sensor: str, minutes: int = 30):
    try:
        return storage.query_history(sensor, minutes)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/camera/snapshot.jpg")
def snapshot():
    jpeg = _last_frame["bytes"]
    if not jpeg:
        return Response(content=b"no frame captured yet", status_code=503)
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/camera/stream.mjpg")
def stream():
    boundary = "segarishframe"

    def gen():
        while True:
            jpeg = _last_frame["bytes"]
            if jpeg:
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            time.sleep(max(0.2, config.CAMERA_SNAPSHOT_INTERVAL_S / 2))

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}")


@app.post("/load/tare")
def tare():
    if not hasattr(load_driver, "tare"):
        return JSONResponse({"ok": False, "reason": "driver has no tare()"}, status_code=400)
    offset = load_driver.tare()
    return {"ok": True, "offset": offset}


# --- manual input (SENSOR_MODE=manual) ------------------------------------
# Same field names/units as the compact LoRa uplink payload (see README
# "LoRa uplink" and "Manual input") -- what you POST here is, verbatim,
# what gets queued for lora-uplink to send. Every field is optional so a
# single POST can update just gas, just the load cell, just GPS, or all
# three; at least one sensor's worth of data is required.
class ManualReading(BaseModel):
    id: Optional[str] = None
    seq: Optional[int] = None
    ts: Optional[int] = None
    gas: Optional[float] = None
    gaslvl: Optional[str] = None
    w: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    hdg: Optional[float] = None
    spd: Optional[float] = None
    fix: Optional[bool] = None
    sat: Optional[int] = None


@app.post("/manual")
def manual_ingest(reading: ManualReading):
    if config.SENSOR_MODE != "manual":
        return JSONResponse(
            {
                "ok": False,
                "error": "SENSOR_MODE is not 'manual' -- set SENSOR_MODE=manual and "
                "restart sensor-service to accept POST /manual instead of simulate/hardware readings.",
            },
            status_code=409,
        )

    now = time.time()
    ts = float(reading.ts) if reading.ts is not None else now

    gas_r = load_r = gps_r = None

    if reading.gas is not None or reading.gaslvl is not None:
        gas_r = GasReading(ts=ts, raw_adc=None, voltage=None, rs_ratio=None, ppm_est=reading.gas, level=reading.gaslvl or "unknown")
        with _lock:
            _state["gas"] = gas_r
        storage.insert_gas(gas_r)

    if reading.w is not None:
        load_r = LoadReading(ts=ts, raw=None, kg=reading.w, tared=True)
        with _lock:
            _state["load"] = load_r
        storage.insert_load(load_r)

    if reading.fix is not None or any(v is not None for v in (reading.lat, reading.lon, reading.hdg, reading.spd, reading.sat)):
        gps_r = GpsReading(
            ts=ts, fix=bool(reading.fix), lat=reading.lat, lon=reading.lon, alt_m=None,
            speed_kn=reading.spd, heading_deg=reading.hdg, heading_source="manual",
            satellites=reading.sat, hdop=None,
        )
        with _lock:
            _state["gps"] = gps_r
        storage.insert_gps(gps_r)

    if gas_r is None and load_r is None and gps_r is None:
        return JSONResponse(
            {"ok": False, "error": "empty reading -- provide at least one of gas/gaslvl, w, or lat/lon/hdg/spd/fix/sat"},
            status_code=400,
        )

    seq = reading.seq if reading.seq is not None else _next_seq()
    payload = {
        "id": reading.id or config.NODE_ID,
        "seq": seq,
        "ts": int(ts),
        "gas": gas_r.ppm_est if gas_r else None,
        "gaslvl": gas_r.level if gas_r else None,
        "w": load_r.kg if load_r else None,
        "lat": round(gps_r.lat, 5) if gps_r and gps_r.lat is not None else None,
        "lon": round(gps_r.lon, 5) if gps_r and gps_r.lon is not None else None,
        "hdg": round(gps_r.heading_deg, 1) if gps_r and gps_r.heading_deg is not None else None,
        "spd": round(gps_r.speed_kn, 1) if gps_r and gps_r.speed_kn is not None else None,
        "fix": bool(gps_r.fix) if gps_r else False,
        "sat": gps_r.satellites if gps_r else None,
    }
    # Queued directly, right now -- unlike simulate/hardware mode (which
    # samples _state on a timer via uplink_sampler_loop), a manual POST
    # *is* the snapshot to send, so it goes straight into uplink_queue for
    # lora-uplink to pick up FIFO.
    storage.insert_uplink_row(now, seq, json.dumps(payload, separators=(",", ":")))
    return {"ok": True, "queued_for_lora": payload}
