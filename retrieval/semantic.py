import logging
import time
from datetime import (
    datetime,
    timezone,
)

from embeddings.jina import (
    MODEL_NAME,
    build_embedding_text,
    embed_texts,
)

from indexing.chunker import (
    build_code_chunks,
)

from indexing.index_state import (
    mark_semantic_index_current,
)

from retrieval.models import (
    SemanticBuildResult,
    SemanticSearchHit,
    SemanticSearchResult,
)

from storage.database import (
    get_database,
)

from storage.vectors import (
    replace_workspace_vectors,
    search_workspace_vectors,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


logger = logging.getLogger("semantic")


def build_semantic_index(
    workspace_id: str,
) -> SemanticBuildResult:
    start_time = time.perf_counter()

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    logger.info(f"[{workspace_id}] Generating code chunks for workspace...")
    chunks = build_code_chunks(
        workspace_id
    )

    if not chunks:

        raise RuntimeError(
            "No code chunks were "
            "generated."
        )

    logger.info(f"[{workspace_id}] Extracted {len(chunks)} code chunks. Generating neural embeddings...")

    embedding_texts = [
        build_embedding_text(
            file_path=chunk[
                "file_path"
            ],

            language=chunk[
                "language"
            ],

            symbol_name=chunk[
                "symbol_name"
            ],

            symbol_kind=chunk[
                "symbol_kind"
            ],

            content=chunk[
                "content"
            ],
        )

        for chunk in chunks
    ]

    vectors = embed_texts(
        embedding_texts
    )

    if len(vectors) != len(
        chunks
    ):

        raise RuntimeError(
            "Embedding count does not "
            "match chunk count."
        )

    vector_dimension = len(
        vectors[0]
    )

    rows = []

    for chunk, vector in zip(
        chunks,
        vectors,
    ):

        rows.append(
            {
                "chunk_id": chunk[
                    "chunk_id"
                ],

                "file_path": chunk[
                    "file_path"
                ],

                "language": chunk[
                    "language"
                ],

                "symbol_name": (
                    chunk[
                        "symbol_name"
                    ]
                    or ""
                ),

                "symbol_kind": (
                    chunk[
                        "symbol_kind"
                    ]
                    or ""
                ),

                "start_line": chunk[
                    "start_line"
                ],

                "end_line": chunk[
                    "end_line"
                ],

                "vector": vector,
            }
        )

    replace_workspace_vectors(
        workspace_id=workspace_id,

        rows=rows,
    )

    indexed_at = datetime.now(
        timezone.utc
    ).isoformat()

    with get_database() as database:

        database.execute(
            """
            INSERT INTO semantic_index_status (
                workspace_id,
                model_name,
                chunks,
                vector_dimension,
                indexed_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(workspace_id)
            DO UPDATE SET
                model_name =
                    excluded.model_name,

                chunks =
                    excluded.chunks,

                vector_dimension =
                    excluded.vector_dimension,

                indexed_at =
                    excluded.indexed_at
            """,
            (
                workspace_id,

                MODEL_NAME,

                len(chunks),

                vector_dimension,

                indexed_at,
            ),
        )

    mark_semantic_index_current(
        workspace_id
    )

    elapsed = time.perf_counter() - start_time
    logger.info(f"[{workspace_id}] Successfully built semantic index for {len(chunks)} chunks in {elapsed:.1f}s.")

    return SemanticBuildResult(
        workspace_id=workspace.id,

        workspace_name=(
            workspace.name
        ),

        model_name=MODEL_NAME,

        chunks=len(
            chunks
        ),

        vector_dimension=(
            vector_dimension
        ),

        indexed_at=indexed_at,
    )


def semantic_search(
    workspace_id: str,

    query: str,

    limit: int = 10,
) -> SemanticSearchResult:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    query_vectors = embed_texts(
        [query],

        batch_size=1,
    )

    query_vector = (
        query_vectors[0]
    )

    vector_results = (
        search_workspace_vectors(
            workspace_id=(
                workspace_id
            ),

            query_vector=(
                query_vector
            ),

            limit=limit,
        )
    )

    chunk_ids = [
        result[
            "chunk_id"
        ]

        for result in vector_results
    ]

    chunk_lookup = {}

    if chunk_ids:

        placeholders = ",".join(
            "?"
            for _ in chunk_ids
        )

        sql = f"""
            SELECT
                chunk_id,
                content

            FROM code_chunks

            WHERE workspace_id = ?
              AND chunk_id IN (
                  {placeholders}
              )
        """

        with get_database() as database:

            rows = database.execute(
                sql,

                [
                    workspace_id,
                    *chunk_ids,
                ],
            ).fetchall()

        chunk_lookup = {
            row["chunk_id"]:
            row["content"]

            for row in rows
        }

    hits = []

    for result in vector_results:

        distance = float(
            result.get(
                "_distance",
                1.0,
            )
        )

        #
        # cosine distance:
        #
        # 0 = identical
        # 1 = orthogonal
        # 2 = opposite
        #
        similarity = (
            1.0 - distance
        )

        similarity = max(
            -1.0,
            min(
                1.0,
                similarity,
            ),
        )

        chunk_id = result[
            "chunk_id"
        ]

        content = (
            chunk_lookup.get(
                chunk_id,
                "",
            )
        )

        preview = content[
            :700
        ]

        hits.append(
            SemanticSearchHit(
                chunk_id=(
                    chunk_id
                ),

                file_path=result[
                    "file_path"
                ],

                language=result[
                    "language"
                ],

                symbol_name=(
                    result[
                        "symbol_name"
                    ]
                    or None
                ),

                symbol_kind=(
                    result[
                        "symbol_kind"
                    ]
                    or None
                ),

                start_line=int(
                    result[
                        "start_line"
                    ]
                ),

                end_line=int(
                    result[
                        "end_line"
                    ]
                ),

                similarity=round(
                    similarity,
                    4,
                ),

                preview=preview,
            )
        )

    return SemanticSearchResult(
        workspace_id=workspace.id,

        workspace_name=(
            workspace.name
        ),

        query=query,

        model_name=MODEL_NAME,

        results=hits,
    )