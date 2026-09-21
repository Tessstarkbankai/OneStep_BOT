import json

from collections import (
    Counter,
    defaultdict,
)

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from indexing.models import (
    DirectorySummary,
    ImportantFileSummary,
    KeySymbolSummary,
    RepositoryMap,
)

from storage.database import (
    get_database,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


ENTRYPOINT_NAMES = {
    "main.py",
    "app.py",
    "manage.py",

    "server.js",
    "server.ts",

    "index.js",
    "index.ts",

    "main.js",
    "main.ts",

    "app.js",
    "app.ts",

    "index.php",
}


SPECIAL_ENTRYPOINT_PATHS = {
    "public/index.php",
    "routes/web.php",
    "routes/api.php",
}


def _top_level_directory(
    file_path: str,
) -> str:

    path = Path(
        file_path
    )

    if len(path.parts) <= 1:
        return "."

    return path.parts[0]


def _detect_entrypoints(
    source_files: list[str],
) -> list[str]:

    results = []

    for file_path in source_files:

        path = Path(
            file_path
        )

        if (
            path.name.lower()
            in ENTRYPOINT_NAMES
        ):

            results.append(
                file_path
            )

            continue

        normalized = (
            file_path.replace(
                "\\",
                "/",
            )
        )

        if (
            normalized
            in SPECIAL_ENTRYPOINT_PATHS
        ):

            results.append(
                file_path
            )

    return sorted(
        set(results)
    )


def generate_repository_map(
    workspace_id: str,
) -> RepositoryMap:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    with get_database() as database:

        file_rows = database.execute(
            """
            SELECT
                path,
                language,
                is_source
            FROM repository_files
            WHERE workspace_id = ?
            ORDER BY path
            """,
            (workspace_id,),
        ).fetchall()

        symbol_rows = database.execute(
            """
            SELECT
                file_path,
                kind,
                name,
                qualified_name
            FROM code_symbols
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()

        import_rows = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path,
                resolution_status
            FROM code_imports
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()

        call_rows = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path,
                resolved_symbol,
                resolution_status
            FROM code_calls
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()

        relation_rows = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path,
                resolved_symbol,
                resolution_status
            FROM code_relations
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()

    source_rows = [
        row
        for row in file_rows
        if bool(
            row["is_source"]
        )
    ]

    source_paths = [
        row["path"]
        for row in source_rows
    ]

    #
    # Languages
    #
    languages = Counter()

    for row in source_rows:

        languages[
            row["language"]
        ] += 1

    #
    # Symbols per file
    #
    symbols_per_file = Counter()

    for row in symbol_rows:

        symbols_per_file[
            row["file_path"]
        ] += 1

    #
    # Directory summaries
    #
    directory_files = Counter()
    directory_symbols = Counter()

    for row in source_rows:

        directory = (
            _top_level_directory(
                row["path"]
            )
        )

        directory_files[
            directory
        ] += 1

        directory_symbols[
            directory
        ] += (
            symbols_per_file[
                row["path"]
            ]
        )

    directories = [
        DirectorySummary(
            path=directory,

            source_files=(
                directory_files[
                    directory
                ]
            ),

            symbols=(
                directory_symbols[
                    directory
                ]
            ),
        )

        for directory in (
            directory_files
        )
    ]

    directories.sort(
        key=lambda item: (
            -item.source_files,
            item.path,
        )
    )

    #
    # File dependency counts
    #
    outgoing_dependencies = Counter()
    incoming_dependencies = Counter()

    resolved_local_imports = 0

    for row in import_rows:

        resolved = (
            row[
                "resolved_file_path"
            ]
        )

        if not resolved:
            continue

        resolved_local_imports += 1

        outgoing_dependencies[
            row["file_path"]
        ] += 1

        incoming_dependencies[
            resolved
        ] += 1

    #
    # Call counts
    #
    outgoing_calls = Counter()
    incoming_calls = Counter()

    resolved_calls = 0

    incoming_symbol_calls = Counter()

    for row in call_rows:

        if (
            row[
                "resolution_status"
            ]
            != "local"
        ):
            continue

        resolved_calls += 1

        outgoing_calls[
            row["file_path"]
        ] += 1

        resolved_file = (
            row[
                "resolved_file_path"
            ]
        )

        resolved_symbol = (
            row[
                "resolved_symbol"
            ]
        )

        if resolved_file:

            incoming_calls[
                resolved_file
            ] += 1

        if (
            resolved_file
            and resolved_symbol
        ):

            incoming_symbol_calls[
                (
                    resolved_file,
                    resolved_symbol,
                )
            ] += 1

    #
    # Relation counts
    #
    resolved_relations = 0

    incoming_symbol_relations = (
        Counter()
    )

    for row in relation_rows:

        if (
            row[
                "resolution_status"
            ]
            != "local"
        ):
            continue

        resolved_relations += 1

        if (
            row[
                "resolved_file_path"
            ]
            and row[
                "resolved_symbol"
            ]
        ):

            incoming_symbol_relations[
                (
                    row[
                        "resolved_file_path"
                    ],
                    row[
                        "resolved_symbol"
                    ],
                )
            ] += 1

    #
    # Important files
    #
    important_files = []

    for row in source_rows:

        file_path = row[
            "path"
        ]

        symbol_count = (
            symbols_per_file[
                file_path
            ]
        )

        incoming_dep = (
            incoming_dependencies[
                file_path
            ]
        )

        outgoing_dep = (
            outgoing_dependencies[
                file_path
            ]
        )

        calls_in = (
            incoming_calls[
                file_path
            ]
        )

        calls_out = (
            outgoing_calls[
                file_path
            ]
        )

        #
        # Simple deterministic scoring.
        #
        # No LLM involved.
        #
        score = (
            symbol_count
            + incoming_dep * 3
            + outgoing_dep
            + calls_in * 3
            + calls_out
        )

        important_files.append(
            ImportantFileSummary(
                path=file_path,

                language=row[
                    "language"
                ],

                symbols=symbol_count,

                incoming_dependencies=(
                    incoming_dep
                ),

                outgoing_dependencies=(
                    outgoing_dep
                ),

                incoming_calls=(
                    calls_in
                ),

                outgoing_calls=(
                    calls_out
                ),

                importance_score=score,
            )
        )

    important_files.sort(
        key=lambda item: (
            -item.importance_score,
            item.path,
        )
    )

    important_files = (
        important_files[:25]
    )

    #
    # Important symbols
    #
    key_symbols = []

    for row in symbol_rows:

        symbol_key = (
            row["file_path"],
            row[
                "qualified_name"
            ],
        )

        call_count = (
            incoming_symbol_calls[
                symbol_key
            ]
        )

        relation_count = (
            incoming_symbol_relations[
                symbol_key
            ]
        )

        kind_bonus = 0

        if row["kind"] == "class":
            kind_bonus = 3

        elif row["kind"] in {
            "interface",
            "trait",
        }:
            kind_bonus = 2

        elif row["kind"] in {
            "function",
            "method",
        }:
            kind_bonus = 1

        score = (
            call_count * 5
            + relation_count * 4
            + kind_bonus
        )

        key_symbols.append(
            KeySymbolSummary(
                name=row["name"],

                qualified_name=row[
                    "qualified_name"
                ],

                kind=row["kind"],

                file_path=row[
                    "file_path"
                ],

                incoming_calls=(
                    call_count
                ),

                incoming_relations=(
                    relation_count
                ),

                importance_score=score,
            )
        )

    key_symbols.sort(
        key=lambda item: (
            -item.importance_score,
            item.qualified_name,
        )
    )

    key_symbols = (
        key_symbols[:30]
    )

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    repository_map = RepositoryMap(
        workspace_id=workspace.id,

        workspace_name=workspace.name,

        generated_at=generated_at,

        total_files=len(
            file_rows
        ),

        source_files=len(
            source_rows
        ),

        languages=dict(
            languages.most_common()
        ),

        symbols=len(
            symbol_rows
        ),

        imports=len(
            import_rows
        ),

        resolved_local_imports=(
            resolved_local_imports
        ),

        calls=len(
            call_rows
        ),

        resolved_calls=(
            resolved_calls
        ),

        relations=len(
            relation_rows
        ),

        resolved_relations=(
            resolved_relations
        ),

        entry_points=(
            _detect_entrypoints(
                source_paths
            )
        ),

        directories=directories,

        important_files=(
            important_files
        ),

        key_symbols=(
            key_symbols
        ),
    )

    with get_database() as database:

        database.execute(
            """
            INSERT INTO repository_maps (
                workspace_id,
                generated_at,
                map_json
            )
            VALUES (?, ?, ?)

            ON CONFLICT(workspace_id)
            DO UPDATE SET
                generated_at =
                    excluded.generated_at,

                map_json =
                    excluded.map_json
            """,
            (
                workspace_id,

                generated_at,

                repository_map
                .model_dump_json(),
            ),
        )

    return repository_map


def get_repository_map(
    workspace_id: str,
) -> RepositoryMap | None:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    with get_database() as database:

        row = database.execute(
            """
            SELECT map_json
            FROM repository_maps
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchone()

    if row is None:
        return None

    return RepositoryMap.model_validate_json(
        row["map_json"]
    )
