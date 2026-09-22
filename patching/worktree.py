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
            or "Unable to create Git worktree."
        )

    return (
        patch_id,
        sandbox,
    )


def get_diff(
    sandbox: Path,
) -> str:

    return _git(
        sandbox,

        "diff",

        "--no-ext-diff",

        "--unified=3",
    )


def diff_check(
    sandbox: Path,
) -> tuple[bool, str]:

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


def changed_files(
    sandbox: Path,
) -> list[str]:

    output = _git(
        sandbox,

        "diff",

        "--name-only",
    )

    return [
        line.strip()

        for line in (
            output.splitlines()
        )

        if line.strip()
    ]


def remove_worktree(
    repo_path: Path,
    sandbox: Path,
):

    subprocess.run(
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

    if sandbox.exists():

        shutil.rmtree(
            sandbox,
            ignore_errors=True,
        )
