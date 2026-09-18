import sqlite3
from contextlib import contextmanager
from typing import Generator

from app.config import DATABASE_PATH, ensure_directories


def initialize_database() -> None:
    ensure_directories()

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                is_git_repo INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS repository_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workspace_id TEXT NOT NULL,

                path TEXT NOT NULL,

                extension TEXT,

                language TEXT NOT NULL,

                size_bytes INTEGER NOT NULL,

                sha256 TEXT NOT NULL,

                is_source INTEGER NOT NULL DEFAULT 0,

                scanned_at TEXT NOT NULL,

                UNIQUE(workspace_id, path),

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_scans (
                workspace_id TEXT PRIMARY KEY,

                scanned_at TEXT NOT NULL,

                scan_method TEXT NOT NULL,

                total_candidates INTEGER NOT NULL,

                indexed_files INTEGER NOT NULL,

                source_files INTEGER NOT NULL,

                other_text_files INTEGER NOT NULL,

                skipped_binary INTEGER NOT NULL,

                skipped_large INTEGER NOT NULL,

                skipped_sensitive INTEGER NOT NULL,

                total_indexed_bytes INTEGER NOT NULL,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.commit()


@contextmanager
def get_database() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()

    finally:
        connection.close()
