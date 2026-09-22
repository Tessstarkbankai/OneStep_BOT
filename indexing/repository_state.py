import hashlib
import subprocess

from dataclasses import dataclass
from pathlib import Path


class RepositoryStateError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class RepositoryState:

    head_commit: str

    state_hash: str

    dirty: bool

    changed_files: list[str]


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

        raise RepositoryStateError(
            result.stderr.strip()
            or result.stdout.strip()
            or "Git command failed."
        )

    return result.stdout


def _hash_file(
    path: Path,
) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        while True:

            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def _tracked_changed_files(
    repo_path: Path,
) -> set[str]:

    output = _git(
        repo_path,
        "diff",
        "--name-only",
        "HEAD",
        "--",
    )

    return {
        line.strip()

        for line in output.splitlines()

        if line.strip()
    }


def _untracked_files(
    repo_path: Path,
) -> set[str]:

    output = _git(
        repo_path,
        "ls-files",
        "--others",
        "--exclude-standard",
    )

    return {
        line.strip()

        for line in output.splitlines()

        if line.strip()
    }


def get_repository_state(
    repo_path: Path,
) -> RepositoryState:

    repo_path = repo_path.resolve()

    head_commit = _git(
        repo_path,
        "rev-parse",
        "HEAD",
    ).strip()

    changed = (
        _tracked_changed_files(
            repo_path
        )
        |
        _untracked_files(
            repo_path
        )
    )

    changed_files = sorted(
        changed
    )

    digest = hashlib.sha256()

    #
    # HEAD represents all committed
    # repository contents.
    #
    digest.update(
        (
            "HEAD:"
            + head_commit
            + "\n"
        ).encode(
            "utf-8"
        )
    )

    #
    # Working-tree paths plus their
    # current contents represent changes
    # that have not yet been committed.
    #
    for relative_path in changed_files:

        digest.update(
            (
                "PATH:"
                + relative_path
                + "\n"
            ).encode(
                "utf-8"
            )
        )

        absolute = (
            repo_path
            / relative_path
        )

        if absolute.is_file():

            try:

                content_hash = (
                    _hash_file(
                        absolute
                    )
                )

                digest.update(
                    (
                        "FILE:"
                        + content_hash
                        + "\n"
                    ).encode(
                        "utf-8"
                    )
                )

            except OSError:

                digest.update(
                    b"UNREADABLE\n"
                )

        elif absolute.exists():

            digest.update(
                b"NON_FILE\n"
            )

        else:

            #
            # Deleted tracked file.
            #
            digest.update(
                b"DELETED\n"
            )

    return RepositoryState(
        head_commit=head_commit,

        state_hash=(
            digest.hexdigest()
        ),

        dirty=bool(
            changed_files
        ),

        changed_files=(
            changed_files
        ),
    )
