from fastapi import (
    APIRouter,
    HTTPException,
)

from agent.answer_agent import (
    answer_question,
)

from agent.models import (
    AskRequest,
    AskResponse,
)

from llm.ollama import (
    get_llm_health,
)

from llm.provider import (
    LLMError,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    tags=["Developer Q&A"],
)


@router.get(
    "/api/llm/health"
)
def api_llm_health():

    return get_llm_health()


@router.post(
    "/api/workspaces/"
    "{workspace_id}/ask",

    response_model=AskResponse,
)
def api_ask(
    workspace_id: str,

    request: AskRequest,
):

    try:

        return answer_question(
            workspace_id=(
                workspace_id
            ),

            question=(
                request.question
            ),

            max_files=(
                request.max_files
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
