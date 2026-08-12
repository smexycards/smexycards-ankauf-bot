from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from config import DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                staff_role_id INTEGER NOT NULL,
                ticket_category_id INTEGER NOT NULL,
                archive_category_id INTEGER,
                log_channel_id INTEGER,
                panel_channel_id INTEGER,
                panel_message_id INTEGER,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER UNIQUE,
                owner_id INTEGER NOT NULL,
                owner_name TEXT NOT NULL,
                kind TEXT NOT NULL,
                details_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                agreed_price_cents INTEGER,
                payment_method TEXT,
                deal_description TEXT,
                seller_name TEXT,
                seller_street TEXT,
                seller_city TEXT,
                seller_contact TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                note TEXT,
                payment_method TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tickets_channel ON tickets(channel_id);
            CREATE INDEX IF NOT EXISTS idx_tickets_owner ON tickets(owner_id);
            CREATE INDEX IF NOT EXISTS idx_offers_ticket_status ON offers(ticket_id, status);
            """
        )


def save_guild_settings(
    guild_id: int,
    staff_role_id: int,
    ticket_category_id: int,
    archive_category_id: int | None,
    log_channel_id: int | None,
    panel_channel_id: int | None = None,
    panel_message_id: int | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO guild_settings (
                guild_id, staff_role_id, ticket_category_id, archive_category_id,
                log_channel_id, panel_channel_id, panel_message_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                staff_role_id=excluded.staff_role_id,
                ticket_category_id=excluded.ticket_category_id,
                archive_category_id=excluded.archive_category_id,
                log_channel_id=excluded.log_channel_id,
                panel_channel_id=COALESCE(excluded.panel_channel_id, guild_settings.panel_channel_id),
                panel_message_id=COALESCE(excluded.panel_message_id, guild_settings.panel_message_id),
                updated_at=excluded.updated_at
            """,
            (
                guild_id,
                staff_role_id,
                ticket_category_id,
                archive_category_id,
                log_channel_id,
                panel_channel_id,
                panel_message_id,
                _now(),
            ),
        )


def update_panel_message(guild_id: int, channel_id: int, message_id: int) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE guild_settings
            SET panel_channel_id=?, panel_message_id=?, updated_at=?
            WHERE guild_id=?
            """,
            (channel_id, message_id, _now(), guild_id),
        )


def get_guild_settings(guild_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)
        ).fetchone()
    return dict(row) if row else None


def create_ticket_placeholder(
    guild_id: int,
    owner_id: int,
    owner_name: str,
    kind: str,
    details: dict[str, Any],
) -> int:
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tickets (
                guild_id, owner_id, owner_name, kind, details_json,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (guild_id, owner_id, owner_name, kind, json.dumps(details, ensure_ascii=False), now, now),
        )
        return int(cur.lastrowid)


def bind_ticket_channel(ticket_id: int, channel_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE tickets SET channel_id=?, updated_at=? WHERE id=?",
            (channel_id, _now(), ticket_id),
        )


def delete_ticket(ticket_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))


def _ticket_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    data["details"] = json.loads(data.pop("details_json"))
    return data


def get_ticket(ticket_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    return _ticket_dict(row)


def get_ticket_by_channel(channel_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
        ).fetchone()
    return _ticket_dict(row)


def set_ticket_status(ticket_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE tickets SET status=?, updated_at=? WHERE id=?",
            (status, _now(), ticket_id),
        )


def set_deal(
    ticket_id: int,
    amount_cents: int,
    payment_method: str,
    description: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE tickets
            SET status='deal', agreed_price_cents=?, payment_method=?,
                deal_description=?, updated_at=?
            WHERE id=?
            """,
            (amount_cents, payment_method, description, _now(), ticket_id),
        )


def set_seller_data(
    ticket_id: int,
    seller_name: str,
    seller_street: str,
    seller_city: str,
    seller_contact: str,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE tickets
            SET seller_name=?, seller_street=?, seller_city=?, seller_contact=?,
                status='seller_data', updated_at=?
            WHERE id=?
            """,
            (seller_name, seller_street, seller_city, seller_contact, _now(), ticket_id),
        )


def create_offer(ticket_id: int, amount_cents: int, note: str, payment_method: str, created_by: int) -> int:
    now = _now()
    with connect() as conn:
        conn.execute(
            "UPDATE offers SET status='superseded', updated_at=? WHERE ticket_id=? AND status='pending'",
            (now, ticket_id),
        )
        cur = conn.execute(
            """
            INSERT INTO offers (ticket_id, amount_cents, note, payment_method, created_by, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (ticket_id, amount_cents, note, payment_method, created_by, now, now),
        )
        conn.execute(
            "UPDATE tickets SET status='offer_pending', updated_at=? WHERE id=?",
            (now, ticket_id),
        )
        return int(cur.lastrowid)


def get_latest_pending_offer(ticket_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM offers
            WHERE ticket_id=? AND status='pending'
            ORDER BY id DESC LIMIT 1
            """,
            (ticket_id,),
        ).fetchone()
    return dict(row) if row else None


def set_offer_status(offer_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE offers SET status=?, updated_at=? WHERE id=?",
            (status, _now(), offer_id),
        )


def get_dashboard_stats(guild_id: int) -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM tickets WHERE guild_id=? GROUP BY status",
            (guild_id,),
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        total = conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()[0]
        agreed = conn.execute(
            """
            SELECT COALESCE(SUM(agreed_price_cents), 0)
            FROM tickets
            WHERE guild_id=? AND agreed_price_cents IS NOT NULL AND status != 'declined'
            """,
            (guild_id,),
        ).fetchone()[0]

    active = sum(counts.get(status, 0) for status in ("open", "offer_pending", "deal", "seller_data", "shipping"))
    return {
        "total": int(total),
        "active": active,
        "open": counts.get("open", 0),
        "offer_pending": counts.get("offer_pending", 0),
        "deal": counts.get("deal", 0),
        "seller_data": counts.get("seller_data", 0),
        "shipping": counts.get("shipping", 0),
        "closed": counts.get("closed", 0),
        "declined": counts.get("declined", 0),
        "agreed_price_cents": int(agreed or 0),
    }


def list_recent_tickets(guild_id: int, limit: int = 12, active_only: bool = True) -> list[dict[str, Any]]:
    where = "guild_id=?"
    params: list[Any] = [guild_id]
    if active_only:
        where += " AND status NOT IN ('closed', 'declined')"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tickets WHERE {where} ORDER BY updated_at DESC, id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [_ticket_dict(row) for row in rows if row is not None]
