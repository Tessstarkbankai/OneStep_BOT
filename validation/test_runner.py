import os
import subprocess

from pathlib import Path

from patching.models import (
    ValidationCheck,
)

from validation.test_policy import (
    detect_test_commands,
)


MAX_OUTPUT = 10000


def _safe_environment() -> dict[
    str,
    str
]:

    environment = dict(
        os.environ
    )

    environment.update(
        {
            "CI": "1",

            "NO_COLOR": "1",

            "PYTHONUNBUFFERED": "1",

            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    return environment


def run_project_tests(
    sandbox: Path,
) -> list[
    ValidationCheck
]:

    sandbox = sandbox.resolve()

    commands = detect_test_commands(
        sandbox
    )

    if not commands:

        return [
            ValidationCheck(
                name="project tests",

                passed=True,

                output=(
                    "SKIPPED: no supported "
                    "installed test framework "
                    "was detected."
                ),
            )
        ]

    results = []

    for test in commands:

        try:

            process = subprocess.run(
                test.command,

                cwd=sandbox,

                capture_output=True,

                text=True,

                timeout=test.timeout,

                env=_safe_environment(),
            )

            output = (
                process.stdout
                + process.stderr
            ).strip()

            results.append(
                ValidationCheck(
                    name=(
                        "project tests: "
                        + test.name
                    ),

                    passed=(
                        process.returncode
                        == 0
                    ),

                    output=(
                        output[:MAX_OUTPUT]
                        or (
                            test.name
                            + " passed."
                        )
                    ),
                )
            )

        except (
            subprocess.TimeoutExpired
        ):

            results.append(
                ValidationCheck(
                    name=(
                        "project tests: "
                        + test.name
                    ),

                    passed=False,

                    output=(
                        "Test command timed "
                        f"out after "
                        f"{test.timeout} "
                        "seconds."
                    ),
                )
            )

        except OSError as error:

            results.append(
                ValidationCheck(
                    name=(
                        "project tests: "
                        + test.name
                    ),

                    passed=False,

                    output=str(error),
                )
            )

    return results
