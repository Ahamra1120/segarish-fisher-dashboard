"""backend: serves the built frontend, proxies /api/* to sensor-service,
and pushes live readings to the browser over /ws.

Deliberately a separate process from sensor-service (see README.md) — it
polls sensor-service over HTTP rather than touching hardware itself, so a
sensor-service hiccup/restart just makes this show "stale" data instead
of crashing the UI.

Run (dev, from this directory):  uvicorn app:app --port 8000 --reload
"""
import asyncio
import json
import logging
import time
from typing import Set

import httpx
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("backend")

app = FastAPI(title="segarish-fisher backend")

_client = httpx.AsyncClient(base_url=config.SENSOR_SERVICE_URL, timeout=5.0)

_cache = {"data": None, "fetched_at": 0.0, "connected": False}
_ws_clients: Set[WebSocket] = set()


def _is_stale():
    if not _cache["fetched_at"]:
        return True
    return (time.time() - _cache["fetched_at"]) > config.STALE_AFTER_S


def _envelope():
    return {
        "connected": _cache["connected"],
        "stale": _is_stale(),
        "fetched_at": _cache["fetched_at"],
        "data": _cache["data"],
    }


async def _broadcast():
    if not _ws_clients:
        return
    msg = json.dumps(_envelope())
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


async def _poll_loop():
    while True:
        try:
            resp = await _client.get("/latest")
            resp.raise_for_status()
            _cache["data"] = resp.json()
            _cache["fetched_at"] = time.time()
            _cache["connected"] = True
        except Exception as e:  # noqa: BLE001
            _cache["connected"] = False
            log.warning("poll sensor-service failed: %s", e)
        await _broadcast()
        await asyncio.sleep(config.WS_PUSH_INTERVAL_S)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_poll_loop())


@app.on_event("shutdown")
async def _shutdown():
    await _client.aclose()


# --- proxy + live data ----------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "connected": _cache["connected"],
        "stale": _is_stale(),
        "sensor_service_url": config.SENSOR_SERVICE_URL,
        "ws_clients": len(_ws_clients),
    }


@app.get("/api/latest")
async def latest():
    return _envelope()


@app.get("/api/history")
async def history(sensor: str, minutes: int = 30):
    try:
        resp = await _client.get("/history", params={"sensor": sensor, "minutes": minutes})
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/camera/snapshot.jpg")
async def snapshot():
    try:
        resp = await _client.get("/camera/snapshot.jpg")
        return Response(content=resp.content, media_type="image/jpeg", status_code=resp.status_code)
    except Exception as e:  # noqa: BLE001
        return Response(content=str(e).encode(), status_code=502)


@app.get("/api/camera/stream.mjpg")
async def stream():
    async def gen():
        async with _client.stream("GET", "/camera/stream.mjpg") as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=segarishframe")


@app.post("/api/load/tare")
async def tare():
    try:
        resp = await _client.post("/load/tare")
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps(_envelope()))
        while True:
            await ws.receive_text()  # client sends nothing meaningful; just await disconnect
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


# --- runtime-tunable UI config (thresholds, capacity) --------------------
# Distinct from sensor-service's hardware .env config: this is small,
# user-facing config the fisher/admin can change from the UI without a
# redeploy (e.g. gas warning threshold, load cell capacity for the % bar).
_DEFAULT_CONFIG = {
    "gas_warn_ppm": 400,
    "gas_danger_ppm": 1000,
    "load_capacity_kg": 50,
}


def _load_config_file():
    if config.CONFIG_PATH.exists():
        try:
            return {**_DEFAULT_CONFIG, **json.loads(config.CONFIG_PATH.read_text())}
        except Exception:  # noqa: BLE001
            log.exception("failed to read config file, using defaults")
    return dict(_DEFAULT_CONFIG)


def _save_config_file(payload):
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged = {**_load_config_file(), **payload}
    config.CONFIG_PATH.write_text(json.dumps(merged, indent=2))
    return merged


@app.get("/api/config")
async def get_config():
    return _load_config_file()


@app.put("/api/config")
async def put_config(payload: dict = Body(...)):
    return _save_config_file(payload)


# --- serve the built frontend (must be mounted last -- catches all other paths) ---
if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="frontend")
else:
    log.warning("frontend build not found at %s -- run `npm run build` in frontend/", config.FRONTEND_DIST)
