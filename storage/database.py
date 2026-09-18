import sqlite3
from contextlib import contextmanager
from typing import Generator

from app.config import DATABASE_PATH, ensure_directories


def initialize_database() -> None:
    ensure_directories()

    with sqlite3.connect(DATABASE_PATH) as connection:
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

        connection.commit()


@contextmanager
def get_database() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(DATABASE_PATH)

    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    finally:
        connection.close()

