import re

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tree_sitter import Node

from indexing.models import (
    CallGraphBuildResult,
    CodeCall,
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


JS_FUNCTION_VALUES = {
    "arrow_function",
    "function_expression",
    "generator_function",
}


CALLABLE_KINDS = {
    "function",
    "method",
}


CLASS_KINDS = {
    "class",
    "interface",
    "trait",
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


def _get_name(
    node: Node,
    source: bytes,
) -> str | None:

    name_node = (
        node.child_by_field_name(
            "name"
        )
    )

    if name_node is None:
        return None

    value = _node_text(
        name_node,
        source,
    ).strip()

    return value or None


def _clean_callee(
    value: str,
) -> str:

    value = " ".join(
        value.split()
    )

    return value.strip()


def _class_basename(
    value: str,
) -> str:

    value = value.strip()

    value = value.lstrip("\\")

    if "\\" in value:
        value = value.split("\\")[-1]

    return value


def _definition_context(
    node: Node,
    source: bytes,
    language: str,
    parent_symbol: str | None,
    current_class: str | None,
):
    """
    Returns:

    (
        new_parent_symbol,
        new_current_class,
        definition_detected
    )
    """

    node_type = node.type

    #
    # Python
    #
    if language == "python":

        if node_type == "class_definition":

            name = _get_name(
                node,
                source,
            )

            if name:
                qualified = (
                    f"{parent_symbol}.{name}"
                    if parent_symbol
                    else name
                )

                return (
                    parent_symbol,
                    qualified,
                    True,
                )

        if node_type == "function_definition":

            name = _get_name(
                node,
                source,
            )

            if name:

                if current_class:
                    qualified = (
                        f"{current_class}.{name}"
                    )

                elif parent_symbol:
                    qualified = (
                        f"{parent_symbol}.{name}"
                    )

                else:
                    qualified = name

                return (
                    qualified,
                    current_class,
                    True,
                )

    #
    # JavaScript / TypeScript
    #
    if language in JS_LANGUAGES:

        if node_type == "class_declaration":

            name = _get_name(
                node,
                source,
            )

            if name:

                qualified = (
                    f"{parent_symbol}.{name}"
                    if parent_symbol
                    else name
                )

                return (
                    parent_symbol,
                    qualified,
                    True,
                )

        if node_type in {
            "function_declaration",
            "generator_function_declaration",
        }:

            name = _get_name(
                node,
                source,
            )

            if name:

                qualified = (
                    f"{parent_symbol}.{name}"
                    if parent_symbol
                    else name
                )

                return (
                    qualified,
                    current_class,
                    True,
                )

        if node_type == "method_definition":

            name = _get_name(
                node,
                source,
            )

            if name:

                if current_class:
                    qualified = (
                        f"{current_class}.{name}"
                    )

                else:
                    qualified = name

                return (
                    qualified,
                    current_class,
                    True,
                )

        if node_type == "variable_declarator":

            value_node = (
                node.child_by_field_name(
                    "value"
                )
            )

            if (
                value_node is not None
                and value_node.type
                in JS_FUNCTION_VALUES
            ):
                name_node = (
                    node.child_by_field_name(
                        "name"
                    )
                )

                if name_node is not None:

                    name = _node_text(
                        name_node,
                        source,
                    ).strip()

                    if name:

                        qualified = (
                            f"{parent_symbol}.{name}"
                            if parent_symbol
                            else name
                        )

                        return (
                            qualified,
                            current_class,
                            True,
                        )

    #
    # PHP
    #
    if language == "php":

        if node_type in {
            "class_declaration",
            "interface_declaration",
            "trait_declaration",
            "enum_declaration",
        }:

            name = _get_name(
                node,
                source,
            )

            if name:

                qualified = (
                    f"{parent_symbol}.{name}"
                    if parent_symbol
                    else name
                )

                return (
                    parent_symbol,
                    qualified,
                    True,
                )

        if node_type == "function_definition":

            name = _get_name(
                node,
                source,
            )

            if name:

                qualified = (
                    f"{parent_symbol}.{name}"
                    if parent_symbol
                    else name
                )

                return (
                    qualified,
                    current_class,
                    True,
                )

        if node_type == "method_declaration":

            name = _get_name(
                node,
                source,
            )

            if name:

                if current_class:
                    qualified = (
                        f"{current_class}.{name}"
                    )

                else:
                    qualified = name

                return (
                    qualified,
                    current_class,
                    True,
                )

    return (
        parent_symbol,
        current_class,
        False,
    )


def _extract_python_call(
    node: Node,
    source: bytes,
):

    if node.type != "call":
        return None

    function_node = (
        node.child_by_field_name(
            "function"
        )
    )

    if function_node is None:
        return None

    callee = _node_text(
        function_node,
        source,
    ).strip()

    if not callee:
        return None

    if "." in callee:
        call_kind = "method"

    else:
        call_kind = "function"

    return {
        "callee_text": callee,
        "call_kind": call_kind,
    }


def _extract_js_call(
    node: Node,
    source: bytes,
):

    if node.type == "call_expression":

        function_node = (
            node.child_by_field_name(
                "function"
            )
        )

        if function_node is None:
            return None

        callee = _node_text(
            function_node,
            source,
        ).strip()

        if not callee:
            return None

        if "." in callee:
            call_kind = "method"

        else:
            call_kind = "function"

        return {
            "callee_text": callee,
            "call_kind": call_kind,
        }

    if node.type == "new_expression":

        constructor_node = (
            node.child_by_field_name(
                "constructor"
            )
        )

        if constructor_node is not None:

            callee = _node_text(
                constructor_node,
                source,
            ).strip()

        else:

            raw = _node_text(
                node,
                source,
            )

            match = re.match(
                r"\s*new\s+([A-Za-z_$][\w$]*)",
                raw,
            )

            if not match:
                return None

            callee = match.group(1)

        return {
            "callee_text": callee,
            "call_kind": "constructor",
        }

    return None


def _extract_php_call(
    node: Node,
    source: bytes,
):

    raw = _node_text(
        node,
        source,
    ).strip()

    if node.type == "object_creation_expression":

        match = re.match(
            r"new\s+\\?([\w\\]+)",
            raw,
        )

        if not match:
            return None

        return {
            "callee_text": (
                match.group(1)
            ),
            "call_kind": "constructor",
        }

    if node.type == "scoped_call_expression":

        match = re.match(
            r"\s*\\?([\w\\]+)"
            r"::"
            r"([A-Za-z_]\w*)"
            r"\s*\(",
            raw,
        )

        if not match:
            return None

        return {
            "callee_text": (
                f"{match.group(1)}"
                f"::{match.group(2)}"
            ),
            "call_kind": "method",
        }

    if node.type == "member_call_expression":

        match = re.match(
            r"\s*(.+?)"
            r"->"
            r"([A-Za-z_]\w*)"
            r"\s*\(",
            raw,
        )

        if not match:
            return None

        return {
            "callee_text": (
                f"{match.group(1)}"
                f"->{match.group(2)}"
            ),
            "call_kind": "method",
        }

    if node.type == "function_call_expression":

        match = re.match(
            r"\s*\\?([\w\\]+)"
            r"\s*\(",
            raw,
        )

        if not match:
            return None

        return {
            "callee_text": (
                match.group(1)
            ),
            "call_kind": "function",
        }

    return None


def _extract_call(
    node: Node,
    source: bytes,
    language: str,
):

    if language == "python":
        return _extract_python_call(
            node,
            source,
        )

    if language in JS_LANGUAGES:
        return _extract_js_call(
            node,
            source,
        )

    if language == "php":
        return _extract_php_call(
            node,
            source,
        )

    return None


def _extract_binding(
    node: Node,
    source: bytes,
    language: str,
):
    """
    Detect simple object bindings such as:

    service = UserService()

    const pricing = new PricingService()

    $service = new CustomerService();

    $this->customers = new CustomerService();
    """

    raw = _node_text(
        node,
        source,
    )

    if language == "python":

        if node.type != "assignment":
            return None

        match = re.match(
            r"\s*"
            r"((?:self\.)?"
            r"[A-Za-z_]\w*)"
            r"\s*=\s*"
            r"([A-Za-z_]\w*)"
            r"\s*\(",
            raw,
        )

        if not match:
            return None

        return (
            match.group(1),
            match.group(2),
        )

    if language in JS_LANGUAGES:

        if node.type not in {
            "variable_declarator",
            "assignment_expression",
        }:
            return None

        match = re.match(
            r"\s*"
            r"((?:this\.)?"
            r"[A-Za-z_$][\w$]*)"
            r"\s*=\s*"
            r"new\s+"
            r"([A-Za-z_$][\w$]*)",
            raw,
        )

        if not match:
            return None

        return (
            match.group(1),
            match.group(2),
        )

    if language == "php":

        if node.type != "assignment_expression":
            return None

        match = re.match(
            r"\s*"
            r"("
            r"\$this->[A-Za-z_]\w*"
            r"|"
            r"\$[A-Za-z_]\w*"
            r")"
            r"\s*=\s*"
            r"new\s+\\?"
            r"([\w\\]+)",
            raw,
        )

        if not match:
            return None

        return (
            match.group(1),
            _class_basename(
                match.group(2)
            ),
        )

    return None


def _collect_file_calls(
    root_node: Node,
    source: bytes,
    language: str,
):

    calls = []

    bindings_by_scope = (
        defaultdict(dict)
    )

    def walk(
        node: Node,
        current_caller: str | None,
        current_class: str | None,
    ):

        next_caller = (
            current_caller
        )

        next_class = (
            current_class
        )

        (
            definition_caller,
            definition_class,
            definition_detected,
        ) = _definition_context(
            node=node,
            source=source,
            language=language,
            parent_symbol=current_caller,
            current_class=current_class,
        )

        if definition_detected:

            next_caller = (
                definition_caller
            )

            next_class = (
                definition_class
            )

        binding = _extract_binding(
            node,
            source,
            language,
        )

        if binding:

            variable_name, class_name = (
                binding
            )

            scope_key = (
                next_caller
                or "__module__"
            )

            bindings_by_scope[
                scope_key
            ][variable_name] = (
                class_name
            )

            #
            # Class property bindings such as:
            #
            # self.service
            # this.service
            # $this->service
            #
            # should be visible to all methods
            # of the class.
            #
            if (
                next_class
                and (
                    variable_name.startswith(
                        "self."
                    )
                    or variable_name.startswith(
                        "this."
                    )
                    or variable_name.startswith(
                        "$this->"
                    )
                )
            ):

                class_scope = (
                    f"__class__:"
                    f"{next_class}"
                )

                bindings_by_scope[
                    class_scope
                ][variable_name] = (
                    class_name
                )

        call = _extract_call(
            node,
            source,
            language,
        )

        if call:

            start_row, _ = (
                node.start_point
            )

            end_row, _ = (
                node.end_point
            )

            calls.append(
                {
                    "caller_symbol": (
                        next_caller
                    ),

                    "caller_class": (
                        next_class
                    ),

                    "callee_text": (
                        _clean_callee(
                            call[
                                "callee_text"
                            ]
                        )
                    ),

                    "call_kind": (
                        call[
                            "call_kind"
                        ]
                    ),

                    "start_line": (
                        start_row + 1
                    ),

                    "end_line": (
                        end_row + 1
                    ),
                }
            )

        for child in node.named_children:

            walk(
                child,
                next_caller,
                next_class,
            )

    walk(
        root_node,
        None,
        None,
    )

    return (
        calls,
        bindings_by_scope,
    )


def _candidate_files(
    file_path: str,
    dependency_map: dict[
        str,
        set[str]
    ],
):

    files = [
        file_path
    ]

    files.extend(
        sorted(
            dependency_map.get(
                file_path,
                set(),
            )
        )
    )

    return files


def _find_symbol_candidates(
    files: list[str],
    symbols_by_file: dict,
    name: str | None = None,
    qualified_name: str | None = None,
    kinds: set[str] | None = None,
):

    candidates = []

    for file_path in files:

        for symbol in (
            symbols_by_file.get(
                file_path,
                []
            )
        ):

            if (
                kinds
                and symbol["kind"]
                not in kinds
            ):
                continue

            if (
                qualified_name
                and symbol[
                    "qualified_name"
                ] == qualified_name
            ):
                candidates.append(
                    symbol
                )

                continue

            if (
                name
                and symbol["name"]
                == name
            ):
                candidates.append(
                    symbol
                )

    return candidates


def _resolve_single_candidate(
    candidates: list[dict],
    method: str,
    confidence: str,
):

    if len(candidates) == 1:

        symbol = candidates[0]

        return {
            "status": "local",

            "resolved_file_path": (
                symbol["file_path"]
            ),

            "resolved_symbol": (
                symbol[
                    "qualified_name"
                ]
            ),

            "resolved_symbol_kind": (
                symbol["kind"]
            ),

            "resolution_method": (
                method
            ),

            "confidence": confidence,
        }

    if len(candidates) > 1:

        return {
            "status": "ambiguous",

            "resolved_file_path": None,
            "resolved_symbol": None,
            "resolved_symbol_kind": None,

            "resolution_method": (
                method
            ),

            "confidence": "low",
        }

    return None


def _lookup_binding(
    callee_object: str,
    caller_symbol: str | None,
    caller_class: str | None,
    bindings_by_scope,
):

    if caller_symbol:

        scoped = (
            bindings_by_scope.get(
                caller_symbol,
                {}
            )
        )

        if callee_object in scoped:

            return scoped[
                callee_object
            ]

    if caller_class:

        class_scope = (
            f"__class__:"
            f"{caller_class}"
        )

        scoped = (
            bindings_by_scope.get(
                class_scope,
                {}
            )
        )

        if callee_object in scoped:

            return scoped[
                callee_object
            ]

    module_bindings = (
        bindings_by_scope.get(
            "__module__",
            {}
        )
    )

    return module_bindings.get(
        callee_object
    )


def _resolve_call(
    call: dict,
    file_path: str,
    symbols_by_file: dict,
    dependency_map: dict,
    bindings_by_scope,
):

    callee = call[
        "callee_text"
    ]

    call_kind = call[
        "call_kind"
    ]

    caller_symbol = call[
        "caller_symbol"
    ]

    caller_class = call[
        "caller_class"
    ]

    files = _candidate_files(
        file_path,
        dependency_map,
    )

    #
    # Constructor calls
    #
    if call_kind == "constructor":

        class_name = (
            _class_basename(
                callee
            )
        )

        candidates = (
            _find_symbol_candidates(
                files=files,
                symbols_by_file=(
                    symbols_by_file
                ),
                name=class_name,
                kinds=CLASS_KINDS,
            )
        )

        result = (
            _resolve_single_candidate(
                candidates,
                "constructor_class_lookup",
                "high",
            )
        )

        if result:
            return result

    #
    # Python / JS:
    #
    # self.method
    # this.method
    #
    if "." in callee:

        object_name, method_name = (
            callee.rsplit(
                ".",
                1,
            )
        )

        if (
            object_name
            in {
                "self",
                "this",
            }
            and caller_class
        ):

            qualified = (
                f"{caller_class}"
                f".{method_name}"
            )

            candidates = (
                _find_symbol_candidates(
                    files=[file_path],
                    symbols_by_file=(
                        symbols_by_file
                    ),
                    qualified_name=(
                        qualified
                    ),
                    kinds={"method"},
                )
            )

            result = (
                _resolve_single_candidate(
                    candidates,
                    "current_class_method",
                    "high",
                )
            )

            if result:
                return result

        class_name = _lookup_binding(
            object_name,
            caller_symbol,
            caller_class,
            bindings_by_scope,
        )

        if class_name:

            qualified = (
                f"{class_name}"
                f".{method_name}"
            )

            candidates = (
                _find_symbol_candidates(
                    files=files,
                    symbols_by_file=(
                        symbols_by_file
                    ),
                    qualified_name=(
                        qualified
                    ),
                    kinds={"method"},
                )
            )

            result = (
                _resolve_single_candidate(
                    candidates,
                    "instance_binding",
                    "high",
                )
            )

            if result:
                return result

        #
        # Static-like class.member
        #
        qualified = (
            f"{object_name}"
            f".{method_name}"
        )

        candidates = (
            _find_symbol_candidates(
                files=files,
                symbols_by_file=(
                    symbols_by_file
                ),
                qualified_name=(
                    qualified
                ),
                kinds={"method"},
            )
        )

        result = (
            _resolve_single_candidate(
                candidates,
                "qualified_method",
                "medium",
            )
        )

        if result:
            return result

    #
    # PHP:
    #
    # $this->method
    # $service->method
    # Class::method
    #
    if "->" in callee:

        object_name, method_name = (
            callee.rsplit(
                "->",
                1,
            )
        )

        if (
            object_name == "$this"
            and caller_class
        ):

            qualified = (
                f"{caller_class}"
                f".{method_name}"
            )

            candidates = (
                _find_symbol_candidates(
                    files=[file_path],
                    symbols_by_file=(
                        symbols_by_file
                    ),
                    qualified_name=(
                        qualified
                    ),
                    kinds={"method"},
                )
            )

            result = (
                _resolve_single_candidate(
                    candidates,
                    "current_class_method",
                    "high",
                )
            )

            if result:
                return result

        class_name = _lookup_binding(
            object_name,
            caller_symbol,
            caller_class,
            bindings_by_scope,
        )

        if class_name:

            class_name = (
                _class_basename(
                    class_name
                )
            )

            qualified = (
                f"{class_name}"
                f".{method_name}"
            )

            candidates = (
                _find_symbol_candidates(
                    files=files,
                    symbols_by_file=(
                        symbols_by_file
                    ),
                    qualified_name=(
                        qualified
                    ),
                    kinds={"method"},
                )
            )

            result = (
                _resolve_single_candidate(
                    candidates,
                    "instance_binding",
                    "high",
                )
            )

            if result:
                return result

    if "::" in callee:

        class_name, method_name = (
            callee.rsplit(
                "::",
                1,
            )
        )

        class_name = (
            _class_basename(
                class_name
            )
        )

        qualified = (
            f"{class_name}"
            f".{method_name}"
        )

        candidates = (
            _find_symbol_candidates(
                files=files,
                symbols_by_file=(
                    symbols_by_file
                ),
                qualified_name=(
                    qualified
                ),
                kinds={"method"},
            )
        )

        result = (
            _resolve_single_candidate(
                candidates,
                "static_method",
                "high",
            )
        )

        if result:
            return result

    #
    # Direct function / class call.
    #
    simple_name = (
        _class_basename(
            callee
        )
    )

    candidates = (
        _find_symbol_candidates(
            files=files,
            symbols_by_file=(
                symbols_by_file
            ),
            name=simple_name,
            kinds=CALLABLE_KINDS,
        )
    )

    result = (
        _resolve_single_candidate(
            candidates,
            "direct_symbol_lookup",
            "high",
        )
    )

    if result:
        return result

    #
    # A Python call such as:
    #
    # UserService()
    #
    # is parsed as an ordinary call,
    # rather than a dedicated constructor
    # expression.
    #
    candidates = (
        _find_symbol_candidates(
            files=files,
            symbols_by_file=(
                symbols_by_file
            ),
            name=simple_name,
            kinds=CLASS_KINDS,
        )
    )

    result = (
        _resolve_single_candidate(
            candidates,
            "class_call_lookup",
            "medium",
        )
    )

    if result:
        return result

    return {
        "status": "unresolved",

        "resolved_file_path": None,
        "resolved_symbol": None,
        "resolved_symbol_kind": None,

        "resolution_method": None,
        "confidence": None,
    }


def build_call_graph(
    workspace_id: str,
) -> CallGraphBuildResult:

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

        source_rows = (
            database.execute(
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
        )

        symbol_rows = (
            database.execute(
                """
                SELECT
                    file_path,
                    language,
                    kind,
                    name,
                    qualified_name
                FROM code_symbols
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            ).fetchall()
        )

        dependency_rows = (
            database.execute(
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
        )

    if not source_rows:

        raise WorkspaceError(
            "No source files indexed. "
            "Run repository scan first."
        )

    if not symbol_rows:

        raise WorkspaceError(
            "No code symbols indexed. "
            "Run parse first."
        )

    symbols_by_file = (
        defaultdict(list)
    )

    for row in symbol_rows:

        symbols_by_file[
            row["file_path"]
        ].append(
            {
                "file_path": (
                    row["file_path"]
                ),
                "language": (
                    row["language"]
                ),
                "kind": row["kind"],
                "name": row["name"],
                "qualified_name": (
                    row[
                        "qualified_name"
                    ]
                ),
            }
        )

    dependency_map = (
        defaultdict(set)
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

    call_records = []

    language_counter = Counter()

    parsed_files = 0

    skipped_unsupported = 0
    failed_files = 0

    resolved_calls = 0
    unresolved_calls = 0
    ambiguous_calls = 0

    constructor_calls = 0
    method_calls = 0
    function_calls = 0

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

            (
                calls,
                bindings_by_scope,
            ) = _collect_file_calls(
                tree.root_node,
                source,
                language,
            )

            parsed_files += 1

            if calls:

                language_counter[
                    language
                ] += len(calls)

            for call in calls:

                result = _resolve_call(
                    call=call,
                    file_path=file_path,
                    symbols_by_file=(
                        symbols_by_file
                    ),
                    dependency_map=(
                        dependency_map
                    ),
                    bindings_by_scope=(
                        bindings_by_scope
                    ),
                )

                status = (
                    result["status"]
                )

                if status == "local":
                    resolved_calls += 1

                elif status == "ambiguous":
                    ambiguous_calls += 1

                else:
                    unresolved_calls += 1

                if (
                    call["call_kind"]
                    == "constructor"
                ):
                    constructor_calls += 1

                elif (
                    call["call_kind"]
                    == "method"
                ):
                    method_calls += 1

                else:
                    function_calls += 1

                call_records.append(
                    (
                        workspace_id,

                        file_path,

                        file_sha256,

                        language,

                        call[
                            "caller_symbol"
                        ],

                        call[
                            "caller_class"
                        ],

                        call[
                            "callee_text"
                        ],

                        call[
                            "call_kind"
                        ],

                        result[
                            "resolved_file_path"
                        ],

                        result[
                            "resolved_symbol"
                        ],

                        result[
                            "resolved_symbol_kind"
                        ],

                        status,

                        result[
                            "resolution_method"
                        ],

                        result[
                            "confidence"
                        ],

                        call[
                            "start_line"
                        ],

                        call[
                            "end_line"
                        ],
                    )
                )

        except Exception:
            failed_files += 1

    with get_database() as database:

        database.execute(
            """
            DELETE FROM code_calls
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        )

        database.executemany(
            """
            INSERT INTO code_calls (
                workspace_id,
                file_path,
                file_sha256,
                language,
                caller_symbol,
                caller_class,
                callee_text,
                call_kind,
                resolved_file_path,
                resolved_symbol,
                resolved_symbol_kind,
                resolution_status,
                resolution_method,
                confidence,
                start_line,
                end_line
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            call_records,
        )

    return CallGraphBuildResult(
        workspace_id=workspace.id,
        workspace_name=workspace.name,

        source_files_seen=len(
            source_rows
        ),

        parsed_files=parsed_files,

        total_calls=len(
            call_records
        ),

        resolved_calls=resolved_calls,

        unresolved_calls=(
            unresolved_calls
        ),

        ambiguous_calls=(
            ambiguous_calls
        ),

        constructor_calls=(
            constructor_calls
        ),

        method_calls=method_calls,

        function_calls=(
            function_calls
        ),

        skipped_unsupported=(
            skipped_unsupported
        ),

        failed_files=failed_files,

        languages=dict(
            language_counter.most_common()
        ),

        indexed_at=indexed_at,
    )


def list_calls(
    workspace_id: str,

    file_path: str | None = None,

    caller: str | None = None,

    callee: str | None = None,

    resolved_symbol: str | None = None,

    resolved_only: bool = False,

    limit: int = 500,
) -> list[CodeCall]:

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
            caller_symbol,
            caller_class,
            callee_text,
            call_kind,
            resolved_file_path,
            resolved_symbol,
            resolved_symbol_kind,
            resolution_status,
            resolution_method,
            confidence,
            start_line,
            end_line
        FROM code_calls
        WHERE workspace_id = ?
    """

    parameters = [
        workspace_id
    ]

    if file_path:

        sql += """
            AND file_path = ?
        """

        parameters.append(
            file_path
        )

    if caller:

        sql += """
            AND caller_symbol LIKE ?
        """

        parameters.append(
            f"%{caller}%"
        )

    if callee:

        sql += """
            AND callee_text LIKE ?
        """

        parameters.append(
            f"%{callee}%"
        )

    if resolved_symbol:

        sql += """
            AND resolved_symbol LIKE ?
        """

        parameters.append(
            f"%{resolved_symbol}%"
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
        CodeCall(
            id=row["id"],

            file_path=row[
                "file_path"
            ],

            language=row[
                "language"
            ],

            caller_symbol=row[
                "caller_symbol"
            ],

            caller_class=row[
                "caller_class"
            ],

            callee_text=row[
                "callee_text"
            ],

            call_kind=row[
                "call_kind"
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

            end_line=row[
                "end_line"
            ],
        )

        for row in rows
    ]
