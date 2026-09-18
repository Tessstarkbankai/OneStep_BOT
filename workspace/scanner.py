import hashlib
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from storage.database import get_database
from workspace.manager import WorkspaceError, get_workspace
from workspace.models import RepositoryFile, ScanResult


MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",

    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",

    ".venv",
    "venv",
    "env",

    "node_modules",
    "bower_components",

    "dist",
    "build",
    "coverage",

    ".next",
    ".nuxt",

    "target",
    ".gradle",

    "vendor",

    ".idea",
    ".vscode",

    "logs",
    "log",

    "tmp",
    "temp",

    ".cache",
}


LANGUAGE_BY_EXTENSION = {
    ".py": "python",

    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",

    ".ts": "typescript",
    ".mts": "typescript",
     ".cts": "typescript",

     ".tsx": "tsx",

     ".jsx": "javascript",

    ".java": "java",

    ".go": "go",

    ".rs": "rust",

    ".php": "php",

    ".rb": "ruby",

    ".cs": "csharp",

    ".c": "c",
    ".h": "c",

    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",

    ".sql": "sql",

    ".html": "html",
    ".htm": "html",

    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",

    ".vue": "vue",
    ".svelte": "svelte",

    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",

    ".json": "json",

    ".yaml": "yaml",
    ".yml": "yaml",

    ".toml": "toml",

    ".xml": "xml",

    ".md": "markdown",
    ".mdx": "markdown",

    ".txt": "text",
}


SPECIAL_FILENAMES = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "procfile": "procfile",

    "package.json": "json",
    "tsconfig.json": "json",
    "jsconfig.json": "json",

    "requirements.txt": "text",

    "pyproject.toml": "toml",

    "docker-compose.yml": "yaml",
    "docker-compose.yaml": "yaml",
    "compose.yml": "yaml",
    "compose.yaml": "yaml",

    ".gitignore": "gitignore",
}


SOURCE_LANGUAGES = {
    "python",
    "javascript",
    "tsx",
    "typescript",
    "java",
    "go",
    "rust",
    "php",
    "ruby",
    "csharp",
    "c",
    "cpp",
    "sql",
    "html",
    "css",
    "scss",
    "sass",
    "less",
    "vue",
    "svelte",
    "shell",
}


SENSITIVE_FILENAMES = {
    "credentials.json",
    "service-account.json",
    "service_account.json",

    "id_rsa",
    "id_dsa",
    "id_ed25519",

    ".npmrc",
    ".pypirc",
}


SENSITIVE_EXTENSIONS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
}


def _is_ignored_path(relative_path: Path) -> bool:
    for part in relative_path.parts[:-1]:
        if part.lower() in IGNORED_DIRECTORIES:
            return True

    return False


def _is_sensitive_file(path: Path) -> bool:
    name = path.name.lower()

    if name in SENSITIVE_FILENAMES:
        return True

    if path.suffix.lower() in SENSITIVE_EXTENSIONS:
        return True

    if name == ".env":
        return True

    if name.startswith(".env."):
        safe_templates = (
            ".example",
            ".sample",
            ".template",
        )

        if not name.endswith(safe_templates):
            return True

    return False


def _detect_language(path: Path) -> str:
    filename = path.name.lower()

    if filename in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[filename]

    if filename.startswith("readme"):
        return "markdown"

    extension = path.suffix.lower()

    return LANGUAGE_BY_EXTENSION.get(
        extension,
        "unknown",
    )


def _is_binary_file(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            chunk = file.read(8192)

    except OSError:
        return True

    return b"\x00" in chunk


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            hasher.update(chunk)

    return hasher.hexdigest()


def _git_files(root: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        check=True,
    )

    output = result.stdout.decode(
        "utf-8",
        errors="replace",
    )

    files = []

    for relative_name in output.split("\0"):
        if not relative_name:
            continue

        path = root / relative_name

        if path.exists() and path.is_file():
            files.append(path)

    return files


def _filesystem_files(root: Path) -> list[Path]:
    files = []

    for current_root, directories, filenames in os.walk(
        root,
        followlinks=False,
    ):
        directories[:] = [
            directory
            for directory in directories
            if directory.lower() not in IGNORED_DIRECTORIES
        ]

        current_path = Path(current_root)

        for filename in filenames:
            path = current_path / filename

            if path.is_symlink():
                continue

            files.append(path)

    return files


def _discover_files(
    root: Path,
    is_git_repo: bool,
) -> tuple[str, list[Path]]:

    if is_git_repo:
        try:
            return "git", _git_files(root)

        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
        ):
            pass

    return "filesystem", _filesystem_files(root)


def scan_workspace(workspace_id: str) -> ScanResult:
    workspace = get_workspace(workspace_id)

    if workspace is None:
        raise WorkspaceError(
            f"Workspace not found: {workspace_id}"
        )

    root = Path(workspace.path).resolve()

    scan_method, candidate_files = _discover_files(
        root,
        workspace.is_git_repo,
    )

    scanned_at = datetime.now(
        timezone.utc
    ).isoformat()

    indexed_records = []

    language_counter = Counter()

    source_files = 0
    other_text_files = 0

    skipped_binary = 0
    skipped_large = 0
    skipped_sensitive = 0

    total_indexed_bytes = 0

    for absolute_path in candidate_files:
        try:
            relative_path = absolute_path.relative_to(root)

        except ValueError:
            continue

        if _is_ignored_path(relative_path):
            continue

        if _is_sensitive_file(absolute_path):
            skipped_sensitive += 1
            continue

        try:
            size_bytes = absolute_path.stat().st_size

        except OSError:
            continue

        if size_bytes > MAX_FILE_SIZE_BYTES:
            skipped_large += 1
            continue

        if _is_binary_file(absolute_path):
            skipped_binary += 1
            continue

        try:
            file_hash = _sha256_file(absolute_path)

        except OSError:
            continue

        language = _detect_language(absolute_path)

        is_source = language in SOURCE_LANGUAGES

        if is_source:
            source_files += 1

        else:
            other_text_files += 1

        language_counter[language] += 1

        total_indexed_bytes += size_bytes

        indexed_records.append(
            (
                workspace.id,
                str(relative_path),
                absolute_path.suffix.lower() or None,
                language,
                size_bytes,
                file_hash,
                int(is_source),
                scanned_at,
            )
        )

    with get_database() as database:
        database.execute(
            """
            DELETE FROM repository_files
            WHERE workspace_id = ?
            """,
            (workspace.id,),
        )

        database.executemany(
            """
            INSERT INTO repository_files (
                workspace_id,
                path,
                extension,
                language,
                size_bytes,
                sha256,
                is_source,
                scanned_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            indexed_records,
        )

        database.execute(
            """
            INSERT INTO workspace_scans (
                workspace_id,
                scanned_at,
                scan_method,
                total_candidates,
                indexed_files,
                source_files,
                other_text_files,
                skipped_binary,
                skipped_large,
                skipped_sensitive,
                total_indexed_bytes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(workspace_id)
            DO UPDATE SET
                scanned_at = excluded.scanned_at,
                scan_method = excluded.scan_method,
                total_candidates = excluded.total_candidates,
                indexed_files = excluded.indexed_files,
                source_files = excluded.source_files,
                other_text_files = excluded.other_text_files,
                skipped_binary = excluded.skipped_binary,
                skipped_large = excluded.skipped_large,
                skipped_sensitive = excluded.skipped_sensitive,
                total_indexed_bytes = excluded.total_indexed_bytes
            """,
            (
                workspace.id,
                scanned_at,
                scan_method,
                len(candidate_files),
                len(indexed_records),
                source_files,
                other_text_files,
                skipped_binary,
                skipped_large,
                skipped_sensitive,
                total_indexed_bytes,
            ),
        )

    return ScanResult(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        root_path=str(root),

        scan_method=scan_method,
        scanned_at=scanned_at,

        total_candidates=len(candidate_files),
        indexed_files=len(indexed_records),

        source_files=source_files,
        other_text_files=other_text_files,

        skipped_binary=skipped_binary,
        skipped_large=skipped_large,
        skipped_sensitive=skipped_sensitive,

        total_indexed_bytes=total_indexed_bytes,

        languages=dict(
            language_counter.most_common()
        ),
    )


def list_repository_files(
    workspace_id: str,
    source_only: bool = False,
    limit: int = 500,
) -> list[RepositoryFile]:

    workspace = get_workspace(workspace_id)

    if workspace is None:
        raise WorkspaceError(
            f"Workspace not found: {workspace_id}"
        )

    query = """
        SELECT
            path,
            extension,
            language,
            size_bytes,
            sha256,
            is_source
        FROM repository_files
        WHERE workspace_id = ?
    """

    parameters = [workspace_id]

    if source_only:
        query += " AND is_source = 1"

    query += " ORDER BY path ASC LIMIT ?"

    parameters.append(limit)

    with get_database() as database:
        rows = database.execute(
            query,
            parameters,
        ).fetchall()

    return [
        RepositoryFile(
            path=row["path"],
            extension=row["extension"],
            language=row["language"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            is_source=bool(row["is_source"]),
        )
        for row in rows
    ]
