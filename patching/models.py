from typing import Literal

from pydantic import (
    BaseModel,
    Field,
)

class PatchHistoryItem(BaseModel):

    patch_id: str

    workspace_id: str

    task: str

    status: str

    summary: str

    files_changed: list[str]

    validation: list[dict]

    base_commit: str | None

    sandbox_path: str

    sandbox_exists: bool

    created_at: str | None

    completed_at: str | None

    decision_at: str | None

    applied_at: str | None

    stale_at: str | None

    cleanup_at: str | None


class PatchHistoryResponse(
    BaseModel
):

    workspace_id: str

    patches: list[
        PatchHistoryItem
    ]


class PatchReconcileResponse(
    BaseModel
):

    workspace_id: str

    checked: int

    patches: list[
        PatchHistoryItem
    ]
class PatchRequest(BaseModel):
    task: str = Field(
        min_length=5,
        max_length=5000,
    )

    max_files: int = Field(
        default=3,
        ge=1,
        le=5,
    )

    use_semantic: bool = True

class PatchDecisionResponse(BaseModel):
    patch_id: str

    workspace_id: str

    status: str

    message: str

    files_changed: list[str]
    
class ProposedEdit(BaseModel):
    operation: Literal[
        "replace_symbol",
        "insert_after_symbol",
        "insert_inside_symbol",
        "append_file",
    ] = "replace_symbol"

    file_path: str

    #
    # Null only for append_file, where
    # there is no existing symbol to
    # anchor to. Every other operation
    # requires an exact existing symbol
    # name (see generator.py's
    # PATCH_EDIT_RULES and applier.py's
    # resolve_symbol).
    #
    target_symbol: str | None = None

    new_text: str

    reason: str = ""


class ValidationCheck(BaseModel):
    name: str

    passed: bool

    output: str


class PatchResponse(BaseModel):
    patch_id: str

    workspace_id: str
    workspace_name: str

    status: str

    task: str

    summary: str

    files_changed: list[str]

    diff: str

    validation: list[
        ValidationCheck
    ]

    sandbox_path: str


class PatchStatus(BaseModel):
    patch_id: str

    workspace_id: str

    task: str

    status: str

    summary: str | None

    files_changed: list[str]

    diff: str | None

    validation: list[
        ValidationCheck
    ]

    error_message: str | None