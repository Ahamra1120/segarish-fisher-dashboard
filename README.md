# Segarish Fisher Dashboard

On-device dashboard for a fishing vessel: MQ135 (air/gas quality), a load
cell, GPS, and an IMX135 camera feed into a Raspberry Pi, shown live on a
7" TFT touchscreen — and the same readings are queued for LoRa uplink to
a future admin dashboard, buffered on-device until they actually send.
**Everything runs on the Pi. No internet, no CDN, no external service.**

```
[MQ135→MCP3008] [HX711+load cell] [Sologood M10 GPS] [IMX135 camera]
          \             |                |                 /
           \            |                |                /
            v           v                v               v
      ┌───────────────────────────────────────────────────────┐
      │  sensor-service  (FastAPI, :8100)                       │
      │  polls every sensor, keeps a rolling SQLite log          │
      │  (readings.db) -- both a per-sensor history for charts    │
      │  and a downsampled uplink_queue for LoRa.                  │
      └───────────────────────────────────────────────────────┘
                │ HTTP (localhost)              │ shared SQLite
                v                                v
      ┌───────────────────────────┐   ┌───────────────────────────────┐
      │  backend (FastAPI, :8000)  │   │  lora-uplink (daemon)           │
      │  serves the built frontend, │   │  drains uplink_queue FIFO,       │
      │  proxies /api/* to :8100,   │   │  sends over SX1276/RFM95 (SPI),   │
      │  pushes live data over /ws  │   │  retries forever until it sends.   │
      └───────────────────────────┘   └───────────────────────────────────┘
                │ WS + HTTP (local)                    │ 923 MHz LoRa
                v                                       v
      ┌───────────────────────────┐        (future) admin dashboard
      │ Chromium --kiosk, 7" TFT   │        gateway -- not built here;
      │ React SPA                  │        this project is sender-only.
      └───────────────────────────┘
```

Four independent processes, each its own systemd unit:

- **sensor-service** is the only thing that talks to hardware; it owns `readings.db`.
- **backend** and **lora-uplink** are both *consumers* of that data for two
  different destinations (the on-screen display vs. the remote admin
  dashboard). Neither depends on the other being healthy: a sensor-service
  restart makes backend show a "stale" badge instead of crashing, and
  lora-uplink just finds nothing new to send.
- **frontend** is a static React build the backend serves — no separate
  frontend server in production.

## Repo layout

```
sensor-service/   Python, FastAPI :8100 -- hardware drivers + SQLite + API
backend/          Python, FastAPI :8000 -- static frontend + /api proxy + /ws
lora-uplink/      Python daemon -- drains uplink_queue over LoRa (SX1276/RFM95)
frontend/         React + Vite -- the kiosk UI (builds to frontend/dist)
deploy/           systemd units, kiosk autostart, .env.example
```

## Dev setup (any OS, no hardware needed)

Every driver — gas, load cell, GPS, camera, and the LoRa radio — falls
back automatically to a simulated version when its hardware library
can't be imported (e.g. developing on Windows/Mac/a non-Pi Linux box),
mirroring the same mean-reverting random walk the sibling `segarish`
project uses client-side. So the whole stack runs anywhere:

```bash
# 1. sensor-service (simulated sensors)
cd sensor-service
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
SENSOR_MODE=simulate uvicorn app:app --port 8100

# 2. backend (in another terminal)
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app:app --port 8000

# 3. lora-uplink (in another terminal, optional for UI dev)
cd lora-uplink
LORA_MODE=simulate python app.py

# 4. frontend
cd frontend
npm install
npm run build      # backend serves frontend/dist at http://localhost:8000
# or: npm run dev   # Vite dev server on :5173, proxies /api and /ws to :8000
```

Open `http://localhost:8000`. You should see live-updating panels within
a couple of seconds; killing sensor-service should flip the header badge
to "Terputus" (disconnected) while the panels keep showing last-known
values instead of going blank.

Force the LoRa retry path without hardware:
`SIMULATE_FAIL_RATE=1.0 LORA_MODE=simulate python app.py` in `lora-uplink/`
— rows will stay `pending` and keep retrying; drop the flag and they drain.

## Raspberry Pi bring-up

1. **Enable interfaces** — `sudo raspi-config` → *Interface Options*:
   enable **SPI** (MQ135/MCP3008, LoRa radio), **I2C** (if you later add a
   magnetometer), **Serial Port** (hardware UART for GPS, *not* the login
   shell over serial), and the **Camera**.
2. **System packages the Pi needs beyond pip:**
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 python3-libcamera chromium-browser
   ```
   `picamera2` wraps `libcamera` and is **not pip-installable** — create
   `sensor-service`'s venv with `--system-site-packages` so it can see the
   apt-installed package:
   ```bash
   cd sensor-service
   python3 -m venv --system-site-packages .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   pip install spidev RPi.GPIO pyserial pynmea2   # hardware drivers (see requirements.txt notes)
   ```
   `backend`'s venv is plain (`python3 -m venv .venv`) — it has no hardware deps.
   `lora-uplink`'s venv also wants `--system-site-packages`:
   ```bash
   cd lora-uplink
   python3 -m venv --system-site-packages .venv
   . .venv/bin/activate
   pip install adafruit-blinka adafruit-circuitpython-rfm9x
   ```
3. **Wiring** (BCM numbering; confirm against your actual boards' silkscreen):

   | Sensor | Interface | Pins (default in `deploy/.env.example`) |
   |---|---|---|
   | MQ135 → MCP3008 | SPI0 | MCP3008 on SPI0 CE0; MQ135 analog out → MCP3008 CH0 |
   | HX711 load cell | bit-banged GPIO | DOUT → GPIO5, SCK → GPIO6 |
   | Sologood M10 GPS | UART | module TX → Pi RXD (GPIO15), module RX → Pi TXD (GPIO14) |
   | IMX135 camera | CSI ribbon | CSI connector |
   | SX1276/RFM95 LoRa | SPI0 (2nd device) or SPI1 | CS → GPIO25 (`D25`), RESET → GPIO22 (`D22`), plus shared SCK/MOSI/MISO |

4. **Calibrate before trusting readings:**
   - **MQ135**: burn the sensor in powered for 24-48h, then in clean
     outdoor air measure/compute R0 and set `MQ135_R0_KOHM` in `.env` —
     until then, `sensor-service` deliberately reports gas level as
     "unknown" rather than a made-up number.
   - **HX711**: zero it (`POST /api/load/tare`, or the dashboard's "Tare /
     Nol" button) with nothing on the scale, then place a known weight
     and solve for `HX711_SCALE` (counts-per-kg) in `.env`.
5. **Copy env config:** `cp deploy/.env.example deploy/.env` and fill in
   the calibration values above plus `LORA_FREQ_MHZ` (see below).
6. **Install the systemd units:**
   ```bash
   sudo cp deploy/*.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now sensor-service backend lora-uplink
   ```
7. **Kiosk autostart:** copy `deploy/kiosk-autostart.desktop` to
   `~/.config/autostart/segarish-kiosk.desktop` on the auto-login desktop
   account (`chmod +x deploy/kiosk.sh` first). See the comments in that
   file for the labwc/Wayland fallback if your Pi OS image doesn't honor
   XDG autostart.
8. **Sanity-check each sensor** once running: `curl localhost:8100/health`
   shows which drivers are real vs. simulated; `voltage` on the gas panel
   should sit mid-range with the sensor warmed up; the load reading
   should zero after tare; the GPS panel should get a fix outdoors within
   a couple of minutes; the camera panel should show a real frame, not
   the "SIMULATED CAMERA" placeholder.

None of the hardware driver code (steps 1-4 above) has been run against
real hardware by the author — it follows datasheet/library conventions
and was verified end-to-end in simulate mode only (no Pi/sensors were
available during development). Budget time for wiring debugging on first
bring-up.

## LoRa uplink

`lora-uplink` is **sender-only** — there is no admin-dashboard gateway
yet. It drains `sensor-service`'s `uplink_queue` table (in the shared
`readings.db`) oldest-first and transmits each row as a compact,
self-describing JSON payload:

```json
{"id":"fisher-01","seq":42,"ts":1893456000,"gas":386.4,"gaslvl":"baik","w":4.62,"lat":-5.98034,"lon":106.75651,"hdg":36.2,"spd":3.8,"fix":true,"sat":10}
```

| key | meaning |
|---|---|
| `id` | node id (`NODE_ID` in `.env`) |
| `seq` | monotonically increasing per-node sequence number, survives restarts — lets a future gateway detect gaps/dedupe |
| `ts` | unix seconds |
| `gas` | MQ135 ppm estimate (null if uncalibrated) |
| `gaslvl` | `"baik"` / `"sedang"` / `"buruk"` / `"unknown"` |
| `w` | load cell weight, kg |
| `lat`, `lon` | degrees, 5 decimals (~1m precision) |
| `hdg` | heading in degrees, **from GPS course-over-ground, not a magnetometer** (see below) |
| `spd` | speed, knots |
| `fix` | GPS fix acquired |
| `sat` | satellite count |

**A row only ever gets marked `sent` after radio TX succeeds.** Anything
else — no gateway listening, boat out of range — leaves it `pending` and
`lora-uplink` retries in order, indefinitely (bounded only by
`BUFFER_CAP_ROWS`, a very generous safety net — see `.env.example`). No
delivery-ACK protocol exists yet since there's nothing to ACK with;
`LORA_WAIT_ACK=true` is there to flip on once a gateway that replies with
a short ack packet exists — the send loop already supports waiting for
one, it's just off by default.

**Frequency**: defaults to `923.0` MHz, targeting Indonesia's unlicensed
LPWAN allocation per Kominfo. **Confirm this against your actual gateway
and local regulations before field use** — many hobbyist SX1276/RFM95
boards are silkscreened 433/868/915 MHz, but the frequency is a
software-tunable radio parameter, not fixed by the board.

## No CDN, no map tiles — why

The sibling `segarish` project (a marketing/mock web platform) pulls
fonts from Google Fonts and map tiles from a Leaflet/unpkg CDN. This
project runs on a boat with no internet, so neither is an option: the
frontend uses the system font stack, and GPS position is shown as
numeric lat/lon + a custom SVG compass rose instead of a map with tile
imagery. Visual identity (brand color, card system, status colors) is
still ported from `segarish/src/index.css` and `ui.jsx` — see comments
in `frontend/src/index.css` for the specifics.

## Heading is GPS, not a compass

The Sologood M10 is GNSS-only — no magnetometer — so `heading_deg`
everywhere in this project is course-over-ground from GPS, which is only
meaningful while actually moving at a few knots or more, and is labeled
"Arah dari GPS (course), bukan kompas magnetik" in the UI rather than
"Compass" so it isn't mistaken for one. `drivers/gps.py`'s
`heading_source` field and the driver interface in `drivers/base.py`
exist specifically so a real magnetometer (e.g. QMC5883L over I2C) can
be dropped in later without touching anything downstream.
