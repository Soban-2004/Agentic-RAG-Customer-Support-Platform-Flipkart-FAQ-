"""
Mock backend for the MCP tools (src/tools/mcp_server.py).

A small SQLite database standing in for Flipkart's real order/refund/support
systems -- gives the agent something real to look up instead of a canned
"not available" string, without needing any actual backend integration.
init_db() is idempotent (safe to call on every server start) and seeds a
handful of demo records on first run.

order_notes is this project's long-term memory: unlike src/memory/persistent_memory.py
(scoped to one browser session), notes are anchored to an order ID and persist
across *any* conversation that mentions that order -- the closest thing to
"remembers this customer" available without a real auth/identity system.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mock_backend.db"

SEED_ORDERS = [
    # order_id, item_name, status, eta
    ("FK1001", "Wireless Bluetooth Headphones", "Out for Delivery", "2026-07-22"),
    ("FK1002", "Smartphone Case", "Delivered", "2026-07-15"),
    ("FK1003", "Running Shoes", "Shipped", "2026-07-25"),
    ("FK1004", "Laptop Stand", "Processing", "2026-07-28"),
]

SEED_REFUNDS = [
    # refund_id, order_id, status, amount
    ("RF2001", "FK1002", "Refund Completed", 899.00),
    ("RF2002", "FK1003", "Refund Approved - Processing", 1499.00),
]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                item_name TEXT NOT NULL,
                status TEXT NOT NULL,
                eta TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                status TEXT NOT NULL,
                amount REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS escalations (
                ticket_id TEXT PRIMARY KEY,
                order_id TEXT,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        if conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO orders (order_id, item_name, status, eta) VALUES (?, ?, ?, ?)",
                SEED_ORDERS,
            )
        if conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO refunds (refund_id, order_id, status, amount) VALUES (?, ?, ?, ?)",
                SEED_REFUNDS,
            )
        conn.commit()
    finally:
        conn.close()


def get_order(order_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_refund(refund_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM refunds WHERE refund_id = ?", (refund_id.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_escalation(summary: str, order_id: Optional[str] = None) -> dict:
    ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO escalations (ticket_id, order_id, summary, created_at, status) "
            "VALUES (?, ?, ?, ?, 'open')",
            (ticket_id, order_id, summary, created_at),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ticket_id": ticket_id,
        "order_id": order_id,
        "summary": summary,
        "created_at": created_at,
        "status": "open",
    }


def get_notes(order_id: str) -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT note FROM order_notes WHERE order_id = ? ORDER BY id ASC",
            (order_id.strip().upper(),),
        ).fetchall()
        return [row["note"] for row in rows]
    finally:
        conn.close()


def add_note(order_id: str, note: str) -> dict:
    order_id = order_id.strip().upper()
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO order_notes (order_id, note, created_at) VALUES (?, ?, ?)",
            (order_id, note, created_at),
        )
        conn.commit()
    finally:
        conn.close()
    return {"order_id": order_id, "note": note, "created_at": created_at}
