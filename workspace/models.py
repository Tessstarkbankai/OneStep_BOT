from pydantic import BaseModel, Field
from typing import Dict


class RepositoryFile(BaseModel):
    path: str
    extension: str | None
    language: str
    size_bytes: int
    sha256: str
    is_source: bool


class ScanResult(BaseModel):
    workspace_id: str
    workspace_name: str
    root_path: str

    scan_method: str
    scanned_at: str

    total_candidates: int
    indexed_files: int

    source_files: int
    other_text_files: int

    skipped_binary: int
    skipped_large: int
    skipped_sensitive: int

    total_indexed_bytes: int

    languages: Dict[str, int]

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1)


class Workspace(BaseModel):
    id: str
    name: str
    path: str
    is_git_repo: bool
    created_at: str
