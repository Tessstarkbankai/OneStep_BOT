from dataclasses import (
    dataclass,
)

from pathlib import Path

from indexing.repo_map import (
    get_repository_map,
)

from retrieval.hybrid import (
    hybrid_retrieve,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


MAX_TOTAL_CONTEXT_CHARS = 24000

MAX_SNIPPETS_PER_FILE = 2

MAX_SNIPPET_LINES = 160


@dataclass
class ContextSnippet:
    file_path: str
    language: str

    start_line: int
    end_line: int

    score: float

    reasons: list[str]

    code: str


@dataclass
class ContextBundle:
    workspace_id: str
    workspace_name: str

    question: str

    rendered_context: str

    snippets: list[
        ContextSnippet
    ]

    files_inspected: list[str]

    retrieval_candidates: int


def _merge_ranges(
    ranges: list[
        tuple[int, int]
    ],
) -> list[
    tuple[int, int]
]:

    if not ranges:
        return []

    cleaned = []

    for start, end in ranges:

        start = max(
            1,
            start,
        )

        end = max(
            start,
            end,
        )

        if (
            end - start + 1
            > MAX_SNIPPET_LINES
        ):

            end = (
                start
                + MAX_SNIPPET_LINES
                - 1
            )

        cleaned.append(
            (
                start,
                end,
            )
        )

    cleaned.sort()

    merged = []

    for start, end in cleaned:

        if not merged:

            merged.append(
                [
                    start,
                    end,
                ]
            )

            continue

        previous = merged[-1]

        if start <= (
            previous[1] + 8
        ):

            previous[1] = max(
                previous[1],
                end,
            )

        else:

            merged.append(
                [
                    start,
                    end,
                ]
            )

    return [
        (
            item[0],
            item[1],
        )

        for item in (
            merged[
                :MAX_SNIPPETS_PER_FILE
            ]
        )
    ]


def _candidate_ranges(
    candidate,
):

    ranges = []

    #
    # Highest priority:
    # exact semantic chunk.
    #
    if (
        candidate
        .semantic_start_line
        is not None
        and candidate
        .semantic_end_line
        is not None
    ):

        ranges.append(
            (
                max(
                    1,
                    candidate
                    .semantic_start_line
                    - 4,
                ),

                candidate
                .semantic_end_line
                + 4,
            )
        )

    #
    # Strong symbol matches.
    #
    strong_symbols = [
        symbol

        for symbol in (
            candidate.symbols
        )

        if symbol.score > 0
    ]

    strong_symbols.sort(
        key=lambda symbol:
        -symbol.score
    )

    for symbol in (
        strong_symbols[:2]
    ):

        ranges.append(
            (
                max(
                    1,
                    symbol.start_line
                    - 3,
                ),

                symbol.end_line + 3,
            )
        )

    #
    # Exact text hits.
    #
    for match in (
        candidate.lexical_matches[
            :3
        ]
    ):

        ranges.append(
            (
                max(
                    1,
                    match.line - 6,
                ),

                match.line + 6,
            )
        )

    #
    # Graph-only fallback.
    #
    if (
        not ranges
        and candidate.symbols
    ):

        symbol = (
            candidate.symbols[0]
        )

        ranges.append(
            (
                max(
                    1,
                    symbol.start_line
                    - 3,
                ),

                symbol.end_line + 3,
            )
        )

    return _merge_ranges(
        ranges
    )


def _read_range(
    root_path: Path,

    file_path: str,

    start_line: int,

    end_line: int,
) -> str:

    absolute_path = (
        root_path / file_path
    ).resolve()

    try:

        absolute_path.relative_to(
            root_path
        )

    except ValueError:

        raise WorkspaceError(
            "Attempted to read outside "
            "workspace root."
        )

    source = (
        absolute_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    lines = source.splitlines()

    start_index = max(
        0,
        start_line - 1,
    )

    end_index = min(
        len(lines),
        end_line,
    )

    selected = lines[
        start_index:end_index
    ]

    rendered = []

    for offset, text in enumerate(
        selected,
        start=start_index + 1,
    ):

        rendered.append(
            f"{offset:>5} | {text}"
        )

    return "\n".join(
        rendered
    )


def build_context(
    workspace_id: str,

    question: str,

    max_files: int = 5,

    use_semantic: bool = True,
) -> ContextBundle:

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

    retrieval = hybrid_retrieve(
        workspace_id=workspace_id,

        query=question,

        limit=max_files + 3,

        expand_graph=True,

        use_semantic=(
            use_semantic
        ),
    )

    repository_map = (
        get_repository_map(
            workspace_id
        )
    )

    snippets = []

    total_chars = 0

    files_used = set()

    for candidate in (
        retrieval.results
    ):

        if (
            len(files_used)
            >= max_files
        ):

            break

        ranges = (
            _candidate_ranges(
                candidate
            )
        )

        if not ranges:
            continue

        file_added = False

        for start, end in ranges:

            try:

                code = _read_range(
                    root_path=(
                        root_path
                    ),

                    file_path=(
                        candidate.file_path
                    ),

                    start_line=start,

                    end_line=end,
                )

            except OSError:
                continue

            if not code:
                continue

            if (
                total_chars
                + len(code)
                > MAX_TOTAL_CONTEXT_CHARS
            ):

                break

            snippets.append(
                ContextSnippet(
                    file_path=(
                        candidate.file_path
                    ),

                    language=(
                        candidate.language
                    ),

                    start_line=start,

                    end_line=end,

                    score=(
                        candidate.score
                    ),

                    reasons=(
                        candidate.reasons[
                            :8
                        ]
                    ),

                    code=code,
                )
            )

            total_chars += len(
                code
            )

            file_added = True

        if file_added:

            files_used.add(
                candidate.file_path
            )

    sections = []

    sections.append(
        "REPOSITORY\n"
        f"Name: {workspace.name}\n"
        f"Root: {workspace.path}"
    )

    if repository_map:

        languages = ", ".join(
            (
                f"{language}: "
                f"{count}"
            )

            for (
                language,
                count,
            ) in (
                repository_map
                .languages
                .items()
            )
        )

        entrypoints = ", ".join(
            repository_map.entry_points[
                :8
            ]
        )

        sections.append(
            "REPOSITORY MAP\n"
            f"Source files: "
            f"{repository_map.source_files}\n"
            f"Symbols: "
            f"{repository_map.symbols}\n"
            f"Languages: {languages}\n"
            f"Entry points: "
            f"{entrypoints or 'none detected'}"
        )

    sections.append(
        "DEVELOPER TASK\n"
        + question
    )

    for index, snippet in enumerate(
        snippets,
        start=1,
    ):

        sections.append(
            "\n".join(
                [
                    (
                        f"CONTEXT {index}"
                    ),

                    (
                        f"File: "
                        f"{snippet.file_path}"
                    ),

                    (
                        f"Language: "
                        f"{snippet.language}"
                    ),

                    (
                        f"Lines: "
                        f"{snippet.start_line}-"
                        f"{snippet.end_line}"
                    ),

                    (
                        f"Retrieval score: "
                        f"{snippet.score}"
                    ),

                    (
                        "Why retrieved: "
                        + "; ".join(
                            snippet.reasons
                        )
                    ),

                    "CODE:",

                    snippet.code,
                ]
            )
        )

    rendered_context = (
        "\n\n"
        "====================\n\n"
        .join(
            sections
        )
    )

    return ContextBundle(
        workspace_id=workspace.id,

        workspace_name=(
            workspace.name
        ),

        question=question,

        rendered_context=(
            rendered_context
        ),

        snippets=snippets,

        files_inspected=sorted(
            files_used
        ),

        retrieval_candidates=(
            retrieval
            .total_candidates
        ),
    )
