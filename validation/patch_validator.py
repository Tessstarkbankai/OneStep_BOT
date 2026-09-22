import shutil
import subprocess
import sys

from pathlib import Path

from patching.models import (
    ValidationCheck,
)

from patching.worktree import (
    diff_check,
)

from validation.project_detector import (
    detect_project,
)
from validation.test_runner import (
    run_project_tests,
)

VALIDATION_TIMEOUT = 90


def _run(
    command: list[str],

    cwd: Path,

    timeout: int = (
        VALIDATION_TIMEOUT
    ),
) -> tuple[bool, str]:

    try:

        result = subprocess.run(
            command,

            cwd=cwd,

            capture_output=True,

            text=True,

            timeout=timeout,
        )

        output = (
            result.stdout
            + result.stderr
        ).strip()

        return (
            result.returncode == 0,

            output[:8000],
        )

    except subprocess.TimeoutExpired:

        return (
            False,

            (
                "Validation timed out "
                f"after {timeout} seconds."
            ),
        )

    except FileNotFoundError as error:

        return (
            False,
            str(error),
        )


def _result(
    name: str,

    passed: bool,

    output: str,

    success_message: str,
) -> ValidationCheck:

    return ValidationCheck(
        name=name,

        passed=passed,

        output=(
            output
            or success_message
        ),
    )


def validate_patch(
    sandbox: Path,

    files: list[str],
) -> list[
    ValidationCheck
]:

    sandbox = sandbox.resolve()

    results = []

    profile = detect_project(
        sandbox,
        files,
    )

    #
    # --------------------------------
    # Project detection
    # --------------------------------
    #

    detected = []

    if profile.python:
        detected.append("python")

    if profile.node:
        detected.append("node")

    if profile.typescript:
        detected.append(
            "typescript"
        )

    if profile.php:
        detected.append("php")

    results.append(
        ValidationCheck(
            name="project detection",

            passed=True,

            output=(
                ", ".join(detected)
                if detected
                else "No specific project type detected."
            ),
        )
    )

    #
    # --------------------------------
    # Git diff integrity
    # --------------------------------
    #

    passed, output = diff_check(
        sandbox
    )

    results.append(
        _result(
            "git diff --check",

            passed,

            output,

            "No whitespace errors.",
        )
    )

    #
    # --------------------------------
    # Python changed files
    # --------------------------------
    #

    python_files = [
        file_path

        for file_path in files

        if file_path.endswith(
            ".py"
        )
    ]

    for file_path in python_files:

        absolute = (
            sandbox
            / file_path
        )

        passed, output = _run(
            [
                sys.executable,

                "-m",

                "py_compile",

                str(absolute),
            ],

            sandbox,
        )

        results.append(
            _result(
                (
                    "python syntax: "
                    + file_path
                ),

                passed,

                output,

                "Python syntax OK.",
            )
        )

    #
    # --------------------------------
    # PHP changed files
    # --------------------------------
    #

    php_files = [
        file_path

        for file_path in files

        if file_path.endswith(
            ".php"
        )
    ]

    if php_files:

        php_binary = shutil.which(
            "php"
        )

        if php_binary:

            for file_path in php_files:

                passed, output = _run(
                    [
                        php_binary,

                        "-l",

                        str(
                            sandbox
                            / file_path
                        ),
                    ],

                    sandbox,
                )

                results.append(
                    _result(
                        (
                            "php syntax: "
                            + file_path
                        ),

                        passed,

                        output,

                        "PHP syntax OK.",
                    )
                )

        else:

            results.append(
                ValidationCheck(
                    name=(
                        "php validator"
                    ),

                    passed=True,

                    output=(
                        "SKIPPED: php binary "
                        "is not installed."
                    ),
                )
            )

    #
    # --------------------------------
    # JavaScript changed files
    # --------------------------------
    #

    javascript_files = [
        file_path

        for file_path in files

        if file_path.endswith(
            (
                ".js",
                ".mjs",
                ".cjs",
            )
        )
    ]

    if javascript_files:

        node_binary = (
            shutil.which(
                "node"
            )
        )

        if node_binary:

            for file_path in (
                javascript_files
            ):

                passed, output = _run(
                    [
                        node_binary,

                        "--check",

                        str(
                            sandbox
                            / file_path
                        ),
                    ],

                    sandbox,
                )

                results.append(
                    _result(
                        (
                            "javascript syntax: "
                            + file_path
                        ),

                        passed,

                        output,

                        (
                            "JavaScript "
                            "syntax OK."
                        ),
                    )
                )

        else:

            results.append(
                ValidationCheck(
                    name=(
                        "javascript validator"
                    ),

                    passed=True,

                    output=(
                        "SKIPPED: node "
                        "is not installed."
                    ),
                )
            )

    #
    # --------------------------------
    # TypeScript project validation
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

    if typescript_files:

        tsc_binary = (
            shutil.which(
                "tsc"
            )
        )

        if tsc_binary:

            if profile.tsconfig:

                command = [
                    tsc_binary,

                    "--noEmit",

                    "--pretty",
                    "false",

                    "-p",
                    profile.tsconfig,
                ]

                check_name = (
                    "typescript project check"
                )

            else:

                command = [
                    tsc_binary,

                    "--noEmit",

                    "--pretty",
                    "false",

                    "--skipLibCheck",

                    "--target",
                    "ES2020",

                    *typescript_files,
                ]

                check_name = (
                    "typescript changed files"
                )

            passed, output = _run(
                command,

                sandbox,
            )

            results.append(
                _result(
                    check_name,

                    passed,

                    output,

                    (
                        "TypeScript "
                        "check passed."
                    ),
                )
            )

        else:

            results.append(
                ValidationCheck(
                    name=(
                        "typescript validator"
                    ),

                    passed=True,

                    output=(
                        "SKIPPED: tsc "
                        "is not installed."
                    ),
                )
            )

    #
    # --------------------------------
    # Composer manifest validation
    # --------------------------------
    #

    if profile.composer_json:

        composer_binary = (
            shutil.which(
                "composer"
            )
        )

        if composer_binary:

            passed, output = _run(
                [
                    composer_binary,

                    "validate",

                    "--no-check-publish",

                    "--no-interaction",
                ],

                sandbox,
            )

            results.append(
                _result(
                    "composer validate",

                    passed,

                    output,

                    (
                        "Composer manifest "
                        "is valid."
                    ),
                )
            )

    #
    # --------------------------------
    # package.json JSON validation
    # --------------------------------
    #

    if profile.package_json:

        package_path = (
            sandbox
            / profile.package_json
        )

        passed, output = _run(
            [
                sys.executable,

                "-m",

                "json.tool",

                str(package_path),
            ],

            sandbox,
        )

        results.append(
            _result(
                "package.json validation",

                passed,

                output,

                "package.json is valid.",
            )
        )

    previous_checks_passed = all(
        check.passed
        for check in results
    )

    if previous_checks_passed:

        test_results = (
            run_project_tests(
                sandbox
            )
        )

        results.extend(
            test_results
        )

    else:

        results.append(
            ValidationCheck(
                name="project tests",

                passed=True,

                output=(
                    "SKIPPED: earlier "
                    "validation failed."
                ),
            )
        )
    return results