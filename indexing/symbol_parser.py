from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tree_sitter import Node

from indexing.models import CodeSymbol, ParseResult
from indexing.parser_registry import (
    is_language_supported,
    get_parser,
)
from storage.database import get_database
from workspace.manager import WorkspaceError, get_workspace


PYTHON_SYMBOL_TYPES = {
    "function_definition",
    "class_definition",
}


JAVASCRIPT_SYMBOL_TYPES = {
    "function_declaration",
    "generator_function_declaration",
    "class_declaration",
    "method_definition",
    "variable_declarator",
}


TYPESCRIPT_EXTRA_SYMBOL_TYPES = {
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
}


FUNCTION_VALUE_TYPES = {
    "arrow_function",
    "function_expression",
    "generator_function",
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


def _get_name_node(node: Node):
    return node.child_by_field_name(
        "name"
    )


def _get_node_name(
    node: Node,
    source: bytes,
) -> str | None:
    name_node = _get_name_node(node)

    if name_node is None:
        return None

    name = _node_text(
        name_node,
        source,
    ).strip()

    if not name:
        return None

    return name


def _build_signature(
    node: Node,
    source: bytes,
) -> str | None:
    body_node = node.child_by_field_name(
        "body"
    )

    if body_node is not None:
        end_byte = body_node.start_byte
    else:
        end_byte = min(
            node.end_byte,
            node.start_byte + 800,
        )

    raw = source[
        node.start_byte:end_byte
    ].decode(
        "utf-8",
        errors="replace",
    )

    signature = " ".join(
        raw.split()
    )

    if not signature:
        return None

    if len(signature) > 500:
        signature = (
            signature[:497] + "..."
        )

    return signature


def _classify_symbol(
    node: Node,
    language: str,
    parent_kind: str | None,
) -> tuple[str, str] | None:

    node_type = node.type

    if language == "python":
        if node_type == "class_definition":
            return "class", node_type

        if node_type == "function_definition":
            if parent_kind == "class":
                return "method", node_type

            return "function", node_type

        return None

    if language in {
        "javascript",
        "typescript",
        "tsx",
    }:
        if node_type == "class_declaration":
            return "class", node_type

        if node_type in {
            "function_declaration",
            "generator_function_declaration",
        }:
            return "function", node_type

        if node_type == "method_definition":
            return "method", node_type

        if node_type == "interface_declaration":
            return "interface", node_type

        if node_type == "type_alias_declaration":
            return "type_alias", node_type

        if node_type == "enum_declaration":
            return "enum", node_type

        if node_type == "variable_declarator":
            value_node = (
                node.child_by_field_name(
                    "value"
                )
            )

            if (
                value_node is not None
                and value_node.type
                in FUNCTION_VALUE_TYPES
            ):
                return "function", node_type

    return None


def _extract_symbols(
    root_node: Node,
    source: bytes,
    language: str,
    file_path: str,
    file_sha256: str,
):
    symbols = []

    def walk(
        node: Node,
        parent_symbol: str | None = None,
        parent_kind: str | None = None,
    ):
        symbol_info = _classify_symbol(
            node=node,
            language=language,
            parent_kind=parent_kind,
        )

        next_parent_symbol = parent_symbol
        next_parent_kind = parent_kind

        if symbol_info is not None:
            kind, _ = symbol_info

            name = _get_node_name(
                node,
                source,
            )

            if name:
                if parent_symbol:
                    qualified_name = (
                        f"{parent_symbol}.{name}"
                    )
                else:
                    qualified_name = name

                start_row, start_column = (
                    node.start_point
                )

                end_row, end_column = (
                    node.end_point
                )

                symbols.append(
                    {
                        "file_path": file_path,
                        "file_sha256": file_sha256,
                        "language": language,
                        "kind": kind,
                        "name": name,
                        "qualified_name": qualified_name,
                        "parent_symbol": parent_symbol,
                        "start_line": start_row + 1,
                        "end_line": end_row + 1,
                        "start_column": start_column,
                        "end_column": end_column,
                        "signature": _build_signature(
                            node,
                            source,
                        ),
                    }
                )

                next_parent_symbol = (
                    qualified_name
                )

                next_parent_kind = kind

        for child in node.named_children:
            walk(
                child,
                next_parent_symbol,
                next_parent_kind,
            )

    walk(root_node)

    return symbols


def _count_error_nodes(
    root_node: Node,
) -> int:
    count = 0

    stack = [root_node]

    while stack:
        node = stack.pop()

        if node.type == "ERROR":
            count += 1

        stack.extend(
            node.named_children
        )

    if root_node.has_error and count == 0:
        count = 1

    return count


def parse_workspace(
    workspace_id: str,
) -> ParseResult:

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
        file_rows = database.execute(
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

    if not file_rows:
        raise WorkspaceError(
            "No source files are indexed. "
            "Run repository scan first."
        )

    parsed_at = datetime.now(
        timezone.utc
    ).isoformat()

    all_symbols = []
    parse_statuses = []

    language_counter = Counter()
    symbol_counter = Counter()

    parsed_files = 0
    skipped_unsupported = 0
    failed_files = 0

    files_with_syntax_errors = 0

    for row in file_rows:
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
        ).resolve()

        try:
            absolute_path.relative_to(
                root_path
            )

        except ValueError:
            failed_files += 1
            continue

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

            root_node = (
                tree.root_node
            )

            error_count = (
                _count_error_nodes(
                    root_node
                )
            )

            if root_node.has_error:
                files_with_syntax_errors += 1

            symbols = _extract_symbols(
                root_node=root_node,
                source=source,
                language=language,
                file_path=file_path,
                file_sha256=file_sha256,
            )

            all_symbols.extend(
                symbols
            )

            for symbol in symbols:
                symbol_counter[
                    symbol["kind"]
                ] += 1

            language_counter[
                language
            ] += 1

            parsed_files += 1

            parse_statuses.append(
                (
                    workspace_id,
                    file_path,
                    file_sha256,
                    language,
                    1,
                    error_count,
                    None,
                    parsed_at,
                )
            )

        except Exception as error:
            failed_files += 1

            parse_statuses.append(
                (
                    workspace_id,
                    file_path,
                    file_sha256,
                    language,
                    0,
                    0,
                    str(error)[:1000],
                    parsed_at,
                )
            )

    with get_database() as database:
        database.execute(
            """
            DELETE FROM code_symbols
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )

        database.execute(
            """
            DELETE FROM file_parse_status
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )

        database.executemany(
            """
            INSERT INTO code_symbols (
                workspace_id,
                file_path,
                file_sha256,
                language,
                kind,
                name,
                qualified_name,
                parent_symbol,
                start_line,
                end_line,
                start_column,
                end_column,
                signature
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            """,
            [
                (
                    workspace_id,
                    symbol["file_path"],
                    symbol["file_sha256"],
                    symbol["language"],
                    symbol["kind"],
                    symbol["name"],
                    symbol["qualified_name"],
                    symbol["parent_symbol"],
                    symbol["start_line"],
                    symbol["end_line"],
                    symbol["start_column"],
                    symbol["end_column"],
                    symbol["signature"],
                )
                for symbol in all_symbols
            ],
        )

        database.executemany(
            """
            INSERT INTO file_parse_status (
                workspace_id,
                file_path,
                file_sha256,
                language,
                parse_ok,
                error_count,
                error_message,
                parsed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            parse_statuses,
        )

    return ParseResult(
        workspace_id=workspace.id,
        workspace_name=workspace.name,

        total_source_files=len(
            file_rows
        ),

        parsed_files=parsed_files,

        skipped_unsupported=(
            skipped_unsupported
        ),

        failed_files=failed_files,

        files_with_syntax_errors=(
            files_with_syntax_errors
        ),

        symbols_extracted=len(
            all_symbols
        ),

        languages=dict(
            language_counter.most_common()
        ),

        symbol_kinds=dict(
            symbol_counter.most_common()
        ),

        parsed_at=parsed_at,
    )


def list_symbols(
    workspace_id: str,
    query: str | None = None,
    kind: str | None = None,
    file_path: str | None = None,
    limit: int = 500,
) -> list[CodeSymbol]:

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
            name,
            qualified_name,
            parent_symbol,
            start_line,
            end_line,
            start_column,
            end_column,
            signature
        FROM code_symbols
        WHERE workspace_id = ?
    """

    parameters = [
        workspace_id
    ]

    if query:
        sql += """
            AND (
                name LIKE ?
                OR qualified_name LIKE ?
            )
        """

        search_value = (
            f"%{query}%"
        )

        parameters.extend(
            [
                search_value,
                search_value,
            ]
        )

    if kind:
        sql += """
            AND kind = ?
        """

        parameters.append(
            kind
        )

    if file_path:
        sql += """
            AND file_path = ?
        """

        parameters.append(
            file_path
        )

    sql += """
        ORDER BY
            file_path ASC,
            start_line ASC
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
        CodeSymbol(
            id=row["id"],

            file_path=row[
                "file_path"
            ],

            language=row[
                "language"
            ],

            kind=row["kind"],

            name=row["name"],

            qualified_name=row[
                "qualified_name"
            ],

            parent_symbol=row[
                "parent_symbol"
            ],

            start_line=row[
                "start_line"
            ],

            end_line=row[
                "end_line"
            ],

            start_column=row[
                "start_column"
            ],

            end_column=row[
                "end_column"
            ],

            signature=row[
                "signature"
            ],
        )

        for row in rows
    ]
