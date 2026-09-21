from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from indexing.call_graph import (
    build_call_graph,
    list_calls,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Call Graph"],
)


@router.post(
    "/{workspace_id}/calls/build"
)
def api_build_call_graph(
    workspace_id: str,
):
    try:

        return build_call_graph(
            workspace_id
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get(
    "/{workspace_id}/calls"
)
def api_list_calls(
    workspace_id: str,

    file_path: str | None = None,

    caller: str | None = None,

    callee: str | None = None,

    resolved_symbol: str | None = None,

    resolved_only: bool = False,

    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
):

    try:

        return list_calls(
            workspace_id=workspace_id,
            file_path=file_path,
            caller=caller,
            callee=callee,
            resolved_symbol=resolved_symbol,
            resolved_only=resolved_only,
            limit=limit,
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )
