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

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workspace_id TEXT NOT NULL,

                file_path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,

                language TEXT NOT NULL,

                kind TEXT NOT NULL,

                name TEXT NOT NULL,
                qualified_name TEXT NOT NULL,

                parent_symbol TEXT,

                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,

                start_column INTEGER NOT NULL,
                end_column INTEGER NOT NULL,

                signature TEXT,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS file_parse_status (
                workspace_id TEXT NOT NULL,

                file_path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,

                language TEXT NOT NULL,

                parse_ok INTEGER NOT NULL,

                error_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,

                parsed_at TEXT NOT NULL,

                PRIMARY KEY(workspace_id, file_path),

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_symbols_workspace_name
            ON code_symbols(workspace_id, name)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_symbols_workspace_kind
            ON code_symbols(workspace_id, kind)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_symbols_workspace_file
            ON code_symbols(workspace_id, file_path)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workspace_id TEXT NOT NULL,

                file_path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,

                language TEXT NOT NULL,

                kind TEXT NOT NULL,

                module TEXT NOT NULL,

                imported_names TEXT NOT NULL DEFAULT '[]',

                is_relative INTEGER NOT NULL DEFAULT 0,

                resolved_file_path TEXT,

                resolution_status TEXT NOT NULL,

                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,

                raw_text TEXT,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_imports_workspace_file
            ON code_imports(
                workspace_id,
                file_path
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_imports_workspace_module
            ON code_imports(
                workspace_id,
                module
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_imports_resolved_file
            ON code_imports(
                workspace_id,
                resolved_file_path
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workspace_id TEXT NOT NULL,

                file_path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,

                language TEXT NOT NULL,

                caller_symbol TEXT,
                caller_class TEXT,

                callee_text TEXT NOT NULL,
                call_kind TEXT NOT NULL,

                resolved_file_path TEXT,
                resolved_symbol TEXT,
                resolved_symbol_kind TEXT,

                resolution_status TEXT NOT NULL,
                resolution_method TEXT,
                confidence TEXT,

                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_calls_workspace_file
            ON code_calls(
                workspace_id,
                file_path
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_calls_caller
            ON code_calls(
                workspace_id,
                caller_symbol
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_calls_resolved_symbol
            ON code_calls(
                workspace_id,
                resolved_symbol
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_calls_resolved_file
            ON code_calls(
                workspace_id,
                resolved_file_path
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workspace_id TEXT NOT NULL,

                file_path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,

                language TEXT NOT NULL,

                source_symbol TEXT NOT NULL,
                source_kind TEXT NOT NULL,

                relation_type TEXT NOT NULL,

                target_text TEXT NOT NULL,

                resolved_file_path TEXT,
                resolved_symbol TEXT,
                resolved_symbol_kind TEXT,

                resolution_status TEXT NOT NULL,
                resolution_method TEXT,
                confidence TEXT,

                start_line INTEGER NOT NULL,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_relations_source
            ON code_relations(
                workspace_id,
                source_symbol
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_relations_target
            ON code_relations(
                workspace_id,
                resolved_symbol
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_relations_type
            ON code_relations(
                workspace_id,
                relation_type
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_index_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                workspace_id TEXT NOT NULL,

                status TEXT NOT NULL,

                started_at TEXT NOT NULL,
                completed_at TEXT,

                error_message TEXT,

                scan_files INTEGER NOT NULL DEFAULT 0,
                symbols INTEGER NOT NULL DEFAULT 0,
                imports INTEGER NOT NULL DEFAULT 0,
                relations INTEGER NOT NULL DEFAULT 0,
                calls INTEGER NOT NULL DEFAULT 0,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_workspace_index_runs_workspace
            ON workspace_index_runs(
                workspace_id,
                started_at
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS repository_maps (
                workspace_id TEXT PRIMARY KEY,

                generated_at TEXT NOT NULL,

                map_json TEXT NOT NULL,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_chunks (
                chunk_id TEXT PRIMARY KEY,

                workspace_id TEXT NOT NULL,

                file_path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,

                language TEXT NOT NULL,

                symbol_name TEXT,
                symbol_kind TEXT,

                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,

                content_hash TEXT NOT NULL,

                content TEXT NOT NULL,

                created_at TEXT NOT NULL,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_chunks_workspace
            ON code_chunks(
                workspace_id
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_chunks_file
            ON code_chunks(
                workspace_id,
                file_path
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_code_chunks_symbol
            ON code_chunks(
                workspace_id,
                symbol_name
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS
            semantic_index_status (
                workspace_id TEXT PRIMARY KEY,

                model_name TEXT NOT NULL,

                chunks INTEGER NOT NULL,
                vector_dimension INTEGER NOT NULL,

                indexed_at TEXT NOT NULL,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS patch_runs (
                patch_id TEXT PRIMARY KEY,

                workspace_id TEXT NOT NULL,

                task TEXT NOT NULL,

                status TEXT NOT NULL,

                sandbox_path TEXT NOT NULL,

                summary TEXT,

                diff_text TEXT,

                files_changed TEXT,

                validation_json TEXT,

                error_message TEXT,

                created_at TEXT NOT NULL,
                completed_at TEXT,

                FOREIGN KEY(workspace_id)
                    REFERENCES workspaces(id)
                    ON DELETE CASCADE
            )
            """
        )

        patch_columns = {
            row[1]

            for row in connection.execute(
                """
                PRAGMA table_info(
                    patch_runs
                )
                """
            ).fetchall()
        }

        if "base_commit" not in patch_columns:

            connection.execute(
                """
                ALTER TABLE patch_runs
                ADD COLUMN base_commit TEXT
                """
            )

        if "decision_at" not in patch_columns:

            connection.execute(
                """
                ALTER TABLE patch_runs
                ADD COLUMN decision_at TEXT
                """
            )

        if "applied_at" not in patch_columns:

            connection.execute(
                """
                ALTER TABLE patch_runs
                ADD COLUMN applied_at TEXT
                """
            )

        if "diff_sha256" not in patch_columns:

            connection.execute(
                """
                ALTER TABLE patch_runs
                ADD COLUMN diff_sha256 TEXT
                """
            )    
        if "stale_at" not in patch_columns:

            connection.execute(
                """
                ALTER TABLE patch_runs
                ADD COLUMN stale_at TEXT
                """
            )

        if "cleanup_at" not in patch_columns:

            connection.execute(
                """
                ALTER TABLE patch_runs
                ADD COLUMN cleanup_at TEXT
                """
            )
            
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_patch_runs_workspace
            ON patch_runs(
                workspace_id,
                created_at
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
