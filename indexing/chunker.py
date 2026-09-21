import hashlib

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from storage.database import (
    get_database,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


CALLABLE_KINDS = {
    "function",
    "method",
}


TYPE_KINDS = {
    "class",
    "interface",
    "trait",
    "enum",
    "type_alias",
}


MAX_CALLABLE_LINES = 160

MAX_TYPE_LINES = 50

FALLBACK_WINDOW_LINES = 120

FALLBACK_OVERLAP_LINES = 20


def _content_hash(
    content: str,
) -> str:

    return hashlib.sha256(
        content.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def _chunk_id(
    workspace_id: str,

    file_path: str,

    symbol_name: str | None,

    start_line: int,

    end_line: int,

    content_hash: str,
) -> str:

    raw = (
        f"{workspace_id}|"
        f"{file_path}|"
        f"{symbol_name or ''}|"
        f"{start_line}|"
        f"{end_line}|"
        f"{content_hash}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _slice_lines(
    lines: list[str],

    start_line: int,

    end_line: int,
) -> str:

    start_index = max(
        0,
        start_line - 1,
    )

    end_index = min(
        len(lines),
        end_line,
    )

    return "".join(
        lines[
            start_index:end_index
        ]
    ).strip()


def _make_chunk(
    workspace_id: str,

    file_path: str,
    file_sha256: str,

    language: str,

    symbol_name: str | None,
    symbol_kind: str | None,

    start_line: int,
    end_line: int,

    content: str,

    created_at: str,
):

    content = content.strip()

    if not content:
        return None

    hash_value = _content_hash(
        content
    )

    return {
        "chunk_id": _chunk_id(
            workspace_id=workspace_id,

            file_path=file_path,

            symbol_name=symbol_name,

            start_line=start_line,

            end_line=end_line,

            content_hash=hash_value,
        ),

        "workspace_id": (
            workspace_id
        ),

        "file_path": file_path,

        "file_sha256": (
            file_sha256
        ),

        "language": language,

        "symbol_name": (
            symbol_name
        ),

        "symbol_kind": (
            symbol_kind
        ),

        "start_line": (
            start_line
        ),

        "end_line": (
            end_line
        ),

        "content_hash": (
            hash_value
        ),

        "content": content,

        "created_at": (
            created_at
        ),
    }


def build_code_chunks(
    workspace_id: str,
) -> list[dict]:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    root_path = Path(
        workspace.path
    ).resolve()

    with get_database() as database:

        files = database.execute(
            """
            SELECT
                path,
                language,
                sha256

            FROM repository_files

            WHERE workspace_id = ?
              AND is_source = 1

            ORDER BY path
            """,
            (workspace_id,),
        ).fetchall()

        symbols = database.execute(
            """
            SELECT
                file_path,
                kind,
                qualified_name,
                start_line,
                end_line

            FROM code_symbols

            WHERE workspace_id = ?

            ORDER BY
                file_path,
                start_line,
                end_line
            """,
            (workspace_id,),
        ).fetchall()

    symbols_by_file = {}

    for symbol in symbols:

        symbols_by_file.setdefault(
            symbol["file_path"],
            [],
        ).append(
            symbol
        )

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    chunks = []

    for file_row in files:

        file_path = file_row[
            "path"
        ]

        absolute_path = (
            root_path / file_path
        ).resolve()

        try:

            absolute_path.relative_to(
                root_path
            )

        except ValueError:

            continue

        try:

            source = (
                absolute_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            )

        except OSError:

            continue

        lines = source.splitlines(
            keepends=True
        )

        file_symbols = (
            symbols_by_file.get(
                file_path,
                [],
            )
        )

        useful_symbols = [
            symbol

            for symbol in file_symbols

            if symbol["kind"]
            in (
                CALLABLE_KINDS
                | TYPE_KINDS
            )
        ]

        #
        # Syntax-aware symbol chunks.
        #
        if useful_symbols:

            for symbol in useful_symbols:

                original_start = (
                    symbol[
                        "start_line"
                    ]
                )

                original_end = (
                    symbol[
                        "end_line"
                    ]
                )

                if (
                    symbol["kind"]
                    in CALLABLE_KINDS
                ):

                    max_lines = (
                        MAX_CALLABLE_LINES
                    )

                else:

                    max_lines = (
                        MAX_TYPE_LINES
                    )

                end_line = min(
                    original_end,

                    original_start
                    + max_lines
                    - 1,
                )

                content = _slice_lines(
                    lines=lines,

                    start_line=(
                        original_start
                    ),

                    end_line=end_line,
                )

                chunk = _make_chunk(
                    workspace_id=(
                        workspace_id
                    ),

                    file_path=file_path,

                    file_sha256=(
                        file_row[
                            "sha256"
                        ]
                    ),

                    language=(
                        file_row[
                            "language"
                        ]
                    ),

                    symbol_name=(
                        symbol[
                            "qualified_name"
                        ]
                    ),

                    symbol_kind=(
                        symbol[
                            "kind"
                        ]
                    ),

                    start_line=(
                        original_start
                    ),

                    end_line=(
                        end_line
                    ),

                    content=content,

                    created_at=(
                        created_at
                    ),
                )

                if chunk:

                    chunks.append(
                        chunk
                    )

        #
        # Files containing no useful
        # symbols still need semantic
        # coverage.
        #
        else:

            total_lines = len(
                lines
            )

            if total_lines == 0:
                continue

            step = (
                FALLBACK_WINDOW_LINES
                -
                FALLBACK_OVERLAP_LINES
            )

            start_line = 1

            while (
                start_line
                <= total_lines
            ):

                end_line = min(
                    total_lines,

                    start_line
                    + FALLBACK_WINDOW_LINES
                    - 1,
                )

                content = _slice_lines(
                    lines=lines,

                    start_line=(
                        start_line
                    ),

                    end_line=(
                        end_line
                    ),
                )

                chunk = _make_chunk(
                    workspace_id=(
                        workspace_id
                    ),

                    file_path=file_path,

                    file_sha256=(
                        file_row[
                            "sha256"
                        ]
                    ),

                    language=(
                        file_row[
                            "language"
                        ]
                    ),

                    symbol_name=None,

                    symbol_kind=(
                        "file_chunk"
                    ),

                    start_line=(
                        start_line
                    ),

                    end_line=(
                        end_line
                    ),

                    content=content,

                    created_at=(
                        created_at
                    ),
                )

                if chunk:

                    chunks.append(
                        chunk
                    )

                if end_line >= total_lines:
                    break

                start_line += step

    with get_database() as database:

        database.execute(
            """
            DELETE FROM code_chunks
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )

        database.executemany(
            """
            INSERT INTO code_chunks (
                chunk_id,
                workspace_id,
                file_path,
                file_sha256,
                language,
                symbol_name,
                symbol_kind,
                start_line,
                end_line,
                content_hash,
                content,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            [
                (
                    chunk[
                        "chunk_id"
                    ],

                    chunk[
                        "workspace_id"
                    ],

                    chunk[
                        "file_path"
                    ],

                    chunk[
                        "file_sha256"
                    ],

                    chunk[
                        "language"
                    ],

                    chunk[
                        "symbol_name"
                    ],

                    chunk[
                        "symbol_kind"
                    ],

                    chunk[
                        "start_line"
                    ],

                    chunk[
                        "end_line"
                    ],

                    chunk[
                        "content_hash"
                    ],

                    chunk[
                        "content"
                    ],

                    chunk[
                        "created_at"
                    ],
                )

                for chunk in chunks
            ],
        )

    return chunks
