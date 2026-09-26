import json

from agent.models import (
    AgentAskResponse,
    AgentToolStep,
)

from agent.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
)

from llm.ollama import (
    chat_json,
    chat_with_tools,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)


AGENT_SYSTEM_PROMPT = """
You are OutrightBot's repository investigation
agent.

Your job is to investigate the developer's question
using ONLY the repository tools provided to you.

Important rules:

1. Use repository tools instead of guessing.

2. For questions about implementation behavior,
   locate the relevant code and read the exact
   implementation before concluding.

3. Use find_callers and find_callees when tracing
   execution flow.

4. Never invent files, symbols, dependencies,
   methods, or behavior.

5. Do not request shell access.

6. Do not modify files.

7. Keep tool usage focused. Do not inspect unrelated
   files.

8. You MUST use at least one repository tool before
   the investigation is considered complete.

9. Once enough evidence has been collected, stop
   requesting tools.

This stage is investigation only.
""".strip()


FINAL_SCHEMA = {
    "type": "object",

    "additionalProperties": False,

    "properties": {
        "answer": {
            "type": "string",
        },

        "needs_more_context": {
            "type": "boolean",
        },

        "missing_context": {
            "type": "string",
        },
    },

    "required": [
        "answer",
        "needs_more_context",
        "missing_context",
    ],
}


FINAL_SYSTEM_PROMPT = """
You are OutrightBot, a software engineering
assistant.

Answer the developer using ONLY the repository
evidence supplied below.

Rules:

- Do not invent files, symbols, functions, methods,
  behavior, or relationships.
- Distinguish confirmed code behavior from
  uncertainty.
- Mention concrete file paths and symbols when useful.
- Prefer existing company code over hypothetical new
  implementations.
- If the evidence is insufficient, set
  needs_more_context=true.
- Keep the response concise and technical.
""".strip()


def _parse_arguments(
    value,
) -> dict:

    if isinstance(
        value,
        dict,
    ):
        return value

    if isinstance(
        value,
        str,
    ):

        try:
            parsed = json.loads(
                value
            )

            if isinstance(
                parsed,
                dict,
            ):
                return parsed

        except json.JSONDecodeError:
            pass

    return {}


def _collect_file_paths(
    value,
    output: set[str],
):

    if isinstance(
        value,
        dict,
    ):

        for key, item in (
            value.items()
        ):

            if (
                key in {
                    "file_path",
                    "path",
                    "resolved_file_path",
                }
                and isinstance(
                    item,
                    str,
                )
                and item
            ):

                output.add(
                    item
                )

            _collect_file_paths(
                item,
                output,
            )

    elif isinstance(
        value,
        list,
    ):

        for item in value:

            _collect_file_paths(
                item,
                output,
            )


def _tool_content(
    result: dict,
) -> str:

    content = json.dumps(
        result,
        ensure_ascii=False,
    )

    #
    # Protect the model context from
    # very large tool responses.
    #
    if len(content) > 7000:

        content = (
            content[:7000]
            + "\n...[tool result truncated]"
        )

    return content


def run_agent(
    workspace_id: str,

    question: str,

    max_steps: int = 2,

    use_semantic: bool = True,
) -> AgentAskResponse:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    messages = [
        {
            "role": "system",
            "content": (
                AGENT_SYSTEM_PROMPT
            ),
        },

        {
            "role": "user",
            "content": question,
        },
    ]

    tool_steps = []

    evidence_blocks = []

    files_inspected = set()

    total_prompt_tokens = 0
    total_completion_tokens = 0

    llm_model = ""

    tool_was_used = False

    for step_number in range(
        1,
        max_steps + 1,
    ):

        response = chat_with_tools(
            messages=messages,

            tools=TOOL_DEFINITIONS,

            #
            # Tool calls should be
            # short and fast.
            #
            max_tokens=140,
        )

        llm_model = response.model

        total_prompt_tokens += (
            response.prompt_tokens
            or 0
        )

        total_completion_tokens += (
            response.completion_tokens
            or 0
        )

        assistant_message = (
            response.message
        )

        messages.append(
            assistant_message
        )

        tool_calls = (
            assistant_message.get(
                "tool_calls"
            )
            or []
        )

        if not tool_calls:

            #
            # If Qwen refuses to use
            # a tool on the first turn,
            # deterministic search is
            # our safe fallback.
            #
            if not tool_was_used:

                result = execute_tool(
                    workspace_id=(
                        workspace_id
                    ),

                    tool_name=(
                        "search_code"
                    ),

                    arguments={
                        "query": question,
                        "limit": 5,
                    },

                    use_semantic=(
                        use_semantic
                    ),
                )

                content = _tool_content(
                    result
                )

                tool_was_used = True

                evidence_blocks.append(
                    (
                        "TOOL: search_code\n"
                        + content
                    )
                )

                _collect_file_paths(
                    result,
                    files_inspected,
                )

                tool_steps.append(
                    AgentToolStep(
                        step=step_number,

                        tool=(
                            "search_code"
                        ),

                        arguments={
                            "query": question,
                            "limit": 5,
                        },

                        result_preview=(
                            content[:800]
                        ),
                    )
                )

            break

        #
        # Prevent one model response
        # from issuing a huge batch of
        # expensive tools.
        #
        for tool_call in (
            tool_calls[:2]
        ):

            function = tool_call.get(
                "function",
                {},
            )

            tool_name = function.get(
                "name",
                "",
            )

            arguments = (
                _parse_arguments(
                    function.get(
                        "arguments",
                        {},
                    )
                )
            )

            try:

                result = execute_tool(
                    workspace_id=(
                        workspace_id
                    ),

                    tool_name=(
                        tool_name
                    ),

                    arguments=(
                        arguments
                    ),

                    use_semantic=(
                        use_semantic
                    ),
                )

            except Exception as error:

                result = {
                    "error": str(error),
                }

            content = _tool_content(
                result
            )

            tool_was_used = True

            _collect_file_paths(
                result,
                files_inspected,
            )

            tool_steps.append(
                AgentToolStep(
                    step=step_number,

                    tool=tool_name,

                    arguments=arguments,

                    result_preview=(
                        content[:800]
                    ),
                )
            )

            evidence_blocks.append(
                (
                    f"TOOL: {tool_name}\n"
                    f"ARGUMENTS: "
                    f"{json.dumps(arguments)}\n"
                    f"RESULT:\n{content}"
                )
            )

            #
            # Ollama supports passing
            # tool results back using
            # role=tool.
            #
            messages.append(
                {
                    "role": "tool",

                    "content": content,

                    "tool_name": (
                        tool_name
                    ),
                }
            )

    #
    # Final response is a separate
    # short structured generation.
    #
    evidence_text = (
        "\n\n====================\n\n"
        .join(
            evidence_blocks
        )
    )

    final_messages = [
        {
            "role": "system",

            "content": (
                FINAL_SYSTEM_PROMPT
            ),
        },

        {
            "role": "user",

            "content": (
                f"DEVELOPER QUESTION:\n"
                f"{question}\n\n"
                f"REPOSITORY EVIDENCE:\n"
                f"{evidence_text}"
            ),
        },
    ]

    final_response = chat_json(
        messages=final_messages,

        schema=FINAL_SCHEMA,

        max_tokens=2048,
    )

    llm_model = (
        final_response.model
        or llm_model
    )

    total_prompt_tokens += (
        final_response.prompt_tokens
        or 0
    )

    total_completion_tokens += (
        final_response
        .completion_tokens
        or 0
    )

    payload = (
        final_response.data
    )

    return AgentAskResponse(
        workspace_id=(
            workspace.id
        ),

        workspace_name=(
            workspace.name
        ),

        question=question,

        answer=payload.get(
            "answer",
            "",
        ),

        needs_more_context=bool(
            payload.get(
                "needs_more_context",
                False,
            )
        ),

        missing_context=(
            payload.get(
                "missing_context",
                "",
            )
        ),

        tool_steps=tool_steps,

        files_inspected=sorted(
            files_inspected
        ),

        llm_model=llm_model,

        prompt_tokens=(
            total_prompt_tokens
        ),

        completion_tokens=(
            total_completion_tokens
        ),
    )
