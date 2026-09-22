from pydantic import (
    BaseModel,
    Field,
)


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
    file_path: str

    target_symbol: str

    new_text: str

    reason: str


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
