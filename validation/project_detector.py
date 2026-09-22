from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectProfile:
    python: bool

    node: bool

    typescript: bool

    php: bool

    python_config: str | None

    package_json: str | None

    tsconfig: str | None

    composer_json: str | None


def _relative_if_exists(
    root: Path,
    name: str,
) -> str | None:

    target = root / name

    if target.exists():
        return name

    return None


def detect_project(
    root: Path,
    changed_files: list[str],
) -> ProjectProfile:

    root = root.resolve()

    suffixes = {
        Path(file_path).suffix.lower()

        for file_path in changed_files
    }

    python_config = None

    for name in (
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "setup.py",
        "requirements.txt",
    ):

        if (root / name).exists():

            python_config = name
            break

    package_json = (
        _relative_if_exists(
            root,
            "package.json",
        )
    )

    tsconfig = (
        _relative_if_exists(
            root,
            "tsconfig.json",
        )
    )

    composer_json = (
        _relative_if_exists(
            root,
            "composer.json",
        )
    )

    python_project = (
        python_config is not None
        or ".py" in suffixes
    )

    node_project = (
        package_json is not None
        or bool(
            suffixes
            & {
                ".js",
                ".mjs",
                ".cjs",
                ".ts",
                ".tsx",
                ".jsx",
            }
        )
    )

    typescript_project = (
        tsconfig is not None
        or bool(
            suffixes
            & {
                ".ts",
                ".tsx",
            }
        )
    )

    php_project = (
        composer_json is not None
        or ".php" in suffixes
    )

    return ProjectProfile(
        python=python_project,

        node=node_project,

        typescript=(
            typescript_project
        ),

        php=php_project,

        python_config=(
            python_config
        ),

        package_json=(
            package_json
        ),

        tsconfig=tsconfig,

        composer_json=(
            composer_json
        ),
    )
