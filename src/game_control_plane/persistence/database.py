from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Small SQLite wrapper with numbered SQL migrations."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def migrate(self) -> None:
        migrations_dir = Path(__file__).parent / "migrations"
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row[0]
            for row in self.connection.execute("SELECT version FROM schema_migrations")
        }
        for migration in sorted(migrations_dir.glob("*.sql")):
            try:
                version = int(migration.name.split("_", 1)[0])
            except (ValueError, IndexError):
                continue
            if version in applied:
                continue
            sql = migration.read_text(encoding="utf-8")
            # executescript() otherwise commits implicitly before running the
            # migration. Put the schema change and its version marker in one
            # explicit transaction so an interrupted migration can be retried.
            script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                "INSERT INTO schema_migrations(version, applied_at) "
                f"VALUES ({version}, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));\n"
                "COMMIT;"
            )
            try:
                self.connection.executescript(script)
            except sqlite3.Error:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
