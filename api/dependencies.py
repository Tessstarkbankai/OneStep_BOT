from typing import Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from indexing.dependency_parser import (
    build_dependency_index,
    list_dependencies,
    list_imports,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Dependencies"],
)


@router.post(
    "/{workspace_id}/dependencies/build"
)
def api_build_dependencies(
    workspace_id: str,
):
    try:
        return build_dependency_index(
            workspace_id
        )

    except WorkspaceError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get(
    "/{workspace_id}/imports"
)
def api_list_imports(
    workspace_id: str,

    q: str | None = None,

    file_path: str | None = None,

    local_only: bool = False,

    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
):
    try:
        return list_imports(
            workspace_id=workspace_id,
            query=q,
            file_path=file_path,
            local_only=local_only,
            limit=limit,
        )

    except WorkspaceError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )


@router.get(
    "/{workspace_id}/dependencies"
)
def api_list_dependencies(
    workspace_id: str,

    file_path: str | None = None,

    direction: Literal[
        "outgoing",
        "incoming",
        "both",
    ] = "outgoing",

    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
):
    try:
        return list_dependencies(
            workspace_id=workspace_id,
            file_path=file_path,
            direction=direction,
            limit=limit,
        )

    except WorkspaceError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )
