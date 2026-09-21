from agent.context_builder import (
    build_context,
)

from agent.models import (
    AnswerEvidence,
    AskResponse,
    PrimaryFile,
)

from llm.ollama import (
    chat_json,
)


ANSWER_SCHEMA = {
    "type": "object",

    "additionalProperties": False,

    "properties": {
        "answer": {
            "type": "string",
        },

        "primary_files": {
            "type": "array",

            "items": {
                "type": "object",

                "additionalProperties":
                    False,

                "properties": {
                    "path": {
                        "type": "string",
                    },

                    "symbols": {
                        "type": "array",

                        "items": {
                            "type": "string",
                        },
                    },

                    "why": {
                        "type": "string",
                    },
                },

                "required": [
                    "path",
                    "symbols",
                    "why",
                ],
            },
        },

        "evidence": {
            "type": "array",

            "items": {
                "type": "object",

                "additionalProperties":
                    False,

                "properties": {
                    "path": {
                        "type": "string",
                    },

                    "start_line": {
                        "type": "integer",
                    },

                    "end_line": {
                        "type": "integer",
                    },

                    "description": {
                        "type": "string",
                    },
                },

                "required": [
                    "path",
                    "start_line",
                    "end_line",
                    "description",
                ],
            },
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
        "primary_files",
        "evidence",
        "needs_more_context",
        "missing_context",
    ],
}


SYSTEM_PROMPT = """
You are OutrightBot, a company-aware software
engineering assistant.

You are given only carefully retrieved evidence
from a repository.

Rules:

1. Base the answer ONLY on the supplied repository
   context.

2. Never invent file paths, functions, classes,
   methods, variables, behavior, or line numbers.

3. Distinguish what the code definitely shows from
   what is only a possible interpretation.

4. Prefer existing company implementations and
   helpers over suggesting duplicate code.

5. When explaining implementation flow, reference
   exact files and symbols from the supplied context.

6. If there is not enough evidence to answer
   reliably, set needs_more_context=true and explain
   what additional code is required.

7. Do not propose code changes unless the developer
   asked for a change or fix.

8. Keep the answer technical and concise.

Return JSON matching the requested schema.
""".strip()


def _valid_line_ranges(
    bundle,
):

    ranges = {}

    for snippet in bundle.snippets:

        ranges.setdefault(
            snippet.file_path,
            [],
        ).append(
            (
                snippet.start_line,
                snippet.end_line,
            )
        )

    return ranges


def _evidence_is_valid(
    path: str,

    start_line: int,

    end_line: int,

    valid_ranges,
) -> bool:

    if path not in valid_ranges:
        return False

    for (
        allowed_start,
        allowed_end,
    ) in valid_ranges[path]:

        if (
            start_line
            >= allowed_start
            and end_line
            <= allowed_end
            and end_line
            >= start_line
        ):

            return True

    return False


def answer_question(
    workspace_id: str,

    question: str,

    max_files: int = 5,

    use_semantic: bool = True,
) -> AskResponse:

    bundle = build_context(
        workspace_id=workspace_id,

        question=question,

        max_files=max_files,

        use_semantic=(
            use_semantic
        ),
    )

    if not bundle.snippets:

        raise RuntimeError(
            "No useful repository context "
            "was found for this question."
        )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },

        {
            "role": "user",

            "content": (
                "Answer the developer task "
                "using this repository context."
                "\n\n"
                + bundle.rendered_context
            ),
        },
    ]

    llm_response = chat_json(
        messages=messages,

        schema=ANSWER_SCHEMA,
    )

    payload = (
        llm_response.data
    )

    valid_files = set(
        bundle.files_inspected
    )

    primary_files = []

    for item in payload.get(
        "primary_files",
        [],
    ):

        path = item.get(
            "path",
            "",
        )

        if path not in valid_files:
            continue

        primary_files.append(
            PrimaryFile(
                path=path,

                symbols=item.get(
                    "symbols",
                    [],
                ),

                why=item.get(
                    "why",
                    "",
                ),
            )
        )

    valid_ranges = (
        _valid_line_ranges(
            bundle
        )
    )

    evidence = []

    for item in payload.get(
        "evidence",
        [],
    ):

        path = item.get(
            "path",
            "",
        )

        start_line = int(
            item.get(
                "start_line",
                0,
            )
        )

        end_line = int(
            item.get(
                "end_line",
                0,
            )
        )

        if not _evidence_is_valid(
            path=path,

            start_line=start_line,

            end_line=end_line,

            valid_ranges=(
                valid_ranges
            ),
        ):

            continue

        evidence.append(
            AnswerEvidence(
                path=path,

                start_line=(
                    start_line
                ),

                end_line=(
                    end_line
                ),

                description=(
                    item.get(
                        "description",
                        "",
                    )
                ),
            )
        )

    return AskResponse(
        workspace_id=(
            bundle.workspace_id
        ),

        workspace_name=(
            bundle.workspace_name
        ),

        question=question,

        answer=payload.get(
            "answer",
            "",
        ),

        primary_files=(
            primary_files
        ),

        evidence=evidence,

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

        files_inspected=(
            bundle.files_inspected
        ),

        llm_model=(
            llm_response.model
        ),

        prompt_tokens=(
            llm_response
            .prompt_tokens
        ),

        completion_tokens=(
            llm_response
            .completion_tokens
        ),
    )
