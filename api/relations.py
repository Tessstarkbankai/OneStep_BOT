from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from indexing.relation_graph import (
    build_relation_graph,
    list_relations,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Symbol Relations"],
)


@router.post(
    "/{workspace_id}/relations/build"
)
def api_build_relations(
    workspace_id: str,
):

    try:

        return build_relation_graph(
            workspace_id
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@router.get(
    "/{workspace_id}/relations"
)
def api_list_relations(
    workspace_id: str,

    symbol: str | None = None,

    target: str | None = None,

    relation_type: str | None = None,

    resolved_only: bool = False,

    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
    ),
):

    try:

        return list_relations(
            workspace_id=workspace_id,
            symbol=symbol,
            target=target,
            relation_type=relation_type,
            resolved_only=resolved_only,
            limit=limit,
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

