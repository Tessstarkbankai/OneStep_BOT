from fastapi import (
    APIRouter,
    HTTPException,
)

from agent.adaptive import (
    adaptive_answer,
)

from agent.models import (
    AdaptiveAskRequest,
    AdaptiveAskResponse,
)

from llm.provider import (
    LLMError,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Adaptive Assistant"],
)


@router.post(
    "/{workspace_id}/assistant/ask",

    response_model=(
        AdaptiveAskResponse
    ),
)
def api_adaptive_ask(
    workspace_id: str,

    request: AdaptiveAskRequest,
):

    try:

        return adaptive_answer(
            workspace_id=(
                workspace_id
            ),

            question=(
                request.question
            ),

            mode=request.mode,

            max_files=(
                request.max_files
            ),

            max_steps=(
                request.max_steps
            ),

            use_semantic=(
                request.use_semantic
            ),
        )

    except WorkspaceError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except LLMError as error:

        raise HTTPException(
            status_code=502,
            detail=str(error),
        )

    except RuntimeError as error:

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )
