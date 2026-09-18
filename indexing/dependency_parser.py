import json
import re

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tree_sitter import Node

from indexing.models import (
    CodeImport,
    DependencyBuildResult,
    DependencyEdge,
)

from indexing.parser_registry import (
    get_parser,
    is_language_supported,
)

from storage.database import get_database

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


JS_LANGUAGES = {
    "javascript",
    "typescript",
    "tsx",
}


JS_EXTENSIONS = {
    "javascript": [
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
    ],

    "typescript": [
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mts",
        ".cts",
        ".mjs",
        ".cjs",
    ],

    "tsx": [
        ".tsx",
        ".ts",
        ".jsx",
        ".js",
        ".mts",
        ".cts",
        ".mjs",
        ".cjs",
    ],
}


def _node_text(
    node: Node,
    source: bytes,
) -> str:
    return source[
        node.start_byte:node.end_byte
    ].decode(
        "utf-8",
        errors="replace",
    )


def _walk_tree(
    root_node: Node,
):
    stack = [root_node]

    while stack:
        node = stack.pop()

        yield node

        children = list(
            node.named_children
        )

        stack.extend(
            reversed(children)
        )


def _normalize_whitespace(
    value: str,
) -> str:
    return " ".join(
        value.split()
    )


def _parse_python_names(
    value: str,
) -> list[str]:

    value = value.strip()

    if (
        value.startswith("(")
        and value.endswith(")")
    ):
        value = value[1:-1]

    names = []

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        item = item.split(
            " as ",
            1,
        )[0].strip()

        if item:
            names.append(item)

    return names


def _extract_python_imports(
    root_node: Node,
    source: bytes,
) -> list[dict]:

    imports = []

    for node in _walk_tree(
        root_node
    ):
        if node.type not in {
            "import_statement",
            "import_from_statement",
        }:
            continue

        raw_text = _node_text(
            node,
            source,
        )

        normalized = (
            _normalize_whitespace(
                raw_text
            )
        )

        start_row, _ = (
            node.start_point
        )

        end_row, _ = (
            node.end_point
        )

        if normalized.startswith(
            "import "
        ):
            payload = normalized[
                len("import "):
            ]

            for item in payload.split(","):
                module = item.strip()

                module = module.split(
                    " as ",
                    1,
                )[0].strip()

                if not module:
                    continue

                imports.append(
                    {
                        "kind": "import",
                        "module": module,
                        "imported_names": [],
                        "is_relative": False,
                        "start_line": (
                            start_row + 1
                        ),
                        "end_line": (
                            end_row + 1
                        ),
                        "raw_text": raw_text,
                    }
                )

            continue

        match = re.match(
            r"^from\s+([.\w]+)"
            r"\s+import\s+(.+)$",
            normalized,
        )

        if not match:
            continue

        module = match.group(1)

        imported_names = (
            _parse_python_names(
                match.group(2)
            )
        )

        #
        # Example:
        #
        # from . import users
        #
        # Turn this into:
        #
        # module = ".users"
        #
        # so it can resolve to users.py.
        #
        if not module.strip("."):
            for name in imported_names:
                if name == "*":
                    continue

                imports.append(
                    {
                        "kind": "from",
                        "module": (
                            module + name
                        ),
                        "imported_names": [
                            name
                        ],
                        "is_relative": True,
                        "start_line": (
                            start_row + 1
                        ),
                        "end_line": (
                            end_row + 1
                        ),
                        "raw_text": raw_text,
                    }
                )

            continue

        imports.append(
            {
                "kind": "from",
                "module": module,
                "imported_names": (
                    imported_names
                ),
                "is_relative": (
                    module.startswith(".")
                ),
                "start_line": (
                    start_row + 1
                ),
                "end_line": (
                    end_row + 1
                ),
                "raw_text": raw_text,
            }
        )

    return imports


def _extract_quoted_module(
    text: str,
) -> str | None:

    match = re.search(
        r"""["']([^"']+)["']""",
        text,
    )

    if not match:
        return None

    return match.group(1)


def _extract_js_imports(
    root_node: Node,
    source: bytes,
) -> list[dict]:

    imports = []

    for node in _walk_tree(
        root_node
    ):
        start_row, _ = (
            node.start_point
        )

        end_row, _ = (
            node.end_point
        )

        if node.type == "import_statement":
            raw_text = _node_text(
                node,
                source,
            )

            module = (
                _extract_quoted_module(
                    raw_text
                )
            )

            if module:
                imports.append(
                    {
                        "kind": "import",
                        "module": module,
                        "imported_names": [],
                        "is_relative": (
                            module.startswith(".")
                        ),
                        "start_line": (
                            start_row + 1
                        ),
                        "end_line": (
                            end_row + 1
                        ),
                        "raw_text": raw_text,
                    }
                )

            continue

        if node.type == "export_statement":
            raw_text = _node_text(
                node,
                source,
            )

            normalized = (
                _normalize_whitespace(
                    raw_text
                )
            )

            if " from " not in normalized:
                continue

            module = (
                _extract_quoted_module(
                    raw_text
                )
            )

            if module:
                imports.append(
                    {
                        "kind": "reexport",
                        "module": module,
                        "imported_names": [],
                        "is_relative": (
                            module.startswith(".")
                        ),
                        "start_line": (
                            start_row + 1
                        ),
                        "end_line": (
                            end_row + 1
                        ),
                        "raw_text": raw_text,
                    }
                )

            continue

        if node.type != "call_expression":
            continue

        function_node = (
            node.child_by_field_name(
                "function"
            )
        )

        if function_node is None:
            continue

        function_name = _node_text(
            function_node,
            source,
        ).strip()

        if function_name != "require":
            continue

        arguments = (
            node.child_by_field_name(
                "arguments"
            )
        )

        if arguments is None:
            continue

        module = None

        for argument in (
            arguments.named_children
        ):
            if argument.type != "string":
                continue

            raw_argument = _node_text(
                argument,
                source,
            )

            module = (
                _extract_quoted_module(
                    raw_argument
                )
            )

            break

        if not module:
            continue

        raw_text = _node_text(
            node,
            source,
        )

        imports.append(
            {
                "kind": "require",
                "module": module,
                "imported_names": [],
                "is_relative": (
                    module.startswith(".")
                ),
                "start_line": (
                    start_row + 1
                ),
                "end_line": (
                    end_row + 1
                ),
                "raw_text": raw_text,
            }
        )

    return imports


def _path_if_known(
    candidate: Path,
    root_path: Path,
    known_paths: set[str],
) -> str | None:

    try:
        candidate = (
            candidate.resolve()
        )

        relative = (
            candidate.relative_to(
                root_path
            )
        )

    except (
        ValueError,
        OSError,
    ):
        return None

    relative_string = (
        relative.as_posix()
    )

    if relative_string in known_paths:
        return relative_string

    return None


def _resolve_python_module(
    module: str,
    imported_names: list[str],
    file_path: str,
    root_path: Path,
    known_paths: set[str],
) -> str | None:

    importer = (
        root_path / file_path
    )

    leading_dots = (
        len(module)
        - len(
            module.lstrip(".")
        )
    )

    module_without_dots = (
        module.lstrip(".")
    )

    module_parts = [
        part
        for part in (
            module_without_dots.split(".")
        )
        if part
    ]

    if leading_dots:
        base = importer.parent

        for _ in range(
            max(
                leading_dots - 1,
                0,
            )
        ):
            base = base.parent

        bases = [base]

    else:
        bases = []

        current = importer.parent

        while True:
            try:
                current.relative_to(
                    root_path
                )

            except ValueError:
                break

            bases.append(
                current
            )

            if current == root_path:
                break

            current = current.parent

    for base in bases:
        target = base.joinpath(
            *module_parts
        )

        candidates = [
            target.with_suffix(
                ".py"
            ),
            target / "__init__.py",
        ]

        for candidate in candidates:
            resolved = (
                _path_if_known(
                    candidate,
                    root_path,
                    known_paths,
                )
            )

            if resolved:
                return resolved

        #
        # Handles namespace-package style:
        #
        # from services import user_service
        #
        # where:
        #
        # services/user_service.py
        #
        # exists but services/__init__.py does not.
        #
        for imported_name in imported_names:
            if (
                imported_name == "*"
                or "." in imported_name
            ):
                continue

            child_target = (
                target / imported_name
            )

            child_candidates = [
                child_target.with_suffix(
                    ".py"
                ),
                (
                    child_target
                    / "__init__.py"
                ),
            ]

            for candidate in (
                child_candidates
            ):
                resolved = (
                    _path_if_known(
                        candidate,
                        root_path,
                        known_paths,
                    )
                )

                if resolved:
                    return resolved

    return None


def _resolve_js_module(
    module: str,
    file_path: str,
    language: str,
    root_path: Path,
    known_paths: set[str],
) -> str | None:

    if not module.startswith("."):
        return None

    importer = (
        root_path / file_path
    )

    target = (
        importer.parent / module
    )

    candidates = [target]

    extension_order = (
        JS_EXTENSIONS.get(
            language,
            JS_EXTENSIONS[
                "javascript"
            ],
        )
    )

    if target.suffix:
        #
        # TypeScript projects sometimes
        # import "./module.js" while the
        # source file is module.ts.
        #
        if target.suffix == ".js":
            candidates.extend(
                [
                    target.with_suffix(
                        ".ts"
                    ),
                    target.with_suffix(
                        ".tsx"
                    ),
                ]
            )

        elif target.suffix == ".mjs":
            candidates.append(
                target.with_suffix(
                    ".mts"
                )
            )

        elif target.suffix == ".cjs":
            candidates.append(
                target.with_suffix(
                    ".cts"
                )
            )

    else:
        for extension in (
            extension_order
        ):
            candidates.append(
                Path(
                    str(target)
                    + extension
                )
            )

        for extension in (
            extension_order
        ):
            candidates.append(
                target
                / (
                    "index"
                    + extension
                )
            )

        candidates.append(
            Path(
                str(target)
                + ".json"
            )
        )

    for candidate in candidates:
        resolved = _path_if_known(
            candidate,
            root_path,
            known_paths,
        )

        if resolved:
            return resolved

    return None


def _resolve_import(
    language: str,
    module: str,
    imported_names: list[str],
    file_path: str,
    root_path: Path,
    known_paths: set[str],
) -> str | None:

    if language == "python":
        return (
            _resolve_python_module(
                module=module,
                imported_names=(
                    imported_names
                ),
                file_path=file_path,
                root_path=root_path,
                known_paths=known_paths,
            )
        )

    if language in JS_LANGUAGES:
        return (
            _resolve_js_module(
                module=module,
                file_path=file_path,
                language=language,
                root_path=root_path,
                known_paths=known_paths,
            )
        )

    return None


def build_dependency_index(
    workspace_id: str,
) -> DependencyBuildResult:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:
        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    root_path = Path(
        workspace.path
    ).resolve()

    with get_database() as database:
        source_rows = database.execute(
            """
            SELECT
                path,
                language,
                sha256
            FROM repository_files
            WHERE workspace_id = ?
              AND is_source = 1
            ORDER BY path ASC
            """,
            (workspace_id,),
        ).fetchall()

        all_path_rows = (
            database.execute(
                """
                SELECT path
                FROM repository_files
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            ).fetchall()
        )

    if not source_rows:
        raise WorkspaceError(
            "No source files are indexed. "
            "Run repository scan first."
        )

    known_paths = {
        row["path"]
        for row in all_path_rows
    }

    indexed_at = datetime.now(
        timezone.utc
    ).isoformat()

    import_records = []

    files_with_imports = set()

    resolved_local_imports = 0
    unresolved_imports = 0

    skipped_unsupported = 0
    failed_files = 0

    language_counter = Counter()
    kind_counter = Counter()

    for row in source_rows:
        file_path = row["path"]
        language = row["language"]
        file_sha256 = row["sha256"]

        if not is_language_supported(
            language
        ):
            skipped_unsupported += 1
            continue

        absolute_path = (
            root_path / file_path
        )

        try:
            source = (
                absolute_path.read_bytes()
            )

            parser = get_parser(
                language
            )

            tree = parser.parse(
                source
            )

            if language == "python":
                discovered = (
                    _extract_python_imports(
                        tree.root_node,
                        source,
                    )
                )

            elif language in JS_LANGUAGES:
                discovered = (
                    _extract_js_imports(
                        tree.root_node,
                        source,
                    )
                )

            else:
                discovered = []

            if discovered:
                files_with_imports.add(
                    file_path
                )

            for record in discovered:
                resolved_file_path = (
                    _resolve_import(
                        language=language,
                        module=record[
                            "module"
                        ],
                        imported_names=(
                            record[
                                "imported_names"
                            ]
                        ),
                        file_path=file_path,
                        root_path=root_path,
                        known_paths=known_paths,
                    )
                )

                if resolved_file_path:
                    status = "local"

                    resolved_local_imports += 1

                else:
                    status = "unresolved"

                    unresolved_imports += 1

                language_counter[
                    language
                ] += 1

                kind_counter[
                    record["kind"]
                ] += 1

                import_records.append(
                    (
                        workspace_id,
                        file_path,
                        file_sha256,
                        language,
                        record["kind"],
                        record["module"],
                        json.dumps(
                            record[
                                "imported_names"
                            ]
                        ),
                        int(
                            record[
                                "is_relative"
                            ]
                        ),
                        resolved_file_path,
                        status,
                        record[
                            "start_line"
                        ],
                        record[
                            "end_line"
                        ],
                        record[
                            "raw_text"
                        ],
                    )
                )

        except Exception:
            failed_files += 1

    with get_database() as database:
        database.execute(
            """
            DELETE FROM code_imports
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )

        database.executemany(
            """
            INSERT INTO code_imports (
                workspace_id,
                file_path,
                file_sha256,
                language,
                kind,
                module,
                imported_names,
                is_relative,
                resolved_file_path,
                resolution_status,
                start_line,
                end_line,
                raw_text
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            """,
            import_records,
        )

    return DependencyBuildResult(
        workspace_id=workspace.id,
        workspace_name=workspace.name,

        source_files_seen=len(
            source_rows
        ),

        files_with_imports=len(
            files_with_imports
        ),

        total_imports=len(
            import_records
        ),

        resolved_local_imports=(
            resolved_local_imports
        ),

        unresolved_imports=(
            unresolved_imports
        ),

        skipped_unsupported=(
            skipped_unsupported
        ),

        failed_files=failed_files,

        languages=dict(
            language_counter.most_common()
        ),

        import_kinds=dict(
            kind_counter.most_common()
        ),

        indexed_at=indexed_at,
    )


def list_imports(
    workspace_id: str,
    query: str | None = None,
    file_path: str | None = None,
    local_only: bool = False,
    limit: int = 500,
) -> list[CodeImport]:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:
        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    sql = """
        SELECT
            id,
            file_path,
            language,
            kind,
            module,
            imported_names,
            is_relative,
            resolved_file_path,
            resolution_status,
            start_line,
            end_line,
            raw_text
        FROM code_imports
        WHERE workspace_id = ?
    """

    parameters = [
        workspace_id
    ]

    if query:
        sql += """
            AND (
                module LIKE ?
                OR raw_text LIKE ?
            )
        """

        search = f"%{query}%"

        parameters.extend(
            [
                search,
                search,
            ]
        )

    if file_path:
        sql += """
            AND file_path = ?
        """

        parameters.append(
            file_path
        )

    if local_only:
        sql += """
            AND resolved_file_path
                IS NOT NULL
        """

    sql += """
        ORDER BY
            file_path,
            start_line
        LIMIT ?
    """

    parameters.append(
        limit
    )

    with get_database() as database:
        rows = database.execute(
            sql,
            parameters,
        ).fetchall()

    return [
        CodeImport(
            id=row["id"],

            file_path=row[
                "file_path"
            ],

            language=row[
                "language"
            ],

            kind=row["kind"],

            module=row["module"],

            imported_names=json.loads(
                row[
                    "imported_names"
                ]
            ),

            is_relative=bool(
                row[
                    "is_relative"
                ]
            ),

            resolved_file_path=row[
                "resolved_file_path"
            ],

            resolution_status=row[
                "resolution_status"
            ],

            start_line=row[
                "start_line"
            ],

            end_line=row[
                "end_line"
            ],

            raw_text=row[
                "raw_text"
            ],
        )

        for row in rows
    ]


def list_dependencies(
    workspace_id: str,
    file_path: str | None = None,
    direction: str = "outgoing",
    limit: int = 500,
) -> list[DependencyEdge]:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:
        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    sql = """
        SELECT DISTINCT
            file_path,
            resolved_file_path,
            kind,
            module
        FROM code_imports

        WHERE workspace_id = ?

        AND resolved_file_path
            IS NOT NULL
    """

    parameters = [
        workspace_id
    ]

    if file_path:
        if direction == "outgoing":
            sql += """
                AND file_path = ?
            """

            parameters.append(
                file_path
            )

        elif direction == "incoming":
            sql += """
                AND resolved_file_path = ?
            """

            parameters.append(
                file_path
            )

        else:
            sql += """
                AND (
                    file_path = ?
                    OR resolved_file_path = ?
                )
            """

            parameters.extend(
                [
                    file_path,
                    file_path,
                ]
            )

    sql += """
        ORDER BY
            file_path,
            resolved_file_path
        LIMIT ?
    """

    parameters.append(
        limit
    )

    with get_database() as database:
        rows = database.execute(
            sql,
            parameters,
        ).fetchall()

    return [
        DependencyEdge(
            from_file=row[
                "file_path"
            ],

            to_file=row[
                "resolved_file_path"
            ],

            kind=row["kind"],

            module=row["module"],
        )

        for row in rows
    ]
