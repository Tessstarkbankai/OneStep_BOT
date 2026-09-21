from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=2000,
    )

    limit: int = Field(
        default=10,
        ge=1,
        le=50,
    )

    expand_graph: bool = True


class LexicalMatch(BaseModel):
    line: int
    text: str
    matched_terms: list[str]


class SymbolHit(BaseModel):
    name: str
    qualified_name: str

    kind: str

    start_line: int
    end_line: int

    signature: str | None

    score: float


class RetrievalCandidate(BaseModel):
    file_path: str
    language: str

    score: float

    reasons: list[str]

    symbols: list[SymbolHit]

    lexical_matches: list[
        LexicalMatch
    ]


class HybridRetrievalResult(BaseModel):
    workspace_id: str
    workspace_name: str

    query: str

    search_terms: list[str]

    total_candidates: int

    results: list[
        RetrievalCandidate
    ]
