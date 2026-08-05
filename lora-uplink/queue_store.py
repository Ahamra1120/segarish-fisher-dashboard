"""Minimal SQLite access to the `uplink_queue` table sensor-service
maintains in readings.db.

This module only ever reads/writes `uplink_queue` — it never creates or
touches the per-sensor history tables (those are sensor-service's
territory; see sensor-service/storage.py, which is this schema's
source of truth). Keep the column list below in sync with it.
"""
import sqlite3
from contextlib import contextmanager

_db_path = None


def init_db(path):
    global _db_path
    _db_path = path
    # sensor-service normally creates this table first, but create it
    # here too (idempotent) in case lora-uplink starts before it, e.g. a
    # systemd ordering hiccup on boot.
    with _connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS uplink_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                seq INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                sent_ts REAL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_uplink_status ON uplink_queue(status, id)")


@contextmanager
def _connect():
    con = sqlite3.connect(_db_path, timeout=10.0)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def get_pending_rows(limit=200):
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM uplink_queue WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_sent(row_id, sent_ts):
    with _connect() as con:
        con.execute("UPDATE uplink_queue SET status = 'sent', sent_ts = ? WHERE id = ?", (sent_ts, row_id))


def mark_attempt(row_id):
    with _connect() as con:
        con.execute("UPDATE uplink_queue SET attempts = attempts + 1 WHERE id = ?", (row_id,))


def count_pending():
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM uplink_queue WHERE status = 'pending'").fetchone()
        return row["n"]


def evict_oldest_pending(keep_at_most):
    """Emergency-only safety net -- see config.BUFFER_CAP_ROWS. Returns
    how many rows were dropped so the caller can log it loudly."""
    with _connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM uplink_queue WHERE status = 'pending'").fetchone()
        pending = row["n"]
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
