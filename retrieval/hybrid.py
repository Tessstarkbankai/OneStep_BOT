import json

from collections import (
    defaultdict,
)

from pathlib import Path

from retrieval.lexical import (
    extract_search_terms,
    lexical_search,
)

from retrieval.models import (
    HybridRetrievalResult,
    RetrievalCandidate,
    SymbolHit,
)

from storage.database import (
    get_database,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)
from retrieval.semantic import (
    semantic_search,
)
from indexing.index_state import (
    semantic_index_is_fresh,
)

def _add_reason(
    candidate: dict,
    reason: str,
):

    if reason not in candidate[
        "reasons"
    ]:

        candidate[
            "reasons"
        ].append(
            reason
        )


def _make_candidate(
    candidates: dict,
    file_path: str,
    language: str,
):

    if file_path not in candidates:

        candidates[
            file_path
        ] = {
            "file_path": file_path,

            "language": language,

            "score": 0.0,

            "semantic_similarity": None,
            "semantic_symbol_name": None,
            "semantic_start_line": None,
            "semantic_end_line": None,      
            "reasons": [],

            "symbols": [],

            "lexical_matches": [],
        }

    return candidates[
        file_path
    ]


def _symbol_score(
    query: str,
    terms: list[str],
    symbol,
) -> tuple[
    float,
    list[str],
]:

    query_lower = (
        query.lower().strip()
    )

    name = (
        symbol["name"]
        or ""
    )

    qualified = (
        symbol[
            "qualified_name"
        ]
        or ""
    )

    signature = (
        symbol[
            "signature"
        ]
        or ""
    )

    name_lower = name.lower()

    qualified_lower = (
        qualified.lower()
    )

    signature_lower = (
        signature.lower()
    )

    score = 0.0
    reasons = []

    if (
        query_lower == name_lower
        or query_lower
        == qualified_lower
    ):

        score += 120

        reasons.append(
            "exact symbol match"
        )

    matched_symbol_terms = set()

    for term in terms:

        lowered = term.lower()

        if lowered == name_lower:

            score += 45

            matched_symbol_terms.add(
                lowered
            )

        elif lowered in name_lower:

            score += 28

            matched_symbol_terms.add(
                lowered
            )

        if (
            lowered
            in qualified_lower
            and lowered
            not in matched_symbol_terms
        ):

            score += 18

            matched_symbol_terms.add(
                lowered
            )

        if (
            signature
            and lowered
            in signature_lower
        ):

            score += 5

    if matched_symbol_terms:

        reasons.append(
            "symbol terms: "
            + ", ".join(
                sorted(
                    matched_symbol_terms
                )
            )
        )

    return score, reasons


def _load_repository_importance(
    workspace_id: str,
) -> dict[str, int]:

    with get_database() as database:

        row = database.execute(
            """
            SELECT map_json

            FROM repository_maps

            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchone()

    if row is None:
        return {}

    try:

        data = json.loads(
            row["map_json"]
        )

    except json.JSONDecodeError:
        return {}

    result = {}

    for item in data.get(
        "important_files",
        [],
    ):

        result[
            item["path"]
        ] = item.get(
            "importance_score",
            0,
        )

    return result


def _expand_graph(
    workspace_id: str,
    seed_files: list[str],
    candidates: dict,
    languages_by_file: dict,
):

    if not seed_files:
        return

    seed_set = set(
        seed_files
    )

    with get_database() as database:

        imports = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path

            FROM code_imports

            WHERE workspace_id = ?
              AND resolved_file_path
                  IS NOT NULL
            """,
            (workspace_id,),
        ).fetchall()

        calls = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path,
                resolved_symbol

            FROM code_calls

            WHERE workspace_id = ?
              AND resolution_status
                  = 'local'
              AND resolved_file_path
                  IS NOT NULL
            """,
            (workspace_id,),
        ).fetchall()

        relations = database.execute(
            """
            SELECT
                file_path,
                resolved_file_path,
                resolved_symbol,
                relation_type

            FROM code_relations

            WHERE workspace_id = ?
              AND resolution_status
                  = 'local'
              AND resolved_file_path
                  IS NOT NULL
            """,
            (workspace_id,),
        ).fetchall()

    #
    # File imports.
    #
    for row in imports:

        source = row[
            "file_path"
        ]

        target = row[
            "resolved_file_path"
        ]

        if source in seed_set:

            candidate = _make_candidate(
                candidates,

                target,

                languages_by_file.get(
                    target,
                    "unknown",
                ),
            )

            candidate[
                "score"
            ] += 12

            _add_reason(
                candidate,
                (
                    "dependency of "
                    + source
                ),
            )

        if target in seed_set:

            candidate = _make_candidate(
                candidates,

                source,

                languages_by_file.get(
                    source,
                    "unknown",
                ),
            )

            candidate[
                "score"
            ] += 10

            _add_reason(
                candidate,
                (
                    "depends on "
                    + target
                ),
            )

    #
    # Resolved call graph.
    #
    for row in calls:

        source = row[
            "file_path"
        ]

        target = row[
            "resolved_file_path"
        ]

        if source in seed_set:

            candidate = _make_candidate(
                candidates,

                target,

                languages_by_file.get(
                    target,
                    "unknown",
                ),
            )

            candidate[
                "score"
            ] += 16

            _add_reason(
                candidate,
                (
                    "called from "
                    + source
                ),
            )

        if target in seed_set:

            candidate = _make_candidate(
                candidates,

                source,

                languages_by_file.get(
                    source,
                    "unknown",
                ),
            )

            candidate[
                "score"
            ] += 16

            _add_reason(
                candidate,
                (
                    "calls into "
                    + target
                ),
            )

    #
    # Inheritance / implementation /
    # traits.
    #
    for row in relations:

        source = row[
            "file_path"
        ]

        target = row[
            "resolved_file_path"
        ]

        relation_type = row[
            "relation_type"
        ]

        if source in seed_set:

            candidate = _make_candidate(
                candidates,

                target,

                languages_by_file.get(
                    target,
                    "unknown",
                ),
            )

            candidate[
                "score"
            ] += 10

            _add_reason(
                candidate,
                (
                    relation_type
                    + " relation from "
                    + source
                ),
            )

        if target in seed_set:

            candidate = _make_candidate(
                candidates,

                source,

                languages_by_file.get(
                    source,
                    "unknown",
                ),
            )

            candidate[
                "score"
            ] += 8

            _add_reason(
                candidate,
                (
                    relation_type
                    + " relation to "
                    + target
                ),
            )

def _semantic_index_ready(
    workspace_id: str,
) -> bool:

    with get_database() as database:

        row = database.execute(
            """
            SELECT workspace_id

            FROM semantic_index_status

            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchone()

    return row is not None

def hybrid_retrieve(
    workspace_id: str,
    query: str,
    limit: int = 10,
    expand_graph: bool = True,
    use_semantic: bool = True,
) -> HybridRetrievalResult:

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

    terms = extract_search_terms(
        query
    )

    with get_database() as database:

        file_rows = database.execute(
            """
            SELECT
                path,
                language

            FROM repository_files

            WHERE workspace_id = ?
              AND is_source = 1
            """,
            (workspace_id,),
        ).fetchall()

        symbol_rows = database.execute(
            """
            SELECT
                file_path,
                language,
                kind,
                name,
                qualified_name,
                start_line,
                end_line,
                signature

            FROM code_symbols

            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()

    if not file_rows:

        raise WorkspaceError(
            "Workspace has no indexed "
            "source files. Run /index first."
        )

    known_files = {
        row["path"]
        for row in file_rows
    }

    languages_by_file = {
        row["path"]:
        row["language"]

        for row in file_rows
    }

    candidates = {}

    #
    # ------------------------------------------------
    # 1. SYMBOL SEARCH
    # ------------------------------------------------
    #
    for symbol in symbol_rows:

        score, reasons = (
            _symbol_score(
                query,
                terms,
                symbol,
            )
        )

        if score <= 0:
            continue

        file_path = symbol[
            "file_path"
        ]

        candidate = _make_candidate(
            candidates,

            file_path,

            symbol[
                "language"
            ],
        )

        candidate[
            "score"
        ] += score

        for reason in reasons:

            _add_reason(
                candidate,
                reason,
            )

        candidate[
            "symbols"
        ].append(
            SymbolHit(
                name=symbol[
                    "name"
                ],

                qualified_name=symbol[
                    "qualified_name"
                ],

                kind=symbol[
                    "kind"
                ],

                start_line=symbol[
                    "start_line"
                ],

                end_line=symbol[
                    "end_line"
                ],

                signature=symbol[
                    "signature"
                ],

                score=score,
            )
        )

    #
    # ------------------------------------------------
    # 2. EXACT TEXT / LEXICAL SEARCH
    # ------------------------------------------------
    #
    lexical_matches = lexical_search(
        root_path=root_path,
        known_files=known_files,
        terms=terms,
    )

    for (
        file_path,
        matches,
    ) in lexical_matches.items():

        candidate = _make_candidate(
            candidates,

            file_path,

            languages_by_file.get(
                file_path,
                "unknown",
            ),
        )

        candidate[
            "lexical_matches"
        ].extend(
            matches
        )

        unique_terms = set()

        for match in matches:

            for term in (
                match.matched_terms
            ):

                unique_terms.add(
                    term.lower()
                )

        lexical_score = min(
            65.0,

            (
                len(unique_terms)
                * 14
            )
            +
            (
                min(
                    len(matches),
                    6,
                )
                * 3
            ),
        )

        candidate[
            "score"
        ] += lexical_score

        if unique_terms:

            _add_reason(
                candidate,
                (
                    "text matches: "
                    + ", ".join(
                        sorted(
                            unique_terms
                        )
                    )
                ),
            )

    #
    # ------------------------------------------------
    # 3. FILE/PATH RELEVANCE
    # ------------------------------------------------
    #
    for file_path in known_files:

        path_lower = (
            file_path.lower()
        )

        matched = [
            term.lower()
            for term in terms
            if term.lower()
            in path_lower
        ]

        if not matched:
            continue

        candidate = _make_candidate(
            candidates,

            file_path,

            languages_by_file[
                file_path
            ],
        )

        candidate[
            "score"
        ] += (
            len(
                set(matched)
            )
            * 10
        )

        _add_reason(
            candidate,
            (
                "file path match: "
                + ", ".join(
                    sorted(
                        set(matched)
                    )
                )
            ),
        )
    #
    # ------------------------------------------------
    # 4. SEMANTIC SEARCH
    # ------------------------------------------------
    #
    semantic_used = False
    semantic_note = None

    semantic_fresh = (
        semantic_index_is_fresh(
            workspace_id
        )
    )

    if use_semantic:

        if not _semantic_index_ready(
            workspace_id
        ):

            semantic_note = (
                "Semantic index is not "
                "available for this workspace."
            )

        elif not semantic_fresh:

            semantic_note = (
                "Semantic index is stale "
                "and was skipped."
            )

        else:

            try:

                semantic_result = (
                    semantic_search(
                        workspace_id=(
                            workspace_id
                        ),

                        query=query,

                        limit=max(
                            12,
                            limit * 3,
                        ),
                    )
                )

                semantic_used = True

                #
                # Multiple chunks from the
                # same file may appear.
                #
                # Use the strongest chunk
                # for file-level scoring.
                #
                best_semantic_by_file = {}

                for hit in (
                    semantic_result.results
                ):

                    #
                    # Very weak vector matches
                    # add more noise than value.
                    #
                    if hit.similarity < 0.25:
                        continue

                    existing = (
                        best_semantic_by_file
                        .get(
                            hit.file_path
                        )
                    )

                    if (
                        existing is None
                        or hit.similarity
                        > existing.similarity
                    ):

                        best_semantic_by_file[
                            hit.file_path
                        ] = hit

                for (
                    file_path,
                    hit,
                ) in (
                    best_semantic_by_file
                    .items()
                ):

                    candidate = (
                        _make_candidate(
                            candidates,

                            file_path,

                            languages_by_file
                            .get(
                                file_path,
                                hit.language,
                            ),
                        )
                    )

                    similarity = float(
                        hit.similarity
                    )

                    candidate[
                        "semantic_similarity"
                    ] = round(
                        similarity,
                        4,
                    )

                    candidate[
                        "semantic_symbol_name"
                    ] = hit.symbol_name

                    candidate[
                        "semantic_start_line"
                    ] = hit.start_line

                    candidate[
                        "semantic_end_line"
                    ] = hit.end_line

                    #
                    # Semantic similarity
                    # should help discovery,
                    # but should NOT overpower
                    # exact symbol evidence.
                    #
                    semantic_bonus = max(
                        0.0,

                        min(
                            40.0,

                            (
                                similarity
                                - 0.20
                            )
                            * 100.0,
                        ),
                    )

                    candidate[
                        "score"
                    ] += semantic_bonus

                    if hit.symbol_name:

                        semantic_label = (
                            hit.symbol_name
                        )

                    else:

                        semantic_label = (
                            f"{file_path}:"
                            f"{hit.start_line}-"
                            f"{hit.end_line}"
                        )

                    _add_reason(
                        candidate,

                        (
                            "semantic match: "
                            f"{semantic_label} "
                            f"({similarity:.3f}, "
                            f"+{semantic_bonus:.1f})"
                        ),
                    )

            except Exception as error:

                #
                # Semantic retrieval is an
                # enhancement.
                #
                # A vector/model problem should
                # not destroy deterministic
                # repository search.
                #
                semantic_note = (
                    "Semantic search skipped: "
                    + str(error)[:500]
                )
    #
    # ------------------------------------------------
    # 5. REPOSITORY IMPORTANCE
    # ------------------------------------------------
    #
    importance = (
        _load_repository_importance(
            workspace_id
        )
    )

    for (
        file_path,
        candidate,
    ) in candidates.items():

        importance_score = (
            importance.get(
                file_path,
                0,
            )
        )

        if importance_score <= 0:
            continue

        bonus = min(
            15.0,

            importance_score
            * 0.5,
        )

        candidate[
            "score"
        ] += bonus

        _add_reason(
            candidate,
            (
                "repository importance "
                f"+{bonus:g}"
            ),
        )

    #
    # Get the strongest direct results.
    #
    initial_ranked = sorted(
        candidates.values(),

        key=lambda item: (
            -item["score"],
            item["file_path"],
        ),
    )

    seed_files = [
        item["file_path"]

        for item in (
            initial_ranked[:8]
        )

        if item["score"] > 0
    ]

    #
    # ------------------------------------------------
    # 6. GRAPH EXPANSION
    # ------------------------------------------------
    #
    if expand_graph:

        _expand_graph(
            workspace_id=workspace_id,

            seed_files=seed_files,

            candidates=candidates,

            languages_by_file=(
                languages_by_file
            ),
        )

    #
    # Add a few representative symbols
    # to graph-only candidates.
    #
    symbols_by_file = defaultdict(
        list
    )

    for symbol in symbol_rows:

        symbols_by_file[
            symbol["file_path"]
        ].append(
            symbol
        )

    for (
        file_path,
        candidate,
    ) in candidates.items():

        if candidate[
            "symbols"
        ]:
            continue

        for symbol in (
            symbols_by_file.get(
                file_path,
                [],
            )[:5]
        ):

            candidate[
                "symbols"
            ].append(
                SymbolHit(
                    name=symbol[
                        "name"
                    ],

                    qualified_name=symbol[
                        "qualified_name"
                    ],

                    kind=symbol[
                        "kind"
                    ],

                    start_line=symbol[
                        "start_line"
                    ],

                    end_line=symbol[
                        "end_line"
                    ],

                    signature=symbol[
                        "signature"
                    ],

                    score=0,
                )
            )

    ranked = sorted(
        candidates.values(),

        key=lambda item: (
            -item["score"],
            item["file_path"],
        ),
    )

    results = []

    for item in ranked[:limit]:

        #
        # Sort symbol matches inside
        # each file.
        #
        item["symbols"].sort(
            key=lambda symbol: (
                -symbol.score,
                symbol.start_line,
            )
        )

        item[
            "lexical_matches"
        ] = item[
            "lexical_matches"
        ][:8]

        results.append(
            RetrievalCandidate(
                file_path=item[
                    "file_path"
                ],

                language=item[
                    "language"
                ],

                score=round(
                    item[
                        "score"
                    ],
                    2,
                ),
                semantic_similarity=(
                    item[
                        "semantic_similarity"
                    ]
                ),
                semantic_symbol_name=(
                    item[
                        "semantic_symbol_name"
                    ]
                ),

                semantic_start_line=(
                    item[
                        "semantic_start_line"
                    ]
                ),

                semantic_end_line=(
                    item[
                        "semantic_end_line"
                    ]
                ),


                reasons=item[
                    "reasons"
                ],

                symbols=item[
                    "symbols"
                ][:8],

                lexical_matches=item[
                    "lexical_matches"
                ],
            )
        )

    return HybridRetrievalResult(
        workspace_id=workspace.id,

        workspace_name=workspace.name,

        query=query,

        search_terms=terms,
        semantic_used=(
            semantic_used
        ),

        semantic_note=(
            semantic_note
        ),        

        total_candidates=len(
            candidates
        ),

        results=results,
    )