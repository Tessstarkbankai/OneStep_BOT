from pydantic import (
    BaseModel,
    Field,
)
from typing import Literal
class AgentAskRequest(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=5000,
    )

    max_steps: int = Field(
        default=2,
        ge=1,
        le=4,
    )

    use_semantic: bool = True


class AgentToolStep(BaseModel):
    step: int

    tool: str

    arguments: dict

    result_preview: str


class AgentAskResponse(BaseModel):
    workspace_id: str
    workspace_name: str

    question: str

    answer: str

    needs_more_context: bool

    missing_context: str

    tool_steps: list[
        AgentToolStep
    ]

    files_inspected: list[str]

    llm_model: str

    prompt_tokens: (
        int | None
    )

    completion_tokens: (
        int | None
    )

class AskRequest(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=5000,
    )

    max_files: int = Field(
        default=5,
        ge=1,
        le=8,
    )

    use_semantic: bool = True


class PrimaryFile(BaseModel):
    path: str

    symbols: list[str]

    why: str


class AnswerEvidence(BaseModel):
    path: str

    start_line: int
    end_line: int

    description: str


class AskResponse(BaseModel):
    workspace_id: str
    workspace_name: str

    question: str

    answer: str

    primary_files: list[
        PrimaryFile
    ]

    evidence: list[
        AnswerEvidence
    ]

    needs_more_context: bool

    missing_context: str

    files_inspected: list[str]

    llm_model: str

    prompt_tokens: (
        int | None
    )

    completion_tokens: (
        int | None
    )

class RoutingDecision(BaseModel):
    route: Literal[
        "fast",
        "agent",
    ]

    request_kind: Literal[
        "question",
        "investigation",
        "change",
    ]

    score: int

    reasons: list[str]


class AdaptiveAskRequest(BaseModel):
    question: str = Field(
        min_length=2,
        max_length=5000,
    )

    mode: Literal[
        "auto",
        "fast",
        "agent",
    ] = "auto"

    max_files: int = Field(
        default=3,
        ge=1,
        le=8,
    )

    max_steps: int = Field(
        default=2,
        ge=1,
        le=4,
    )

    use_semantic: bool = True


class AdaptiveAskResponse(BaseModel):
    workspace_id: str
    workspace_name: str

    question: str

    route: Literal[
        "fast",
        "agent",
    ]

    routing: RoutingDecision

    answer: str

    needs_more_context: bool

    missing_context: str

    files_inspected: list[str]

    tool_steps: list[
        AgentToolStep
    ] = []

    primary_files: list[
        PrimaryFile
    ] = []

    evidence: list[
        AnswerEvidence
    ] = []

    llm_model: str

    prompt_tokens: (
        int | None
    )

    completion_tokens: (
        int | None
    )
