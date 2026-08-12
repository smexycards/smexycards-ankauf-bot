from __future__ import annotations

import csv
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from config import BACKUP_DIR, DB_PATH, EXPORT_DIR


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def backup_database(destination: Path) -> Path:
    """Create a transaction-safe SQLite backup using SQLite's backup API."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = _connect(DB_PATH)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    return destination


def create_scheduled_backup(keep: int = 14) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"ankauf_{_stamp()}.sqlite3"
    backup_database(path)

    backups = sorted(BACKUP_DIR.glob("ankauf_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[max(1, keep):]:
        try:
            old.unlink()
        except OSError:
            pass
    return path


def latest_backup() -> Path | None:
    backups = sorted(BACKUP_DIR.glob("ankauf_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def _write_csv(path: Path, rows: Iterable[sqlite3.Row]) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def create_csv_export(guild_id: int) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    work_dir = EXPORT_DIR / f"export_{stamp}"
    work_dir.mkdir(parents=True, exist_ok=True)

    conn = _connect(DB_PATH)
    try:
        tickets = conn.execute(
            "SELECT * FROM tickets WHERE guild_id=? ORDER BY id ASC",
            (guild_id,),
        ).fetchall()
        offers = conn.execute(
            """
            SELECT o.*
            FROM offers o
            JOIN tickets t ON t.id=o.ticket_id
            WHERE t.guild_id=?
            ORDER BY o.id ASC
            """,
            (guild_id,),
        ).fetchall()
        settings = conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?",
            (guild_id,),
        ).fetchall()
    finally:
        conn.close()

    _write_csv(work_dir / "tickets.csv", tickets)
    _write_csv(work_dir / "offers.csv", offers)
    _write_csv(work_dir / "guild_settings.csv", settings)

    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "guild_id": guild_id,
        "ticket_count": len(tickets),
        "offer_count": len(offers),
        "notice": "Enthält Verkäufer-/Kontaktdaten. Vertraulich behandeln.",
    }
    (work_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    zip_path = EXPORT_DIR / f"smexycards_export_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in work_dir.iterdir():
            archive.write(item, arcname=item.name)

    for item in work_dir.iterdir():
        try:
            item.unlink()
        except OSError:
            pass
    try:
        work_dir.rmdir()
    except OSError:
        pass
    return zip_path


def create_backup_bundle(guild_id: int) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    sqlite_path = EXPORT_DIR / f"ankauf_backup_{stamp}.sqlite3"
    backup_database(sqlite_path)

    conn = _connect(sqlite_path)
    try:
        ticket_count = conn.execute("SELECT COUNT(*) FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()[0]
        offer_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM offers o JOIN tickets t ON t.id=o.ticket_id
            WHERE t.guild_id=?
            """,
            (guild_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    metadata_path = EXPORT_DIR / f"backup_metadata_{stamp}.json"
    metadata_path.write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "guild_id": guild_id,
                "ticket_count": ticket_count,
                "offer_count": offer_count,
                "database": sqlite_path.name,
                "notice": "Datenbank-Backup enthält Verkäufer-/Kontaktdaten. Vertraulich behandeln.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    zip_path = EXPORT_DIR / f"smexycards_backup_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(sqlite_path, arcname=sqlite_path.name)
        archive.write(metadata_path, arcname="metadata.json")

    for path in (sqlite_path, metadata_path):
        try:
            path.unlink()
        except OSError:
            pass
    return zip_path
