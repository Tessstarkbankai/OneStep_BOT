from datetime import (
    datetime,
    timezone,
)

from indexing.call_graph import (
    build_call_graph,
)

from indexing.dependency_parser import (
    build_dependency_index,
)

from indexing.models import (
    IndexRunStatus,
    UnifiedIndexResult,
)

from indexing.relation_graph import (
    build_relation_graph,
)

from indexing.repo_map import (
    generate_repository_map,
)

from indexing.symbol_parser import (
    parse_workspace,
)

from storage.database import (
    get_database,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)

from workspace.scanner import (
    scan_workspace,
)


def run_full_index(
    workspace_id: str,
) -> UnifiedIndexResult:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    with get_database() as database:

        cursor = database.execute(
            """
            INSERT INTO workspace_index_runs (
                workspace_id,
                status,
                started_at
            )
            VALUES (?, ?, ?)
            """,
            (
                workspace_id,
                "running",
                started_at,
            ),
        )

        run_id = cursor.lastrowid

    try:

        #
        # STEP 1
        # Discover files.
        #
        scan_result = (
            scan_workspace(
                workspace_id
            )
        )

        #
        # STEP 2
        # Extract symbols.
        #
        parse_result = (
            parse_workspace(
                workspace_id
            )
        )

        #
        # STEP 3
        # Resolve imports.
        #
        dependency_result = (
            build_dependency_index(
                workspace_id
            )
        )

        #
        # STEP 4
        # Class/interface/trait graph.
        #
        relation_result = (
            build_relation_graph(
                workspace_id
            )
        )

        #
        # STEP 5
        # Function/method call graph.
        #
        call_result = (
            build_call_graph(
                workspace_id
            )
        )

        #
        # STEP 6
        # Compact architecture map.
        #
        repository_map = (
            generate_repository_map(
                workspace_id
            )
        )

        completed_at = datetime.now(
            timezone.utc
        ).isoformat()

        with get_database() as database:

            database.execute(
                """
                UPDATE workspace_index_runs

                SET
                    status = ?,
                    completed_at = ?,

                    scan_files = ?,
                    symbols = ?,
                    imports = ?,
                    relations = ?,
                    calls = ?

                WHERE id = ?
                """,
                (
                    "completed",

                    completed_at,

                    scan_result
                    .indexed_files,

                    parse_result
                    .symbols_extracted,

                    dependency_result
                    .total_imports,

                    relation_result
                    .total_relations,

                    call_result
                    .total_calls,

                    run_id,
                ),
            )

        return UnifiedIndexResult(
            workspace_id=(
                workspace.id
            ),

            workspace_name=(
                workspace.name
            ),

            status="completed",

            started_at=started_at,

            completed_at=(
                completed_at
            ),

            indexed_files=(
                scan_result
                .indexed_files
            ),

            symbols=(
                parse_result
                .symbols_extracted
            ),

            imports=(
                dependency_result
                .total_imports
            ),

            relations=(
                relation_result
                .total_relations
            ),

            calls=(
                call_result
                .total_calls
            ),

            repository_map=(
                repository_map
            ),
        )

    except Exception as error:

        completed_at = datetime.now(
            timezone.utc
        ).isoformat()

        with get_database() as database:

            database.execute(
                """
                UPDATE workspace_index_runs

                SET
                    status = ?,
                    completed_at = ?,
                    error_message = ?

                WHERE id = ?
                """,
                (
                    "failed",

                    completed_at,

                    str(error)[
                        :3000
                    ],

                    run_id,
                ),
            )

        raise


def get_latest_index_run(
    workspace_id: str,
) -> IndexRunStatus | None:

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
            SELECT
                id,
                workspace_id,
                status,
                started_at,
                completed_at,
                error_message,
                scan_files,
                symbols,
                imports,
                relations,
                calls

            FROM workspace_index_runs

            WHERE workspace_id = ?

            ORDER BY id DESC

            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()

    if row is None:
        return None

    return IndexRunStatus(
        id=row["id"],

        workspace_id=row[
            "workspace_id"
        ],

        status=row["status"],

        started_at=row[
            "started_at"
        ],

        completed_at=row[
            "completed_at"
        ],

        error_message=row[
            "error_message"
        ],

        scan_files=row[
            "scan_files"
        ],

        symbols=row[
            "symbols"
        ],

        imports=row[
            "imports"
        ],

        relations=row[
            "relations"
        ],

        calls=row[
            "calls"
        ],
    )
