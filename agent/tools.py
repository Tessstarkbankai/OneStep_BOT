import json

from pathlib import Path

from retrieval.hybrid import (
    hybrid_retrieve,
)

from storage.database import (
    get_database,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


MAX_READ_LINES = 160


TOOL_DEFINITIONS = [
    {
        "type": "function",

        "function": {
            "name": "search_code",

            "description": (
                "Search the indexed repository "
                "for code relevant to a concept, "
                "feature, error, function, class, "
                "or developer question."
            ),

            "parameters": {
                "type": "object",

                "properties": {
                    "query": {
                        "type": "string",
                    },

                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 8,
                    },
                },

                "required": [
                    "query"
                ],
            },
        },
    },

    {
        "type": "function",

        "function": {
            "name": "read_code",

            "description": (
                "Read an exact line range from "
                "an approved indexed source file. "
                "Use this after locating a likely "
                "implementation."
            ),

            "parameters": {
                "type": "object",

                "properties": {
                    "file_path": {
                        "type": "string",
                    },

                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                    },

                    "end_line": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },

                "required": [
                    "file_path",
                    "start_line",
                    "end_line",
                ],
            },
        },
    },

    {
        "type": "function",

        "function": {
            "name": "find_symbol",

            "description": (
                "Find functions, methods, "
                "classes, interfaces, traits, "
                "or other indexed symbols by "
                "name."
            ),

            "parameters": {
                "type": "object",

                "properties": {
                    "name": {
                        "type": "string",
                    },

                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },

                "required": [
                    "name"
                ],
            },
        },
    },

    {
        "type": "function",

        "function": {
            "name": "find_callers",

            "description": (
                "Find code that calls a given "
                "resolved function or method."
            ),

            "parameters": {
                "type": "object",

                "properties": {
                    "symbol": {
                        "type": "string",
                    },

                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },

                "required": [
                    "symbol"
                ],
            },
        },
    },

    {
        "type": "function",

        "function": {
            "name": "find_callees",

            "description": (
                "Find functions or methods "
                "called by a given function "
                "or method."
            ),

            "parameters": {
                "type": "object",

                "properties": {
                    "symbol": {
                        "type": "string",
                    },

                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                },

                "required": [
                    "symbol"
                ],
            },
        },
    },
]


def _workspace(
    workspace_id: str,
):

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    return workspace


def _tool_search_code(
    workspace_id: str,

    query: str,

    limit: int = 5,

    use_semantic: bool = True,
):

    result = hybrid_retrieve(
        workspace_id=workspace_id,

        query=query,

        limit=min(
            max(limit, 1),
            8,
        ),

        expand_graph=True,

        use_semantic=(
            use_semantic
        ),
    )

    output = []

    for candidate in result.results:

        output.append(
            {
                "file_path": (
                    candidate.file_path
                ),

                "language": (
                    candidate.language
                ),

                "score": (
                    candidate.score
                ),

                "semantic_similarity": (
                    candidate
                    .semantic_similarity
                ),

                "symbols": [
                    {
                        "name": (
                            symbol.name
                        ),

                        "qualified_name": (
                            symbol
                            .qualified_name
                        ),

                        "kind": (
                            symbol.kind
                        ),

                        "start_line": (
                            symbol
                            .start_line
                        ),

                        "end_line": (
                            symbol
                            .end_line
                        ),
                    }

                    for symbol in (
                        candidate.symbols[
                            :5
                        ]
                    )
                ],

                "reasons": (
                    candidate.reasons[
                        :5
                    ]
                ),
            }
        )

    return {
        "query": query,

        "semantic_used": (
            result.semantic_used
        ),

        "results": output,
    }


def _tool_read_code(
    workspace_id: str,

    file_path: str,

    start_line: int,

    end_line: int,
):

    workspace = _workspace(
        workspace_id
    )

    with get_database() as database:

        row = database.execute(
            """
            SELECT
                path,
                language,
                is_source

            FROM repository_files

            WHERE workspace_id = ?
              AND path = ?
              AND is_source = 1
            """,
            (
                workspace_id,
                file_path,
            ),
        ).fetchone()

    if row is None:

        raise WorkspaceError(
            "File is not an approved "
            "indexed source file: "
            f"{file_path}"
        )

    root = Path(
        workspace.path
    ).resolve()

    absolute = (
        root / file_path
    ).resolve()

    try:

        absolute.relative_to(
            root
        )

    except ValueError:

        raise WorkspaceError(
            "Attempted to read outside "
            "workspace root."
        )

    start_line = max(
        1,
        int(start_line),
    )

    end_line = max(
        start_line,
        int(end_line),
    )

    end_line = min(
        end_line,

        start_line
        + MAX_READ_LINES
        - 1,
    )

    source = absolute.read_text(
        encoding="utf-8",
        errors="replace",
    )

    lines = source.splitlines()

    end_line = min(
        end_line,
        len(lines),
    )

    selected = lines[
        start_line - 1:
        end_line
    ]

    rendered = []

    for number, text in enumerate(
        selected,
        start=start_line,
    ):

        rendered.append(
            f"{number:>5} | {text}"
        )

    return {
        "file_path": file_path,

        "language": row[
            "language"
        ],

        "start_line": start_line,

        "end_line": end_line,

        "content": "\n".join(
            rendered
        ),
    }


def _tool_find_symbol(
    workspace_id: str,

    name: str,

    limit: int = 10,
):

    _workspace(
        workspace_id
    )

    limit = min(
        max(limit, 1),
        20,
    )

    pattern = (
        f"%{name.lower()}%"
    )

    with get_database() as database:

        rows = database.execute(
            """
            SELECT
                file_path,
                language,
                kind,
                name,
                qualified_name,
                start_line,
                end_line,
                signature

            FROM code_symbols

            WHERE workspace_id = ?
              AND (
                    LOWER(name) LIKE ?
                    OR
                    LOWER(qualified_name)
                        LIKE ?
              )

            ORDER BY
                CASE
                    WHEN LOWER(name)
                         = LOWER(?)
                    THEN 0

                    WHEN LOWER(
                        qualified_name
                    ) = LOWER(?)
                    THEN 0

                    ELSE 1
                END,

                file_path,
                start_line

            LIMIT ?
            """,
            (
                workspace_id,
                pattern,
                pattern,
                name,
                name,
                limit,
            ),
        ).fetchall()

    return {
        "query": name,

        "results": [
            dict(row)
            for row in rows
        ],
    }


def _tool_find_callers(
    workspace_id: str,

    symbol: str,

    limit: int = 10,
):

    _workspace(
        workspace_id
    )

    limit = min(
        max(limit, 1),
        20,
    )

    suffix = (
        f"%.{symbol.lower()}"
    )

    with get_database() as database:

        rows = database.execute(
            """
            SELECT
                file_path,
                caller_symbol,
                caller_class,
                callee_text,
                resolved_file_path,
                resolved_symbol,
                confidence,
                start_line,
                end_line

            FROM code_calls

            WHERE workspace_id = ?
              AND resolution_status
                  = 'local'
              AND (
                    LOWER(
                        resolved_symbol
                    ) = LOWER(?)

                    OR

                    LOWER(
                        resolved_symbol
                    ) LIKE ?
              )

            ORDER BY
                confidence DESC,
                file_path,
                start_line

            LIMIT ?
            """,
            (
                workspace_id,
                symbol,
                suffix,
                limit,
            ),
        ).fetchall()

    return {
        "symbol": symbol,

        "callers": [
            dict(row)
            for row in rows
        ],
    }


def _tool_find_callees(
    workspace_id: str,

    symbol: str,

    limit: int = 10,
):

    _workspace(
        workspace_id
    )

    limit = min(
        max(limit, 1),
        20,
    )

    suffix = (
        f"%.{symbol.lower()}"
    )

    with get_database() as database:

        rows = database.execute(
            """
            SELECT
                file_path,
                caller_symbol,
                callee_text,
                call_kind,
                resolved_file_path,
                resolved_symbol,
                resolved_symbol_kind,
                confidence,
                start_line,
                end_line

            FROM code_calls

            WHERE workspace_id = ?
              AND (
                    LOWER(
                        caller_symbol
                    ) = LOWER(?)

                    OR

                    LOWER(
                        caller_symbol
                    ) LIKE ?
              )

            ORDER BY
                CASE
                    WHEN resolution_status
                         = 'local'
                    THEN 0
                    ELSE 1
                END,

                file_path,
                start_line

            LIMIT ?
            """,
            (
                workspace_id,
                symbol,
                suffix,
                limit,
            ),
        ).fetchall()

    return {
        "symbol": symbol,

        "callees": [
            dict(row)
            for row in rows
        ],
    }


def execute_tool(
    workspace_id: str,

    tool_name: str,

    arguments: dict,

    use_semantic: bool = True,
):

    if tool_name == "search_code":

        return _tool_search_code(
            workspace_id=workspace_id,

            query=str(
                arguments.get(
                    "query",
                    "",
                )
            ),

            limit=int(
                arguments.get(
                    "limit",
                    5,
                )
            ),

            use_semantic=(
                use_semantic
            ),
        )

    if tool_name == "read_code":

        return _tool_read_code(
            workspace_id=workspace_id,

            file_path=str(
                arguments.get(
                    "file_path",
                    "",
                )
            ),

            start_line=int(
                arguments.get(
                    "start_line",
                    1,
                )
            ),

            end_line=int(
                arguments.get(
                    "end_line",
                    80,
                )
            ),
        )

    if tool_name == "find_symbol":

        return _tool_find_symbol(
            workspace_id=workspace_id,

            name=str(
                arguments.get(
                    "name",
                    "",
                )
            ),

            limit=int(
                arguments.get(
                    "limit",
                    10,
                )
            ),
        )

    if tool_name == "find_callers":

        return _tool_find_callers(
            workspace_id=workspace_id,

            symbol=str(
                arguments.get(
                    "symbol",
                    "",
                )
            ),

            limit=int(
                arguments.get(
                    "limit",
                    10,
                )
            ),
        )

    if tool_name == "find_callees":

        return _tool_find_callees(
            workspace_id=workspace_id,

            symbol=str(
                arguments.get(
                    "symbol",
                    "",
                )
            ),

            limit=int(
                arguments.get(
                    "limit",
                    10,
                )
            ),
        )

    raise RuntimeError(
        f"Unknown agent tool: "
        f"{tool_name}"
    )
