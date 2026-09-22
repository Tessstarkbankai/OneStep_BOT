import json
import shutil

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCommand:
    name: str

    command: list[str]

    timeout: int = 120


def _inside_repository(
    root: Path,
    target: Path,
) -> bool:

    try:

        target.resolve().relative_to(
            root.resolve()
        )

        return True

    except ValueError:

        return False


def _local_binary(
    root: Path,
    name: str,
) -> Path | None:

    candidate = (
        root
        / "node_modules"
        / ".bin"
        / name
    )

    if not candidate.exists():

        return None

    if not _inside_repository(
        root,
        candidate,
    ):

        return None

    return candidate


def _read_package_json(
    root: Path,
) -> dict:

    package_path = (
        root / "package.json"
    )

    if not package_path.exists():

        return {}

    try:

        return json.loads(
            package_path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):

        return {}


def _node_dependencies(
    root: Path,
) -> set[str]:

    package = _read_package_json(
        root
    )

    dependencies = set()

    for section in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
    ):

        values = package.get(
            section,
            {}
        )

        if isinstance(
            values,
            dict,
        ):

            dependencies.update(
                values.keys()
            )

    return dependencies


def _has_python_tests(
    root: Path,
) -> bool:

    if (
        root / "tests"
    ).is_dir():

        return True

    for pattern in (
        "test_*.py",
        "*_test.py",
    ):

        if next(
            root.glob(pattern),
            None,
        ):

            return True

    return False


def detect_test_commands(
    root: Path,
) -> list[TestCommand]:

    root = root.resolve()

    commands: list[
        TestCommand
    ] = []

    #
    # -----------------------------
    # Python / pytest
    # -----------------------------
    #
    if _has_python_tests(
        root
    ):

        pytest_binary = (
            shutil.which(
                "pytest"
            )
        )

        if pytest_binary:

            commands.append(
                TestCommand(
                    name="pytest",

                    command=[
                        pytest_binary,
                        "-q",
                        "--disable-warnings",
                        "--maxfail=1",
                    ],

                    timeout=120,
                )
            )

    #
    # -----------------------------
    # JavaScript / TypeScript
    # -----------------------------
    #
    dependencies = (
        _node_dependencies(
            root
        )
    )

    if "vitest" in dependencies:

        binary = _local_binary(
            root,
            "vitest",
        )

        if binary:

            commands.append(
                TestCommand(
                    name="vitest",

                    command=[
                        str(binary),
                        "run",
                    ],

                    timeout=120,
                )
            )

    elif "jest" in dependencies:

        binary = _local_binary(
            root,
            "jest",
        )

        if binary:

            commands.append(
                TestCommand(
                    name="jest",

                    command=[
                        str(binary),
                        "--runInBand",
                    ],

                    timeout=120,
                )
            )

    elif "mocha" in dependencies:

        binary = _local_binary(
            root,
            "mocha",
        )

        if binary:

            commands.append(
                TestCommand(
                    name="mocha",

                    command=[
                        str(binary),
                    ],

                    timeout=120,
                )
            )

    #
    # -----------------------------
    # PHP / PHPUnit
    # -----------------------------
    #
    phpunit = (
        root
        / "vendor"
        / "bin"
        / "phpunit"
    )

    if (
        phpunit.exists()
        and _inside_repository(
            root,
            phpunit,
        )
    ):

        php_binary = shutil.which(
            "php"
        )

        if php_binary:

            commands.append(
                TestCommand(
                    name="phpunit",

                    command=[
                        php_binary,
                        str(phpunit),
                        "--colors=never",
                    ],

                    timeout=120,
                )
            )

    return commands
