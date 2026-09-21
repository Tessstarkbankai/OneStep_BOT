import re

import lancedb

from app.config import (
    VECTOR_DIR,
)


def _table_name(
    workspace_id: str,
) -> str:

    safe = re.sub(
        r"[^A-Za-z0-9_]+",
        "_",
        workspace_id,
    )

    return (
        "semantic_"
        + safe
    )


def get_vector_database():

    return lancedb.connect(
        str(
            VECTOR_DIR
        )
    )


def replace_workspace_vectors(
    workspace_id: str,
    rows: list[dict],
):

    if not rows:

        raise RuntimeError(
            "No semantic vectors "
            "were generated."
        )

    database = (
        get_vector_database()
    )

    table_name = _table_name(
        workspace_id
    )

    table = database.create_table(
        table_name,

        data=rows,

        mode="overwrite",
    )

    return table


def search_workspace_vectors(
    workspace_id: str,

    query_vector: list[float],

    limit: int = 10,
):

    database = (
        get_vector_database()
    )

    table_name = _table_name(
        workspace_id
    )

    try:

        table = database.open_table(
            table_name
        )

    except Exception as error:

        raise RuntimeError(
            "Semantic index does not "
            "exist for this workspace. "
            "Run semantic indexing first."
        ) from error

    return (
        table
        .search(
            query_vector
        )
        .distance_type(
            "cosine"
        )
        .limit(
            limit
        )
        .to_list()
    )
