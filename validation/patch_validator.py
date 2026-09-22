import shutil
import subprocess

from pathlib import Path

from patching.models import (
    ValidationCheck,
)

from patching.worktree import (
    diff_check,
)


def _run(
    command: list[str],
    cwd: Path,
):

    result = subprocess.run(
        command,

        cwd=cwd,

        capture_output=True,
        text=True,

        timeout=60,
    )

    output = (
        result.stdout
        + result.stderr
    ).strip()

    return (
        result.returncode == 0,
        output[:4000],
    )


def validate_patch(
    sandbox: Path,

    files: list[str],
) -> list[
    ValidationCheck
]:

    results = []

    #
    # Always validate Git diff syntax.
    #
    passed, output = diff_check(
        sandbox
    )

    results.append(
        ValidationCheck(
            name="git diff --check",

            passed=passed,

            output=(
                output
                or "No whitespace errors."
            ),
        )
    )

    for file_path in files:

        absolute = (
            sandbox
            / file_path
        )

        suffix = (
            absolute.suffix.lower()
        )

        #
        # Python syntax only.
        #
        if suffix == ".py":

            passed, output = _run(
                [
                    "python",
                    "-m",
                    "py_compile",
                    str(absolute),
                ],

                sandbox,
            )

            results.append(
                ValidationCheck(
                    name=(
                        f"python syntax: "
                        f"{file_path}"
                    ),

                    passed=passed,

                    output=(
                        output
                        or "Syntax OK."
                    ),
                )
            )

        #
        # PHP syntax if PHP exists.
        #
        elif (
            suffix == ".php"
            and shutil.which(
                "php"
            )
        ):

            passed, output = _run(
                [
                    "php",
                    "-l",
                    str(absolute),
                ],

                sandbox,
            )

            results.append(
                ValidationCheck(
                    name=(
                        f"php syntax: "
                        f"{file_path}"
                    ),

                    passed=passed,

                    output=output,
                )
            )

        #
        # JavaScript syntax if Node exists.
        #
        elif (
            suffix in {
                ".js",
                ".mjs",
                ".cjs",
            }
            and shutil.which(
                "node"
            )
        ):

            passed, output = _run(
                [
                    "node",
                    "--check",
                    str(absolute),
                ],

                sandbox,
            )

            results.append(
                ValidationCheck(
                    name=(
                        f"javascript syntax: "
                        f"{file_path}"
                    ),

                    passed=passed,

                    output=(
                        output
                        or "Syntax OK."
                    ),
                )
            )

    return results
