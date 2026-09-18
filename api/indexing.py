from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from indexing.symbol_parser import (
    list_symbols,
    parse_workspace,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Code Intelligence"],
)


@router.post("/{workspace_id}/parse")
def api_parse_workspace(
    workspace_id: str,
):
    try:
        return parse_workspace(
            workspace_id
        )

    except WorkspaceError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get("/{workspace_id}/symbols")
def api_list_symbols(
    workspace_id: str,

    q: str | None = None,

    kind: str | None = None,

    file_path: str | None = None,

    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
):
    try:
        return list_symbols(
            workspace_id=workspace_id,
            query=q,
            kind=kind,
            file_path=file_path,
            limit=limit,
        )

    except WorkspaceError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )
