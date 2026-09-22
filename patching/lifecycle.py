import json

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from patching.worktree import (
    get_head_commit,
    remove_worktree,
)

from storage.database import (
    get_database,
)

from workspace.manager import (
    get_workspace,
)


ACTIVE_PATCH_STATUSES = {
    "generating",
    "ready",
    "validation_failed",
}


FINAL_PATCH_STATUSES = {
    "applied",
    "rejected",
    "failed",
    "stale",
}


def _now() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def _loads_json(
    value,
    default,
):

    if not value:

        return default

    try:

        return json.loads(
            value
        )

    except (
        TypeError,
        json.JSONDecodeError,
    ):

        return default


def patch_row_to_dict(
    row,
) -> dict:

    sandbox_path = (
        row["sandbox_path"]
        or ""
    )

    sandbox_exists = False

    if sandbox_path:

        sandbox_exists = Path(
            sandbox_path
        ).exists()

    return {
        "patch_id": (
            row["patch_id"]
        ),

        "workspace_id": (
            row["workspace_id"]
        ),

        "task": row["task"],

        "status": row["status"],

        "summary": (
            row["summary"]
            or ""
        ),

        "files_changed": (
            _loads_json(
                row["files_changed"],
                [],
            )
        ),

        "validation": (
            _loads_json(
                row["validation_json"],
                [],
            )
        ),

        "base_commit": (
            row["base_commit"]
        ),

        "sandbox_path": (
            sandbox_path
        ),

        "sandbox_exists": (
            sandbox_exists
        ),

        "created_at": (
            row["created_at"]
        ),

        "completed_at": (
            row["completed_at"]
        ),

        "decision_at": (
            row["decision_at"]
        ),

        "applied_at": (
            row["applied_at"]
        ),

        "stale_at": (
            row["stale_at"]
        ),

        "cleanup_at": (
            row["cleanup_at"]
        ),
    }


def list_workspace_patches(
    workspace_id: str,
    limit: int = 50,
) -> list[dict]:

    limit = max(
        1,
        min(
            limit,
            200,
        ),
    )

    with get_database() as database:

        rows = database.execute(
            """
            SELECT *
            FROM patch_runs

            WHERE workspace_id = ?

            ORDER BY
                created_at DESC

            LIMIT ?
            """,
            (
                workspace_id,
                limit,
            ),
        ).fetchall()

    return [
        patch_row_to_dict(
            row
        )
        for row in rows
    ]


def reconcile_patch(
    patch_id: str,
) -> dict:

    with get_database() as database:

        row = database.execute(
            """
            SELECT *
            FROM patch_runs

            WHERE patch_id = ?
            """,
            (
                patch_id,
            ),
        ).fetchone()

    if row is None:

        raise RuntimeError(
            "Patch not found."
        )

    status = row[
        "status"
    ]

    #
    # Final patches do not become stale.
    #
    if status in FINAL_PATCH_STATUSES:

        return patch_row_to_dict(
            row
        )

    workspace = get_workspace(
        row["workspace_id"]
    )

    if workspace is None:

        raise RuntimeError(
            "Workspace not found."
        )

    repo_path = Path(
        workspace.path
    ).resolve()

    current_head = (
        get_head_commit(
            repo_path
        )
    )

    base_commit = row[
        "base_commit"
    ]

    #
    # Ready patches are tied to a
    # specific repository commit.
    #
    if (
        status == "ready"
        and base_commit
        and current_head
        != base_commit
    ):

        stale_at = _now()

        with get_database() as database:

            database.execute(
                """
                UPDATE patch_runs

                SET
                    status = ?,
                    stale_at = ?

                WHERE patch_id = ?
                  AND status = ?
                """,
                (
                    "stale",
                    stale_at,
                    patch_id,
                    "ready",
                ),
            )

        with get_database() as database:

            row = database.execute(
                """
                SELECT *
                FROM patch_runs
                WHERE patch_id = ?
                """,
                (
                    patch_id,
                ),
            ).fetchone()

    return patch_row_to_dict(
        row
    )


def reconcile_workspace_patches(
    workspace_id: str,
) -> list[dict]:

    with get_database() as database:

        rows = database.execute(
            """
            SELECT patch_id

            FROM patch_runs

            WHERE workspace_id = ?
              AND status IN (
                    'generating',
                    'ready',
                    'validation_failed'
              )

            ORDER BY created_at DESC
            """,
            (
                workspace_id,
            ),
        ).fetchall()

    results = []

    for row in rows:

        results.append(
            reconcile_patch(
                row["patch_id"]
            )
        )

    return results


def cleanup_patch(
    patch_id: str,
) -> dict:

    with get_database() as database:

        row = database.execute(
            """
            SELECT *
            FROM patch_runs

            WHERE patch_id = ?
            """,
            (
                patch_id,
            ),
        ).fetchone()

    if row is None:

        raise RuntimeError(
            "Patch not found."
        )

    #
    # Never destroy the sandbox of a
    # patch that is still being generated.
    #
    if row["status"] == "generating":

        raise RuntimeError(
            "Cannot clean a patch while "
            "it is still generating."
        )

    workspace = get_workspace(
        row["workspace_id"]
    )

    if workspace is None:

        raise RuntimeError(
            "Workspace not found."
        )

    repo_path = Path(
        workspace.path
    ).resolve()

    sandbox_value = (
        row["sandbox_path"]
        or ""
    )

    if sandbox_value:

        sandbox = Path(
            sandbox_value
        ).resolve()

        if sandbox.exists():

            remove_worktree(
                repo_path=repo_path,
                sandbox=sandbox,
            )

    cleanup_at = _now()

    with get_database() as database:

        database.execute(
            """
            UPDATE patch_runs

            SET cleanup_at = ?

            WHERE patch_id = ?
            """,
            (
                cleanup_at,
                patch_id,
            ),
        )

        row = database.execute(
            """
            SELECT *
            FROM patch_runs

            WHERE patch_id = ?
            """,
            (
                patch_id,
            ),
        ).fetchone()

    return patch_row_to_dict(
        row
    )
