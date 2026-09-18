from typing import Dict

from pydantic import BaseModel


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
