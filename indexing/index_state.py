from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from indexing.repository_state import (
    get_repository_state,
)

from storage.database import (
    get_database,
)

from workspace.manager import (
    get_workspace,
    WorkspaceError,
)


def _now() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def _repository_path(
    workspace_id: str,
) -> Path:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            "Workspace not found: "
            f"{workspace_id}"
        )

    return Path(
        workspace.path
    ).resolve()


def mark_structural_index_current(
    workspace_id: str,
):

    repo_path = (
        _repository_path(
            workspace_id
        )
    )

    state = get_repository_state(
        repo_path
    )

    indexed_at = _now()

    with get_database() as database:

        database.execute(
            """
            INSERT INTO workspace_index_state (
                workspace_id,
                structural_state_hash,
                structural_head_commit,
                structural_indexed_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(workspace_id)
            DO UPDATE SET
                structural_state_hash =
                    excluded.structural_state_hash,

                structural_head_commit =
                    excluded.structural_head_commit,

                structural_indexed_at =
                    excluded.structural_indexed_at
            """,
            (
                workspace_id,
                state.state_hash,
                state.head_commit,
                indexed_at,
            ),
        )

    return state


def mark_semantic_index_current(
    workspace_id: str,
):

    repo_path = (
        _repository_path(
            workspace_id
        )
    )

    state = get_repository_state(
        repo_path
    )

    indexed_at = _now()

    with get_database() as database:

        database.execute(
            """
            INSERT INTO workspace_index_state (
                workspace_id,
                semantic_state_hash,
                semantic_head_commit,
                semantic_indexed_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(workspace_id)
            DO UPDATE SET
                semantic_state_hash =
                    excluded.semantic_state_hash,

                semantic_head_commit =
                    excluded.semantic_head_commit,

                semantic_indexed_at =
                    excluded.semantic_indexed_at
            """,
            (
                workspace_id,
                state.state_hash,
                state.head_commit,
                indexed_at,
            ),
        )

    return state


def get_workspace_index_state(
    workspace_id: str,
) -> dict:

    repo_path = (
        _repository_path(
            workspace_id
        )
    )

    current = (
        get_repository_state(
            repo_path
        )
    )

    with get_database() as database:

        row = database.execute(
            """
            SELECT *
            FROM workspace_index_state

            WHERE workspace_id = ?
            """,
            (
                workspace_id,
            ),
        ).fetchone()

    if row is None:

        return {
            "workspace_id": (
                workspace_id
            ),

            "current": {
                "head_commit": (
                    current.head_commit
                ),

                "state_hash": (
                    current.state_hash
                ),

                "dirty": (
                    current.dirty
                ),

                "changed_files": (
                    current.changed_files
                ),
            },

            "structural": {
                "fresh": False,
                "state_hash": None,
                "head_commit": None,
                "indexed_at": None,
            },

            "semantic": {
                "fresh": False,
                "state_hash": None,
                "head_commit": None,
                "indexed_at": None,
            },
        }

    structural_hash = row[
        "structural_state_hash"
    ]

    semantic_hash = row[
        "semantic_state_hash"
    ]

    return {
        "workspace_id": (
            workspace_id
        ),

        "current": {
            "head_commit": (
                current.head_commit
            ),

            "state_hash": (
                current.state_hash
            ),

            "dirty": (
                current.dirty
            ),

            "changed_files": (
                current.changed_files
            ),
        },

        "structural": {
            "fresh": (
                structural_hash
                == current.state_hash
            ),

            "state_hash": (
                structural_hash
            ),

            "head_commit": row[
                "structural_head_commit"
            ],

            "indexed_at": row[
                "structural_indexed_at"
            ],
        },

        "semantic": {
            "fresh": (
                semantic_hash
                == current.state_hash
            ),

            "state_hash": (
                semantic_hash
            ),

            "head_commit": row[
                "semantic_head_commit"
            ],

            "indexed_at": row[
                "semantic_indexed_at"
            ],
        },
    }


def structural_index_is_fresh(
    workspace_id: str,
) -> bool:

    state = get_workspace_index_state(
        workspace_id
    )

    return bool(
        state[
            "structural"
        ][
            "fresh"
        ]
    )


def semantic_index_is_fresh(
    workspace_id: str,
) -> bool:

    state = get_workspace_index_state(
        workspace_id
    )

    return bool(
        state[
            "semantic"
        ][
            "fresh"
        ]
    )
