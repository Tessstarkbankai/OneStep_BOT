from fastapi import (
    APIRouter,
    HTTPException,
)

from indexing.index_state import (
    get_workspace_index_state,
)

from indexing.repository_state import (
    RepositoryStateError,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    tags=[
        "Index State",
    ],
)


@router.get(
    "/api/workspaces/"
    "{workspace_id}/index-state"
)
def api_get_index_state(
    workspace_id: str,
):

    try:

        return (
            get_workspace_index_state(
                workspace_id
            )
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except RepositoryStateError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )
