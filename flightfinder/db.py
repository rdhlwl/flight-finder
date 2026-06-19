import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, UTC

DB_PATH = Path(__file__).resolve().parent.parent / "flights.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT,
    price REAL,
    outbound_departure_time TEXT,
    outbound_arrival_time TEXT,
    duration_minutes INTEGER,
    match_type TEXT NOT NULL DEFAULT 'exact',
    search_label TEXT,
    scanned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scans_route_dates
    ON scans (origin, destination, depart_date, return_date);
CREATE INDEX IF NOT EXISTS idx_scans_price ON scans (price);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    return conn


def _ensure_columns(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(scans)")}
    for col, decl in (("outbound_arrival_time", "TEXT"), ("duration_minutes", "INTEGER")):
        if col not in existing:
            conn.execute(f"ALTER TABLE scans ADD COLUMN {col} {decl}")
    conn.commit()


def get_cached(origin, destination, depart_date, return_date, max_age_hours):
    conn = get_conn()
    cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
    row = conn.execute(
        """SELECT * FROM scans WHERE origin=? AND destination=? AND depart_date=?
           AND (return_date=? OR (return_date IS NULL AND ? IS NULL))
           AND scanned_at >= ? ORDER BY scanned_at DESC LIMIT 1""",
        (origin, destination, depart_date, return_date, return_date, cutoff),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_scan(origin, destination, depart_date, return_date, price,
                 outbound_departure_time, outbound_arrival_time, duration_minutes,
                 match_type, search_label):
    conn = get_conn()
    conn.execute(
        """INSERT INTO scans (origin, destination, depart_date, return_date, price,
           outbound_departure_time, outbound_arrival_time, duration_minutes,
           match_type, search_label, scanned_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (origin, destination, depart_date, return_date, price,
         outbound_departure_time, outbound_arrival_time, duration_minutes,
         match_type, search_label, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    conn.close()


def best_deals(limit=100, origin_codes=None, destination_codes=None, min_price=None):
    conn = get_conn()
    query = """
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY origin, destination, depart_date, return_date
                ORDER BY price ASC
            ) AS rn
            FROM scans
            WHERE price IS NOT NULL
    """
    params = []
    if origin_codes:
        query += f" AND origin IN ({','.join('?' * len(origin_codes))})"
        params += list(origin_codes)
    if destination_codes:
        query += f" AND destination IN ({','.join('?' * len(destination_codes))})"
        params += list(destination_codes)
    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)
    query += """
        ) WHERE rn = 1
        ORDER BY price ASC LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
