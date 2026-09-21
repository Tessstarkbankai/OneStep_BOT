from typing import Dict

from pydantic import BaseModel


class CodeCall(BaseModel):
    id: int

    file_path: str
    language: str

    caller_symbol: str | None
    caller_class: str | None

    callee_text: str
    call_kind: str

    resolved_file_path: str | None
    resolved_symbol: str | None
    resolved_symbol_kind: str | None

    resolution_status: str
    resolution_method: str | None
    confidence: str | None

    start_line: int
    end_line: int


class CallGraphBuildResult(BaseModel):
    workspace_id: str
    workspace_name: str

    source_files_seen: int
    parsed_files: int

    total_calls: int
    resolved_calls: int
    unresolved_calls: int
    ambiguous_calls: int

    constructor_calls: int
    method_calls: int
    function_calls: int

    skipped_unsupported: int
    failed_files: int

    languages: Dict[str, int]

    indexed_at: str

class CodeSymbol(BaseModel):
    id: int

    file_path: str
    language: str

    kind: str

    name: str
    qualified_name: str

    parent_symbol: str | None

    start_line: int
    end_line: int

    start_column: int
    end_column: int

    signature: str | None


class ParseResult(BaseModel):
    workspace_id: str
    workspace_name: str

    total_source_files: int
    parsed_files: int

    skipped_unsupported: int
    failed_files: int

    files_with_syntax_errors: int

    symbols_extracted: int

    languages: Dict[str, int]
    symbol_kinds: Dict[str, int]

    parsed_at: str
class CodeImport(BaseModel):
    id: int

    file_path: str
    language: str

    kind: str

    module: str

    imported_names: list[str]

    is_relative: bool

    resolved_file_path: str | None

    resolution_status: str

    start_line: int
    end_line: int

    raw_text: str | None


class DependencyEdge(BaseModel):
    from_file: str
    to_file: str

    kind: str
    module: str


class DependencyBuildResult(BaseModel):
    workspace_id: str
    workspace_name: str

    source_files_seen: int
    files_with_imports: int

    total_imports: int

    resolved_local_imports: int
    unresolved_imports: int

    skipped_unsupported: int
    failed_files: int

    languages: Dict[str, int]
    import_kinds: Dict[str, int]

    indexed_at: str
