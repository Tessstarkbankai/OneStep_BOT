from fastapi import (
    APIRouter,
    HTTPException,
)

from retrieval.hybrid import (
    hybrid_retrieve,
)

from retrieval.models import (
    HybridRetrievalResult,
    RetrievalRequest,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Retrieval"],
)


@router.post(
    "/{workspace_id}/search",
    response_model=(
        HybridRetrievalResult
    ),
)
def api_hybrid_search(
    workspace_id: str,
    request: RetrievalRequest,
):

    try:

        return hybrid_retrieve(
            workspace_id=workspace_id,

            query=request.query,

            limit=request.limit,

            expand_graph=(
                request.expand_graph
            ),

            use_semantic=(
                request.use_semantic
            ),
        )
    except WorkspaceError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )
