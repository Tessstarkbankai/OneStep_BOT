import shutil
import subprocess
import uuid

from pathlib import Path


WORKTREE_ROOT = Path(
    "/tmp/outrightbot-worktrees"
)


class WorktreeError(
    RuntimeError
):
    pass


def _git(
    repo_path: Path,
    *args: str,
) -> str:
    """
    Run a Git command inside repo_path.

    Raises WorktreeError if Git returns
    a non-zero exit code.
    """

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            *args,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise WorktreeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Git command failed."
        )

    return result.stdout


def verify_git_repository(
    repo_path: Path,
):
    """
    Ensure the workspace is inside
    a valid Git repository.
    """

    repo_path = repo_path.resolve()

    output = _git(
        repo_path,
        "rev-parse",
        "--is-inside-work-tree",
    ).strip()

    if output != "true":
        raise WorktreeError(
            "Workspace is not a Git repository."
        )


def verify_clean_repository(
    repo_path: Path,
):
    """
    Refuse patch generation when the real
    repository contains uncommitted changes.

    This prevents OutrightBot from creating
    a sandbox from an unclear repository state.
    """

    repo_path = repo_path.resolve()

    status = _git(
        repo_path,
        "status",
        "--porcelain",
    )

    if status.strip():
        raise WorktreeError(
            "Repository has uncommitted changes. "
            "Commit or stash them before creating "
            "a patch."
        )


def create_patch_worktree(
    repo_path: Path,
) -> tuple[str, Path]:
    """
    Create a detached Git worktree from HEAD.

    Returns:
        patch_id
        sandbox_path
    """

    repo_path = repo_path.resolve()

    verify_git_repository(
        repo_path
    )

    verify_clean_repository(
        repo_path
    )

    WORKTREE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    patch_id = (
        "patch-"
        + uuid.uuid4().hex[:12]
    )

    sandbox = (
        WORKTREE_ROOT
        / patch_id
    ).resolve()

    if sandbox.exists():
        raise WorktreeError(
            "Patch sandbox already exists: "
            f"{sandbox}"
        )

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "worktree",
            "add",
            "--detach",
            str(sandbox),
            "HEAD",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise WorktreeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Unable to create Git worktree."
        )

    return (
        patch_id,
        sandbox,
    )


def get_diff(
    sandbox: Path,
) -> str:
    """
    Return the current unstaged Git diff
    inside the patch sandbox.
    """

    sandbox = sandbox.resolve()

    return _git(
        sandbox,
        "diff",
        "--no-ext-diff",
        "--unified=3",
    )


def diff_check(
    sandbox: Path,
) -> tuple[bool, str]:
    """
    Run `git diff --check`.

    This detects whitespace errors such as
    trailing whitespace and malformed patches.
    """

    sandbox = sandbox.resolve()

    result = subprocess.run(
        [
            "git",
            "-C",
            str(sandbox),
            "diff",
            "--check",
        ],
        capture_output=True,
        text=True,
    )

    output = (
        result.stdout
        + result.stderr
    ).strip()

    return (
        result.returncode == 0,
        output,
    )
def get_head_commit(
    repo_path: Path,
) -> str:

    return _git(
        repo_path,
        "rev-parse",
        "HEAD",
    ).strip()


def apply_diff_to_repository(
    repo_path: Path,
    diff_text: str,
):
    """
    Validate and apply an already-reviewed
    patch to the primary repository.

    Does NOT commit.
    """

    repo_path = repo_path.resolve()

    verify_git_repository(
        repo_path
    )

    verify_clean_repository(
        repo_path
    )

    #
    # First check whether the patch can
    # cleanly apply.
    #
    check = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "apply",
            "--check",
            "-",
        ],
        input=diff_text,
        capture_output=True,
        text=True,
    )

    if check.returncode != 0:

        raise WorktreeError(
            "Patch no longer applies cleanly: "
            + (
                check.stderr.strip()
                or check.stdout.strip()
            )
        )

    #
    # Apply only after --check passed.
    #
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "apply",
            "-",
        ],
        input=diff_text,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        raise WorktreeError(
            "Unable to apply approved patch: "
            + (
                result.stderr.strip()
                or result.stdout.strip()
            )
        )
def changed_files(
    sandbox: Path,
) -> list[str]:
    """
    Return repository-relative paths for
    files changed in the patch sandbox.
    """

    sandbox = sandbox.resolve()

    output = _git(
        sandbox,
        "diff",
        "--name-only",
    )

    return [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]


def reset_worktree(
    sandbox: Path,
):
    """
    Reset the sandbox back to its original
    detached HEAD state.

    Used before an automatic patch repair.
    """

    sandbox = sandbox.resolve()

    _git(
        sandbox,
        "reset",
        "--hard",
        "HEAD",
    )

    _git(
        sandbox,
        "clean",
        "-fd",
    )


def remove_worktree(
    repo_path: Path,
    sandbox: Path,
):
    """
    Remove a patch worktree safely.

    This does not modify the primary
    repository's checked-out files.
    """

    repo_path = repo_path.resolve()
    sandbox = sandbox.resolve()

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "worktree",
            "remove",
            "--force",
            str(sandbox),
        ],
        capture_output=True,
        text=True,
    )

    #
    # It is possible that Git already
    # considers the worktree removed but
    # the directory still exists.
    #
    if sandbox.exists():
        shutil.rmtree(
            sandbox,
            ignore_errors=True,
        )

    #
    # Clean stale worktree metadata.
    #
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "worktree",
            "prune",
        ],
        capture_output=True,
        text=True,
    )

    if (
        result.returncode != 0
        and "is not a working tree"
        not in result.stderr.lower()
        and "is not a working tree"
        not in result.stdout.lower()
    ):
        raise WorktreeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Unable to remove Git worktree."
        )