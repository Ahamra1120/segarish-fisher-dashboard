"""SQLite persistence for sensor-service.

Two kinds of tables live in the same readings.db:

- Per-sensor *history* tables (gas_history, load_history, gps_history):
  high-resolution logs used to answer GET /history for the on-screen
  charts. Pruned periodically to HISTORY_RETENTION_MINUTES.

- uplink_queue: one row per combined reading sampled for LoRa uplink
  (much lower rate than the history tables). lora-uplink is the only
  other process that touches this table — it reads pending rows FIFO
  and flips their status to 'sent' once radio TX succeeds. Rows are
  never deleted just because the buffer is large; the WAL journal mode
  lets sensor-service (writer) and lora-uplink (reader/writer) share the
  file safely from two processes.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gas_history (
    ts REAL NOT NULL,
    raw_adc INTEGER,
    voltage REAL,
    ppm_est REAL,
    level TEXT
);
CREATE INDEX IF NOT EXISTS idx_gas_ts ON gas_history(ts);

CREATE TABLE IF NOT EXISTS load_history (
    ts REAL NOT NULL,
    raw INTEGER,
    kg REAL
);
CREATE INDEX IF NOT EXISTS idx_load_ts ON load_history(ts);

CREATE TABLE IF NOT EXISTS gps_history (
    ts REAL NOT NULL,
    fix INTEGER,
    lat REAL,
    lon REAL,
    alt_m REAL,
    speed_kn REAL,
    heading_deg REAL,
    satellites INTEGER,
    hdop REAL
);
CREATE INDEX IF NOT EXISTS idx_gps_ts ON gps_history(ts);

CREATE TABLE IF NOT EXISTS uplink_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    seq INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    sent_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_uplink_status ON uplink_queue(status, id);
"""

_db_path = None


def init_db(path):
    global _db_path
    _db_path = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _connect() as con:
        con.executescript(_SCHEMA)


@contextmanager
def _connect():
    con = sqlite3.connect(_db_path, timeout=10.0)
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


# --- history writes -------------------------------------------------------

def insert_gas(r):
    with _connect() as con:
        con.execute(
            "INSERT INTO gas_history (ts, raw_adc, voltage, ppm_est, level) VALUES (?,?,?,?,?)",
            (r.ts, r.raw_adc, r.voltage, r.ppm_est, r.level),
        )


def insert_load(r):
    with _connect() as con:
        con.execute(
            "INSERT INTO load_history (ts, raw, kg) VALUES (?,?,?)",
            (r.ts, r.raw, r.kg),
        )


def insert_gps(r):
    with _connect() as con:
        con.execute(
            "INSERT INTO gps_history (ts, fix, lat, lon, alt_m, speed_kn, heading_deg, satellites, hdop) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (r.ts, int(r.fix), r.lat, r.lon, r.alt_m, r.speed_kn, r.heading_deg, r.satellites, r.hdop),
        )


_HISTORY_TABLES = {"gas": "gas_history", "load": "load_history", "gps": "gps_history"}


def query_history(sensor, minutes):
    table = _HISTORY_TABLES.get(sensor)
    if table is None:
        raise ValueError(f"unknown sensor '{sensor}', expected one of {list(_HISTORY_TABLES)}")
    since = time.time() - minutes * 60
    with _connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(f"SELECT * FROM {table} WHERE ts >= ? ORDER BY ts ASC", (since,)).fetchall()
        return [dict(row) for row in rows]


def prune_history(retention_minutes):
    cutoff = time.time() - retention_minutes * 60
    with _connect() as con:
        for table in _HISTORY_TABLES.values():
            con.execute(f"DELETE FROM {table} WHERE ts < ?", (cutoff,))


# --- uplink queue -----------------------------------------------------------

def get_last_seq():
    with _connect() as con:
        row = con.execute("SELECT MAX(seq) FROM uplink_queue").fetchone()
        return row[0] or 0


def insert_uplink_row(ts, seq, payload_json):
    with _connect() as con:
        cur = con.execute(
            "INSERT INTO uplink_queue (ts, seq, payload_json) VALUES (?,?,?)",
            (ts, seq, payload_json),
        )
        return cur.lastrowid


def count_uplink_rows(status="pending"):
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) FROM uplink_queue WHERE status = ?", (status,)).fetchone()
        return row[0]


def evict_oldest_pending(keep_at_most):
    """Emergency-only safety net: if the pending backlog has grown past
    `keep_at_most` rows (default config is generous — tens of thousands,
    i.e. many days of outage), drop the oldest pending rows beyond that
    cap so disk usage stays bounded. Callers should log loudly whenever
    this actually removes anything, since it does mean data loss.
    """
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) FROM uplink_queue WHERE status = 'pending'").fetchone()
        pending = row[0]
        if pending <= keep_at_most:
            return 0
        to_remove = pending - keep_at_most
        con.execute(
            "DELETE FROM uplink_queue WHERE id IN ("
            "  SELECT id FROM uplink_queue WHERE status = 'pending' ORDER BY id ASC LIMIT ?"
            ")",
            (to_remove,),
        )
        return to_remove
