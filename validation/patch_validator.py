import shutil
import subprocess

from pathlib import Path

from patching.models import (
    ValidationCheck,
)

from patching.worktree import (
    diff_check,
)


VALIDATION_TIMEOUT = 60


def _run(
    command: list[str],
    cwd: Path,
):

    try:

        result = subprocess.run(
            command,

            cwd=cwd,

            capture_output=True,
            text=True,

            timeout=(
                VALIDATION_TIMEOUT
            ),
        )

        output = (
            result.stdout
            + result.stderr
        ).strip()

        return (
            result.returncode == 0,
            output[:6000],
        )

    except subprocess.TimeoutExpired:

        return (
            False,
            "Validation timed out.",
        )

    except FileNotFoundError as error:

        return (
            False,
            str(error),
        )


def validate_patch(
    sandbox: Path,

    files: list[str],
) -> list[
    ValidationCheck
]:

    results = []

    #
    # --------------------------------
    # Git structural diff check
    # --------------------------------
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

    #
    # --------------------------------
    # Python
    # --------------------------------
    #
    for file_path in files:

        absolute = (
            sandbox / file_path
        )

        suffix = (
            absolute.suffix.lower()
        )

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
                        "python syntax: "
                        + file_path
                    ),

                    passed=passed,

                    output=(
                        output
                        or "Syntax OK."
                    ),
                )
            )

    #
    # --------------------------------
    # PHP
    # --------------------------------
    #
    if shutil.which("php"):

        for file_path in files:

            if not file_path.endswith(
                ".php"
            ):
                continue

            passed, output = _run(
                [
                    "php",
                    "-l",
                    str(
                        sandbox
                        / file_path
                    ),
                ],

                sandbox,
            )

            results.append(
                ValidationCheck(
                    name=(
                        "php syntax: "
                        + file_path
                    ),

                    passed=passed,

                    output=(
                        output
                        or "Syntax OK."
                    ),
                )
            )

    #
    # --------------------------------
    # JavaScript
    # --------------------------------
    #
    if shutil.which("node"):

        for file_path in files:

            if not file_path.endswith(
                (
                    ".js",
                    ".mjs",
                    ".cjs",
                )
            ):
                continue

            passed, output = _run(
                [
                    "node",
                    "--check",
                    str(
                        sandbox
                        / file_path
                    ),
                ],

                sandbox,
            )

            results.append(
                ValidationCheck(
                    name=(
                        "javascript syntax: "
                        + file_path
                    ),

                    passed=passed,

                    output=(
                        output
                        or "Syntax OK."
                    ),
                )
            )

    #
    # --------------------------------
    # TypeScript
    # --------------------------------
    #
    typescript_files = [
        file_path

        for file_path in files

        if file_path.endswith(
            (
                ".ts",
                ".tsx",
            )
        )
    ]

    if (
        typescript_files
        and shutil.which("tsc")
    ):

        tsconfig = (
            sandbox / "tsconfig.json"
        )

        if tsconfig.exists():

            command = [
                "tsc",
                "--noEmit",
                "--pretty",
                "false",
            ]

            name = (
                "typescript project check"
            )

        else:

            command = [
                "tsc",
                "--noEmit",
                "--pretty",
                "false",
                "--skipLibCheck",
                "--target",
                "ES2020",

                *typescript_files,
            ]

            name = (
                "typescript changed files"
            )

        passed, output = _run(
            command,
            sandbox,
        )

        results.append(
            ValidationCheck(
                name=name,

                passed=passed,

                output=(
                    output
                    or "TypeScript check passed."
                ),
            )
        )

    return results