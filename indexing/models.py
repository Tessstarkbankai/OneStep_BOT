from typing import Dict

from pydantic import BaseModel

class DirectorySummary(BaseModel):
    path: str

    source_files: int
    symbols: int


class ImportantFileSummary(BaseModel):
    path: str
    language: str

    symbols: int

    incoming_dependencies: int
    outgoing_dependencies: int

    incoming_calls: int
    outgoing_calls: int

    importance_score: int


class KeySymbolSummary(BaseModel):
    name: str
    qualified_name: str

    kind: str
    file_path: str

    incoming_calls: int
    incoming_relations: int

    importance_score: int


class RepositoryMap(BaseModel):
    workspace_id: str
    workspace_name: str

    generated_at: str

    total_files: int
    source_files: int

    languages: Dict[str, int]

    symbols: int

    imports: int
    resolved_local_imports: int

    calls: int
    resolved_calls: int

    relations: int
    resolved_relations: int

    entry_points: list[str]

    directories: list[
        DirectorySummary
    ]

    important_files: list[
        ImportantFileSummary
    ]

    key_symbols: list[
        KeySymbolSummary
    ]


class UnifiedIndexResult(BaseModel):
    workspace_id: str
    workspace_name: str

    status: str

    started_at: str
    completed_at: str

    indexed_files: int
    symbols: int
    imports: int
    relations: int
    calls: int

    repository_map: RepositoryMap


class IndexRunStatus(BaseModel):
    id: int

    workspace_id: str

    status: str

    started_at: str
    completed_at: str | None

    error_message: str | None

    scan_files: int
    symbols: int
    imports: int
    relations: int
    calls: int

class CodeRelation(BaseModel):
    id: int

    file_path: str
    language: str

    source_symbol: str
    source_kind: str

    relation_type: str

    target_text: str

    resolved_file_path: str | None
    resolved_symbol: str | None
    resolved_symbol_kind: str | None

    resolution_status: str
    resolution_method: str | None
    confidence: str | None

    start_line: int


class RelationBuildResult(BaseModel):
    workspace_id: str
    workspace_name: str

    source_files_seen: int
    parsed_files: int

    total_relations: int

    resolved_relations: int
    unresolved_relations: int
    ambiguous_relations: int

    extends_relations: int
    implements_relations: int
    trait_relations: int

    failed_files: int

    languages: Dict[str, int]
    relation_types: Dict[str, int]

    indexed_at: str
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
