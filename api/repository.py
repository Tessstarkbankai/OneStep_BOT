from fastapi import (
    APIRouter,
    HTTPException,
)

from indexing.indexer import (
    get_latest_index_run,
    run_full_index,
)

from indexing.repo_map import (
    get_repository_map,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Repository Intelligence"],
)


@router.post(
    "/{workspace_id}/index"
)
def api_full_index(
    workspace_id: str,
):

    try:

        return run_full_index(
            workspace_id
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get(
    "/{workspace_id}/index/status"
)
def api_index_status(
    workspace_id: str,
):

    try:

        result = (
            get_latest_index_run(
                workspace_id
            )
        )

        if result is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Workspace has not "
                    "been indexed yet."
                ),
            )

        return result

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/{workspace_id}/map"
)
def api_repository_map(
    workspace_id: str,
):

    try:

        result = (
            get_repository_map(
                workspace_id
            )
        )

        if result is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Repository map "
                    "does not exist. "
                    "Run indexing first."
                ),
            )

        return result

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )
