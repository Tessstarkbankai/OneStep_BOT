import json
import hashlib
from datetime import (
    datetime,
    timezone,
)
MAX_REPAIR_ATTEMPTS = 1
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
    apply_diff_to_repository,
    changed_files,
    create_patch_worktree,
    get_diff,
    get_head_commit,
    remove_worktree,
    reset_worktree,
    verify_clean_repository,
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
def _hash_diff(
    diff_text: str,
) -> str:

    return hashlib.sha256(
        diff_text.encode(
            "utf-8"
        )
    ).hexdigest()

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

    base_commit = get_head_commit(
        repo_path
    )    
    if (
        len(base_commit) != 40
        or not all(
            character
            in "0123456789abcdef"

            for character
            in base_commit.lower()
        )
    ):

        raise RuntimeError(
            "Invalid Git base commit: "
            f"{base_commit}"
        )
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
                base_commit,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patch_id,
                workspace_id,
                task,
                "generating",
                str(sandbox),
                base_commit,
                created_at,
            ),
        )

    try:

        validation_feedback = None

        summary = ""
        files = []
        diff = ""
        validation = []

        for attempt in range(
            MAX_REPAIR_ATTEMPTS + 1
        ):

            if attempt > 0:

                reset_worktree(
                    sandbox
                )

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

                    validation_feedback=(
                        validation_feedback
                    ),
                )
            )

            apply_edits(
                workspace_id=(
                    workspace_id
                ),

                sandbox=sandbox,

                edits=edits,
            )

            files = changed_files(
                sandbox
            )

            if not files:

                raise RuntimeError(
                    "Patch produced no "
                    "Git changes."
                )

            diff = get_diff(
                sandbox
            )
            diff_sha256 = _hash_diff(
                diff
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

            if validation_passed:

                break

            if (
                attempt
                >= MAX_REPAIR_ATTEMPTS
            ):

                break

            validation_feedback = (
                "FAILED PATCH DIFF:\n"
                + diff[:6000]
                + "\n\n"
                "VALIDATION ERRORS:\n"
            )

            for check in validation:

                if check.passed:
                    continue

                validation_feedback += (
                    "\n"
                    + check.name
                    + ":\n"
                    + check.output[:3000]
                    + "\n"
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
                    diff_sha256 = ?,
                    files_changed = ?,
                    validation_json = ?,
                    completed_at = ?

                WHERE patch_id = ?
                """,
                (
                    status,
                    summary,
                    diff,
                    diff_sha256,

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

def approve_patch(
    patch_id: str,
):

    from patching.models import (
        PatchDecisionResponse,
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

    if row is None:

        raise RuntimeError(
            "Patch not found."
        )

    if row["status"] != "ready":

        raise RuntimeError(
            "Only patches with status "
            "'ready' can be approved. "
            f"Current status: "
            f"{row['status']}"
        )

    workspace = get_workspace(
        row["workspace_id"]
    )

    if workspace is None:

        raise WorkspaceError(
            "Workspace no longer exists."
        )

    repo_path = Path(
        workspace.path
    ).resolve()

    #
    # Real repository must have no
    # uncommitted changes.
    #
    verify_clean_repository(
        repo_path
    )

    current_commit = get_head_commit(
        repo_path
    )

    base_commit = row[
        "base_commit"
    ]
    if (
        not base_commit
        or len(base_commit) != 40
        or not all(
            character
            in "0123456789abcdef"

            for character
            in base_commit.lower()
        )
    ):

        raise RuntimeError(
            "Patch contains an invalid "
            "base Git commit: "
            f"{base_commit}. "
            "Generate a fresh patch."
        )    

    if not base_commit:

        raise RuntimeError(
            "Patch does not contain a "
            "base commit. Generate a "
            "fresh patch."
        )

    #
    # Critical stale-patch protection.
    #
    if current_commit != base_commit:

        raise RuntimeError(
            "Repository HEAD changed after "
            "this patch was generated. "
            f"Patch base: "
            f"{base_commit[:12]}, "
            f"current HEAD: "
            f"{current_commit[:12]}. "
            "Generate a fresh patch."
        )

    #
    # The persisted validated diff is
    # the durable approval artifact.
    #
    stored_diff = row[
        "diff_text"
    ]

    if (
        not stored_diff
        or not stored_diff.strip()
    ):

        raise RuntimeError(
            "Patch has no stored diff."
        )

    stored_hash = row[
        "diff_sha256"
    ]

    calculated_hash = _hash_diff(
        stored_diff
    )

    #
    # New patches should always have
    # diff_sha256.
    #
    # For patches created immediately
    # before this migration, populate it
    # from their already-stored diff.
    #
    if not stored_hash:

        stored_hash = calculated_hash

        with get_database() as database:

            database.execute(
                """
                UPDATE patch_runs

                SET diff_sha256 = ?

                WHERE patch_id = ?
                """,
                (
                    stored_hash,
                    patch_id,
                ),
            )

    if stored_hash != calculated_hash:

        raise RuntimeError(
            "Stored patch integrity check "
            "failed. The saved diff no "
            "longer matches its SHA256."
        )

    sandbox = Path(
        row["sandbox_path"]
    ).resolve()

    #
    # If the sandbox still exists,
    # compare its current diff with the
    # durable stored patch.
    #
    # If it disappeared, approval can
    # still safely continue because the
    # validated diff and base commit were
    # persisted.
    #
    if sandbox.exists():

        sandbox_diff = get_diff(
            sandbox
        )

        if sandbox_diff.strip():

            sandbox_hash = _hash_diff(
                sandbox_diff
            )

            if (
                sandbox_hash
                != stored_hash
            ):

                raise RuntimeError(
                    "Patch sandbox differs "
                    "from the validated "
                    "stored patch."
                )

    files = json.loads(
        row["files_changed"]
        or "[]"
    )

    #
    # git apply --check happens inside
    # this function before actual apply.
    #
    apply_diff_to_repository(
        repo_path=repo_path,
        diff_text=stored_diff,
    )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    with get_database() as database:

        database.execute(
            """
            UPDATE patch_runs

            SET
                status = ?,
                decision_at = ?,
                applied_at = ?

            WHERE patch_id = ?
            """,
            (
                "applied",
                now,
                now,
                patch_id,
            ),
        )

    #
    # Sandbox cleanup is optional.
    # Approval must not depend on it.
    #
    if sandbox.exists():

        try:

            remove_worktree(
                repo_path=repo_path,
                sandbox=sandbox,
            )

        except Exception as error:

            print(
                "[patch cleanup warning] "
                f"{error}"
            )

    return PatchDecisionResponse(
        patch_id=patch_id,

        workspace_id=(
            row["workspace_id"]
        ),

        status="applied",

        message=(
            "Patch was applied to the "
            "workspace working tree. "
            "It has NOT been committed "
            "or pushed."
        ),

        files_changed=files,
    )
def reject_patch(
    patch_id: str,
):

    from patching.models import (
        PatchDecisionResponse,
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

    if row is None:

        raise RuntimeError(
            "Patch not found."
        )

    if row["status"] not in {
        "ready",
        "validation_failed",
        "failed",
    }:

        raise RuntimeError(
            "Patch cannot be rejected "
            "from status: "
            f"{row['status']}"
        )

    workspace = get_workspace(
        row["workspace_id"]
    )

    if workspace is None:

        raise WorkspaceError(
            "Workspace no longer exists."
        )

    repo_path = Path(
        workspace.path
    ).resolve()

    sandbox = Path(
        row["sandbox_path"]
    ).resolve()

    if sandbox.exists():

        remove_worktree(
            repo_path=repo_path,
            sandbox=sandbox,
        )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    with get_database() as database:

        database.execute(
            """
            UPDATE patch_runs

            SET
                status = ?,
                decision_at = ?

            WHERE patch_id = ?
            """,
            (
                "rejected",
                now,
                patch_id,
            ),
        )

    files = json.loads(
        row["files_changed"]
        or "[]"
    )

    return PatchDecisionResponse(
        patch_id=patch_id,

        workspace_id=(
            row["workspace_id"]
        ),

        status="rejected",

        message=(
            "Patch was rejected and "
            "its sandbox was removed."
        ),

        files_changed=files,
    )