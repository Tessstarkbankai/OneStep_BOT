import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tree_sitter import Node

from indexing.models import (
    CodeRelation,
    RelationBuildResult,
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


RELATION_TARGET_KINDS = {
    "class",
    "interface",
    "trait",
    "enum",
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


def _node_name(
    node: Node,
    source: bytes,
) -> str | None:

    name_node = node.child_by_field_name(
        "name"
    )

    if name_node is None:
        return None

    value = _node_text(
        name_node,
        source,
    ).strip()

    return value or None


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


def _header_text(
    node: Node,
    source: bytes,
) -> str:

    body = node.child_by_field_name(
        "body"
    )

    if body is not None:
        end_byte = body.start_byte

    else:
        end_byte = min(
            node.end_byte,
            node.start_byte + 1500,
        )

    value = source[
        node.start_byte:end_byte
    ].decode(
        "utf-8",
        errors="replace",
    )

    return " ".join(
        value.split()
    )


def _clean_target(
    value: str,
) -> str:

    value = value.strip()

    value = re.sub(
        r"<.*>$",
        "",
        value,
    )

    value = re.sub(
        r"\[.*\]$",
        "",
        value,
    )

    return value.strip()


def _target_basename(
    value: str,
) -> str:

    value = _clean_target(
        value
    )

    value = value.lstrip("\\")

    if "\\" in value:
        value = value.split("\\")[-1]

    if "." in value:
        value = value.split(".")[-1]

    return value


def _split_targets(
    value: str,
) -> list[str]:

    targets = []

    for item in value.split(","):

        item = _clean_target(
            item
        )

        if item:
            targets.append(item)

    return targets


def _extract_python_relations(
    node: Node,
    source: bytes,
):

    if node.type != "class_definition":
        return []

    name = _node_name(
        node,
        source,
    )

    if not name:
        return []

    header = _header_text(
        node,
        source,
    )

    match = re.search(
        r"class\s+\w+\s*\((.*?)\)",
        header,
    )

    if not match:
        return []

    relations = []

    for base in _split_targets(
        match.group(1)
    ):

        if base.startswith(
            "metaclass="
        ):
            continue

        relations.append(
            {
                "source_symbol": name,
                "source_kind": "class",
                "relation_type": "extends",
                "target_text": base,
            }
        )

    return relations


def _extract_js_relations(
    node: Node,
    source: bytes,
):

    relations = []

    if node.type not in {
        "class_declaration",
        "interface_declaration",
    }:
        return relations

    name = _node_name(
        node,
        source,
    )

    if not name:
        return relations

    header = _header_text(
        node,
        source,
    )

    source_kind = (
        "interface"
        if node.type
        == "interface_declaration"
        else "class"
    )

    extends_match = re.search(
        r"\bextends\s+(.+?)"
        r"(?=\s+implements\b|$)",
        header,
    )

    if extends_match:

        for target in _split_targets(
            extends_match.group(1)
        ):

            relations.append(
                {
                    "source_symbol": name,
                    "source_kind": source_kind,
                    "relation_type": "extends",
                    "target_text": target,
                }
            )

    if source_kind == "class":

        implements_match = re.search(
            r"\bimplements\s+(.+)$",
            header,
        )

        if implements_match:

            for target in _split_targets(
                implements_match.group(1)
            ):

                relations.append(
                    {
                        "source_symbol": name,
                        "source_kind": "class",
                        "relation_type": "implements",
                        "target_text": target,
                    }
                )

    return relations


def _extract_php_relations(
    node: Node,
    source: bytes,
):

    relations = []

    if node.type not in {
        "class_declaration",
        "interface_declaration",
    }:
        return relations

    name = _node_name(
        node,
        source,
    )

    if not name:
        return relations

    header = _header_text(
        node,
        source,
    )

    source_kind = (
        "interface"
        if node.type
        == "interface_declaration"
        else "class"
    )

    extends_match = re.search(
        r"\bextends\s+"
        r"([\\A-Za-z_][\\\w]*)",
        header,
    )

    if extends_match:

        relations.append(
            {
                "source_symbol": name,
                "source_kind": source_kind,
                "relation_type": "extends",
                "target_text": (
                    extends_match.group(1)
                ),
            }
        )

    if source_kind == "class":

        implements_match = re.search(
            r"\bimplements\s+(.+)$",
            header,
        )

        if implements_match:

            for target in _split_targets(
                implements_match.group(1)
            ):

                relations.append(
                    {
                        "source_symbol": name,
                        "source_kind": "class",
                        "relation_type": "implements",
                        "target_text": target,
                    }
                )

        body = node.child_by_field_name(
            "body"
        )

        if body is not None:

            body_text = _node_text(
                body,
                source,
            )

            #
            # Trait declarations inside classes:
            #
            # use LogsActivity;
            #
            # Avoid closure syntax:
            #
            # function () use ($x)
            #
            trait_matches = re.finditer(
                r"(?m)^\s*use\s+"
                r"([\\A-Za-z_][^;(]*?)"
                r"\s*;",
                body_text,
            )

            for match in trait_matches:

                for target in _split_targets(
                    match.group(1)
                ):

                    relations.append(
                        {
                            "source_symbol": name,
                            "source_kind": "class",
                            "relation_type": "uses_trait",
                            "target_text": target,
                        }
                    )

    return relations


def _extract_relations(
    node: Node,
    source: bytes,
    language: str,
):

    if language == "python":

        return _extract_python_relations(
            node,
            source,
        )

    if language in JS_LANGUAGES:

        return _extract_js_relations(
            node,
            source,
        )

    if language == "php":

        return _extract_php_relations(
            node,
            source,
        )

    return []


def _candidate_files(
    file_path: str,
    dependency_map,
):

    result = [file_path]

    result.extend(
        sorted(
            dependency_map.get(
                file_path,
                set(),
            )
        )
    )

    return result


def _resolve_relation(
    file_path: str,
    target_text: str,
    symbols_by_file,
    dependency_map,
):

    target_name = (
        _target_basename(
            target_text
        )
    )

    candidates = []

    for candidate_file in (
        _candidate_files(
            file_path,
            dependency_map,
        )
    ):

        for symbol in (
            symbols_by_file.get(
                candidate_file,
                []
            )
        ):

            if (
                symbol["kind"]
                not in RELATION_TARGET_KINDS
            ):
                continue

            if symbol["name"] == target_name:

                candidates.append(
                    symbol
                )

    if len(candidates) == 1:

        symbol = candidates[0]

        return {
            "status": "local",

            "resolved_file_path": (
                symbol["file_path"]
            ),

            "resolved_symbol": (
                symbol["qualified_name"]
            ),

            "resolved_symbol_kind": (
                symbol["kind"]
            ),

            "resolution_method": (
                "symbol_dependency_lookup"
            ),

            "confidence": "high",
        }

    if len(candidates) > 1:

        return {
            "status": "ambiguous",

            "resolved_file_path": None,
            "resolved_symbol": None,
            "resolved_symbol_kind": None,

            "resolution_method": (
                "symbol_dependency_lookup"
            ),

            "confidence": "low",
        }

    return {
        "status": "unresolved",

        "resolved_file_path": None,
        "resolved_symbol": None,
        "resolved_symbol_kind": None,

        "resolution_method": None,
        "confidence": None,
    }


def build_relation_graph(
    workspace_id: str,
) -> RelationBuildResult:

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
            ORDER BY path
            """,
            (workspace_id,),
        ).fetchall()

        symbol_rows = database.execute(
            """
            SELECT
                file_path,
                kind,
                name,
                qualified_name
            FROM code_symbols
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()

        dependency_rows = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path
            FROM code_imports
            WHERE workspace_id = ?
              AND resolved_file_path
                  IS NOT NULL
            """,
            (workspace_id,),
        ).fetchall()

    symbols_by_file = defaultdict(
        list
    )

    for row in symbol_rows:

        symbols_by_file[
            row["file_path"]
        ].append(
            {
                "file_path": row[
                    "file_path"
                ],

                "kind": row["kind"],

                "name": row["name"],

                "qualified_name": row[
                    "qualified_name"
                ],
            }
        )

    dependency_map = defaultdict(
        set
    )

    for row in dependency_rows:

        dependency_map[
            row["file_path"]
        ].add(
            row[
                "resolved_file_path"
            ]
        )

    indexed_at = datetime.now(
        timezone.utc
    ).isoformat()

    relation_records = []

    parsed_files = 0
    failed_files = 0

    resolved_relations = 0
    unresolved_relations = 0
    ambiguous_relations = 0

    language_counter = Counter()
    relation_counter = Counter()

    for row in source_rows:

        file_path = row["path"]
        language = row["language"]
        file_sha256 = row["sha256"]

        if not is_language_supported(
            language
        ):
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

            parsed_files += 1

            for node in _walk_tree(
                tree.root_node
            ):

                discovered = (
                    _extract_relations(
                        node,
                        source,
                        language,
                    )
                )

                for relation in discovered:

                    resolution = (
                        _resolve_relation(
                            file_path=(
                                file_path
                            ),

                            target_text=(
                                relation[
                                    "target_text"
                                ]
                            ),

                            symbols_by_file=(
                                symbols_by_file
                            ),

                            dependency_map=(
                                dependency_map
                            ),
                        )
                    )

                    status = resolution[
                        "status"
                    ]

                    if status == "local":

                        resolved_relations += 1

                    elif status == "ambiguous":

                        ambiguous_relations += 1

                    else:

                        unresolved_relations += 1

                    relation_type = relation[
                        "relation_type"
                    ]

                    relation_counter[
                        relation_type
                    ] += 1

                    language_counter[
                        language
                    ] += 1

                    start_row, _ = (
                        node.start_point
                    )

                    relation_records.append(
                        (
                            workspace_id,

                            file_path,

                            file_sha256,

                            language,

                            relation[
                                "source_symbol"
                            ],

                            relation[
                                "source_kind"
                            ],

                            relation_type,

                            relation[
                                "target_text"
                            ],

                            resolution[
                                "resolved_file_path"
                            ],

                            resolution[
                                "resolved_symbol"
                            ],

                            resolution[
                                "resolved_symbol_kind"
                            ],

                            status,

                            resolution[
                                "resolution_method"
                            ],

                            resolution[
                                "confidence"
                            ],

                            start_row + 1,
                        )
                    )

        except Exception:

            failed_files += 1

    with get_database() as database:

        database.execute(
            """
            DELETE FROM code_relations
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )

        database.executemany(
            """
            INSERT INTO code_relations (
                workspace_id,
                file_path,
                file_sha256,
                language,
                source_symbol,
                source_kind,
                relation_type,
                target_text,
                resolved_file_path,
                resolved_symbol,
                resolved_symbol_kind,
                resolution_status,
                resolution_method,
                confidence,
                start_line
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            relation_records,
        )

    return RelationBuildResult(
        workspace_id=workspace.id,

        workspace_name=workspace.name,

        source_files_seen=len(
            source_rows
        ),

        parsed_files=parsed_files,

        total_relations=len(
            relation_records
        ),

        resolved_relations=(
            resolved_relations
        ),

        unresolved_relations=(
            unresolved_relations
        ),

        ambiguous_relations=(
            ambiguous_relations
        ),

        extends_relations=(
            relation_counter[
                "extends"
            ]
        ),

        implements_relations=(
            relation_counter[
                "implements"
            ]
        ),

        trait_relations=(
            relation_counter[
                "uses_trait"
            ]
        ),

        failed_files=failed_files,

        languages=dict(
            language_counter.most_common()
        ),

        relation_types=dict(
            relation_counter.most_common()
        ),

        indexed_at=indexed_at,
    )


def list_relations(
    workspace_id: str,

    symbol: str | None = None,

    target: str | None = None,

    relation_type: str | None = None,

    resolved_only: bool = False,

    limit: int = 500,
) -> list[CodeRelation]:

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
            source_symbol,
            source_kind,
            relation_type,
            target_text,
            resolved_file_path,
            resolved_symbol,
            resolved_symbol_kind,
            resolution_status,
            resolution_method,
            confidence,
            start_line
        FROM code_relations
        WHERE workspace_id = ?
    """

    parameters = [
        workspace_id
    ]

    if symbol:

        sql += """
            AND source_symbol LIKE ?
        """

        parameters.append(
            f"%{symbol}%"
        )

    if target:

        sql += """
            AND (
                target_text LIKE ?
                OR resolved_symbol LIKE ?
            )
        """

        search = f"%{target}%"

        parameters.extend(
            [
                search,
                search,
            ]
        )

    if relation_type:

        sql += """
            AND relation_type = ?
        """

        parameters.append(
            relation_type
        )

    if resolved_only:

        sql += """
            AND resolution_status = 'local'
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
        CodeRelation(
            id=row["id"],

            file_path=row[
                "file_path"
            ],

            language=row[
                "language"
            ],

            source_symbol=row[
                "source_symbol"
            ],

            source_kind=row[
                "source_kind"
            ],

            relation_type=row[
                "relation_type"
            ],

            target_text=row[
                "target_text"
            ],

            resolved_file_path=row[
                "resolved_file_path"
            ],

            resolved_symbol=row[
                "resolved_symbol"
            ],

            resolved_symbol_kind=row[
                "resolved_symbol_kind"
            ],

            resolution_status=row[
                "resolution_status"
            ],

            resolution_method=row[
                "resolution_method"
            ],

            confidence=row[
                "confidence"
            ],

            start_line=row[
                "start_line"
            ],
        )

        for row in rows
    ]
