import json

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from patching.applier import (
    apply_edits,
)

from patching.generator import (
    generate_patch_plan,
)

from patching.models import (
    PatchResponse,
)

from patching.worktree import (
    changed_files,
    create_patch_worktree,
    get_diff,
)

from storage.database import (
    get_database,
)

from validation.patch_validator import (
    validate_patch,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


def create_patch(
    workspace_id: str,

    task: str,

    max_files: int = 3,

    use_semantic: bool = True,
) -> PatchResponse:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    repo_path = Path(
        workspace.path
    ).resolve()

    patch_id, sandbox = (
        create_patch_worktree(
            repo_path
        )
    )

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    with get_database() as database:

        database.execute(
            """
            INSERT INTO patch_runs (
                patch_id,
                workspace_id,
                task,
                status,
                sandbox_path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                patch_id,
                workspace_id,
                task,
                "generating",
                str(sandbox),
                created_at,
            ),
        )

    try:

        summary, edits, context = (
            generate_patch_plan(
                workspace_id=(
                    workspace_id
                ),

                task=task,

                max_files=max_files,

                use_semantic=(
                    use_semantic
                ),
            )
        )

        apply_edits(
            workspace_id=workspace_id,
            sandbox=sandbox,

            edits=edits,
        )

        files = changed_files(
            sandbox
        )

        if not files:

            raise RuntimeError(
                "Patch produced no Git changes."
            )

        diff = get_diff(
            sandbox
        )

        validation = (
            validate_patch(
                sandbox=sandbox,

                files=files,
            )
        )

        validation_passed = all(
            item.passed

            for item in validation
        )

        status = (
            "ready"
            if validation_passed
            else "validation_failed"
        )

        completed_at = datetime.now(
            timezone.utc
        ).isoformat()

        with get_database() as database:

            database.execute(
                """
                UPDATE patch_runs

                SET
                    status = ?,
                    summary = ?,
                    diff_text = ?,
                    files_changed = ?,
                    validation_json = ?,
                    completed_at = ?

                WHERE patch_id = ?
                """,
                (
                    status,

                    summary,

                    diff,

                    json.dumps(
                        files
                    ),

                    json.dumps(
                        [
                            item.model_dump()

                            for item
                            in validation
                        ]
                    ),

                    completed_at,

                    patch_id,
                ),
            )

        return PatchResponse(
            patch_id=patch_id,

            workspace_id=(
                workspace.id
            ),

            workspace_name=(
                workspace.name
            ),

            status=status,

            task=task,

            summary=summary,

            files_changed=files,

            diff=diff,

            validation=validation,

            sandbox_path=str(
                sandbox
            ),
        )

    except Exception as error:

        with get_database() as database:

            database.execute(
                """
                UPDATE patch_runs

                SET
                    status = ?,
                    error_message = ?,
                    completed_at = ?

                WHERE patch_id = ?
                """,
                (
                    "failed",

                    str(error)[:4000],

                    datetime.now(
                        timezone.utc
                    ).isoformat(),

                    patch_id,
                ),
            )

        raise

def get_patch(
    patch_id: str,
):

    from patching.models import (
        PatchStatus,
        ValidationCheck,
    )

    with get_database() as database:

        row = database.execute(
            """
            SELECT *
            FROM patch_runs

            WHERE patch_id = ?
            """,
            (patch_id,),
        ).fetchone()

    if row is None:
        return None

    files = json.loads(
        row["files_changed"]
        or "[]"
    )

    validation_data = json.loads(
        row["validation_json"]
        or "[]"
    )

    validation = [
        ValidationCheck(
            **item
        )

        for item
        in validation_data
    ]

    return PatchStatus(
        patch_id=row[
            "patch_id"
        ],

        workspace_id=row[
            "workspace_id"
        ],

        task=row["task"],

        status=row["status"],

        summary=row["summary"],

        files_changed=files,

        diff=row["diff_text"],

        validation=validation,

        error_message=row[
            "error_message"
        ],
    )
