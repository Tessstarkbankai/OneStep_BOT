from agent.answer_agent import (
    answer_question,
)

from agent.models import (
    AdaptiveAskResponse,
    RoutingDecision,
)

from agent.orchestrator import (
    run_agent,
)

from agent.task_router import (
    classify_task,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


def adaptive_answer(
    workspace_id: str,

    question: str,

    mode: str = "auto",

    max_files: int = 3,

    max_steps: int = 2,

    use_semantic: bool = True,
) -> AdaptiveAskResponse:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    routing = classify_task(
        question
    )

    #
    # Allow explicit developer override.
    #
    if mode == "fast":

        routing = RoutingDecision(
            route="fast",

            request_kind=(
                routing.request_kind
            ),

            score=(
                routing.score
            ),

            reasons=[
                "route forced to fast "
                "by request",
                *routing.reasons,
            ],
        )

    elif mode == "agent":

        routing = RoutingDecision(
            route="agent",

            request_kind=(
                routing.request_kind
            ),

            score=(
                routing.score
            ),

            reasons=[
                "route forced to agent "
                "by request",
                *routing.reasons,
            ],
        )

    #
    # --------------------------------
    # FAST PATH
    # --------------------------------
    #
    if routing.route == "fast":

        result = answer_question(
            workspace_id=(
                workspace_id
            ),

            question=question,

            max_files=max_files,

            use_semantic=(
                use_semantic
            ),
        )

        return AdaptiveAskResponse(
            workspace_id=(
                result.workspace_id
            ),

            workspace_name=(
                result.workspace_name
            ),

            question=question,

            route="fast",

            routing=routing,

            answer=result.answer,

            needs_more_context=(
                result.needs_more_context
            ),

            missing_context=(
                result.missing_context
            ),

            files_inspected=(
                result.files_inspected
            ),

            tool_steps=[],

            primary_files=(
                result.primary_files
            ),

            evidence=(
                result.evidence
            ),

            llm_model=(
                result.llm_model
            ),

            prompt_tokens=(
                result.prompt_tokens
            ),

            completion_tokens=(
                result.completion_tokens
            ),
        )

    #
    # --------------------------------
    # AGENT PATH
    # --------------------------------
    #
    result = run_agent(
        workspace_id=(
            workspace_id
        ),

        question=question,

        max_steps=max_steps,

        use_semantic=(
            use_semantic
        ),
    )

    return AdaptiveAskResponse(
        workspace_id=(
            result.workspace_id
        ),

        workspace_name=(
            result.workspace_name
        ),

        question=question,

        route="agent",

        routing=routing,

        answer=result.answer,

        needs_more_context=(
            result.needs_more_context
        ),

        missing_context=(
            result.missing_context
        ),

        files_inspected=(
            result.files_inspected
        ),

        tool_steps=(
            result.tool_steps
        ),

        primary_files=[],

        evidence=[],

        llm_model=(
            result.llm_model
        ),

        prompt_tokens=(
            result.prompt_tokens
        ),

        completion_tokens=(
            result.completion_tokens
        ),
    )
