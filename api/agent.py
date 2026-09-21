from fastapi import (
    APIRouter,
    HTTPException,
)

from agent.models import (
    AgentAskRequest,
    AgentAskResponse,
)

from agent.orchestrator import (
    run_agent,
)

from llm.provider import (
    LLMError,
)

from workspace.manager import (
    WorkspaceError,
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Coding Agent"],
)


@router.post(
    "/{workspace_id}/agent/ask",

    response_model=(
        AgentAskResponse
    ),
)
def api_agent_ask(
    workspace_id: str,

    request: AgentAskRequest,
):

    try:

        return run_agent(
            workspace_id=(
                workspace_id
            ),

            question=(
                request.question
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
