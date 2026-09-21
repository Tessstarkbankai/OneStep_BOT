from pydantic import BaseModel, Field

class SemanticBuildResult(BaseModel):
    workspace_id: str
    workspace_name: str

    model_name: str

    chunks: int

    vector_dimension: int

    indexed_at: str


class SemanticSearchRequest(
    BaseModel
):
    query: str = Field(
        min_length=1,
        max_length=2000,
    )

    limit: int = Field(
        default=10,
        ge=1,
        le=50,
    )


class SemanticSearchHit(
    BaseModel
):
    chunk_id: str

    file_path: str
    language: str

    symbol_name: str | None
    symbol_kind: str | None

    start_line: int
    end_line: int

    similarity: float

    preview: str


class SemanticSearchResult(
    BaseModel
):
    workspace_id: str
    workspace_name: str

    query: str

    model_name: str

    results: list[
        SemanticSearchHit
    ]
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
    use_semantic: bool = True

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
    semantic_similarity: (
        float | None
    ) = None

    semantic_symbol_name: (
        str | None
    ) = None

    semantic_start_line: (
        int | None
    ) = None

    semantic_end_line: (
        int | None
    ) = None


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
    semantic_used: bool = False

    semantic_note: str | None = None
    total_candidates: int

    results: list[
        RetrievalCandidate
    ]
