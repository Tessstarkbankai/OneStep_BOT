from fastapi import (
    APIRouter,
    HTTPException,
)

from retrieval.models import (
    SemanticBuildResult,
    SemanticSearchRequest,
    SemanticSearchResult,
)

from retrieval.semantic import (
    build_semantic_index,
    semantic_search,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Semantic Retrieval"],
)


@router.post(
    "/{workspace_id}/semantic/build",

    response_model=(
        SemanticBuildResult
    ),
)
def api_build_semantic_index(
    workspace_id: str,
):

    try:

        return build_semantic_index(
            workspace_id
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


@router.post(
    "/{workspace_id}/semantic/search",

    response_model=(
        SemanticSearchResult
    ),
)
def api_semantic_search(
    workspace_id: str,

    request: SemanticSearchRequest,
):

    try:

        return semantic_search(
            workspace_id=workspace_id,

            query=request.query,

            limit=request.limit,
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
