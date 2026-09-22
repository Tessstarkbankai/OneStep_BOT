from pathlib import Path

from agent.context_builder import (
    build_context,
)

from llm.ollama import (
    chat_json,
)

from patching.models import (
    ProposedEdit,
)

from workspace.manager import (
    WorkspaceError,
    get_workspace,
)
from storage.database import (
    get_database,
)


PATCH_SCHEMA = {
    "type": "object",

    "additionalProperties": False,

    "properties": {
        "summary": {
            "type": "string",
        },

        "edits": {
            "type": "array",

            "items": {
                "type": "object",

                "additionalProperties":
                    False,

                "properties": {
                    "file_path": {
                        "type": "string",
                    },

                    "target_symbol": {
                        "type": "string",
                    },

                    "new_text": {
                        "type": "string",
                    },

                    "reason": {
                        "type": "string",
                    },
                },

                "required": [
                    "file_path",
                    "target_symbol",
                    "new_text",
                    "reason",
                ],
            },
        },
    },

    "required": [
        "summary",
        "edits",
    ],
}


PATCH_SYSTEM_PROMPT = """
You are OutrightBot's patch generation engine.

You are given a developer task and repository source
code with indexed symbols.

Produce the smallest safe code change that satisfies
the task.

For every edit:

1. file_path must be an existing file supplied in
   the repository context.

2. target_symbol must be the EXACT indexed symbol
   name supplied in the context, preferably its
   qualified name.

   Example:
   PricingService.calculateOffer

3. new_text must contain the COMPLETE replacement
   source for that symbol.

4. Preserve the language's indentation and syntax.

5. Do not include markdown code fences.

6. Do not create or delete files.

7. Prefer existing company helpers rather than
   duplicating functionality.

8. Change only the smallest relevant symbol.

9. Do not modify unrelated formatting.

10. Do not add dependencies unless explicitly asked.

Python will locate the original implementation from
the repository index. Do NOT return old_text.

Return JSON matching the requested schema.
""".strip()


def _read_raw_range(
    root_path: Path,

    file_path: str,

    start_line: int,

    end_line: int,
) -> str:

    absolute_path = (
        root_path / file_path
    ).resolve()

    try:

        absolute_path.relative_to(
            root_path
        )

    except ValueError:

        raise WorkspaceError(
            "Attempted to read outside "
            "workspace root."
        )

    source = absolute_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    lines = source.splitlines(
        keepends=True
    )

    start_index = max(
        0,
        start_line - 1,
    )

    end_index = min(
        len(lines),
        end_line,
    )

    return "".join(
        lines[
            start_index:end_index
        ]
    )


def _build_raw_patch_context(
    workspace_id: str,

    context,
) -> str:

    workspace = get_workspace(
        workspace_id
    )

    if workspace is None:

        raise WorkspaceError(
            f"Workspace not found: "
            f"{workspace_id}"
        )

    root_path = Path(
        workspace.path
    ).resolve()

    blocks = []

    for index, snippet in enumerate(
        context.snippets,
        start=1,
    ):

        raw_code = _read_raw_range(
            root_path=root_path,

            file_path=(
                snippet.file_path
            ),

            start_line=(
                snippet.start_line
            ),

            end_line=(
                snippet.end_line
            ),
        )

        blocks.append(
            "\n".join(
                [
                    (
                        f"SOURCE BLOCK "
                        f"{index}"
                    ),

                    (
                        f"FILE: "
                        f"{snippet.file_path}"
                    ),

                    (
                        f"LANGUAGE: "
                        f"{snippet.language}"
                    ),

                    (
                        f"LINES: "
                        f"{snippet.start_line}-"
                        f"{snippet.end_line}"
                    ),

                    "RAW SOURCE BEGIN",

                    raw_code,

                    "RAW SOURCE END",
                ]
            )
        )

    return (
        "\n\n"
        "====================\n\n"
        .join(
            blocks
        )
    )
def _build_editable_symbols(
    workspace_id: str,
    context,
) -> str:

    files = list(
        context.files_inspected
    )

    if not files:
        return ""

    placeholders = ",".join(
        "?"
        for _ in files
    )

    query = f"""
        SELECT
            file_path,
            kind,
            name,
            qualified_name,
            start_line,
            end_line,
            signature

        FROM code_symbols

        WHERE workspace_id = ?
          AND file_path IN (
              {placeholders}
          )

        ORDER BY
            file_path,
            start_line
    """

    with get_database() as database:

        rows = database.execute(
            query,
            (
                workspace_id,
                *files,
            ),
        ).fetchall()

    output = [
        "EDITABLE INDEXED SYMBOLS:",
    ]

    for row in rows:

        output.append(
            (
                f"- file={row['file_path']} "
                f"symbol={row['qualified_name']} "
                f"kind={row['kind']} "
                f"lines={row['start_line']}-"
                f"{row['end_line']} "
                f"signature={row['signature']}"
            )
        )

    return "\n".join(
        output
    )

def generate_patch_plan(
    workspace_id: str,

    task: str,

    max_files: int = 3,

    use_semantic: bool = True,

    validation_feedback: (
        str | None
    ) = None,
):

    context = build_context(
        workspace_id=(
            workspace_id
        ),

        question=task,

        max_files=max_files,

        use_semantic=(
            use_semantic
        ),
    )

    if not context.snippets:

        raise RuntimeError(
            "No relevant code was found "
            "for patch generation."
        )

    #
    # IMPORTANT:
    #
    # Do NOT use context.rendered_context
    # here because that representation
    # contains line-number prefixes.
    #
    # Patching requires exact raw source.
    #
    raw_patch_context = (
        _build_raw_patch_context(
            workspace_id=(
                workspace_id
            ),

            context=context,
        )
    )
    editable_symbols = (
        _build_editable_symbols(
            workspace_id,
            context,
        )
    )
    feedback_section = ""

    if validation_feedback:

        feedback_section = (
            "\n\n"
            "PREVIOUS PATCH FAILED VALIDATION:\n"
            + validation_feedback
            + "\n\n"
            "Generate a corrected patch from "
            "the ORIGINAL repository source. "
            "Do not repeat the validation error."
        )
    messages = [
        {
            "role": "system",

            "content": (
                PATCH_SYSTEM_PROMPT
            ),
        },

        {
            "role": "user",

            "content": (
                "DEVELOPER TASK:\n"
                + task
                + "\n\n"
                + editable_symbols
                + "\n\n"
                "EXACT REPOSITORY SOURCE:\n\n"
                + raw_patch_context
                + feedback_section
            ),
        },
    ]

    response = chat_json(
        messages=messages,

        schema=PATCH_SCHEMA,

        max_tokens=600,
    )

    payload = response.data

    edits = [
        ProposedEdit(
            **item
        )

        for item in (
            payload.get(
                "edits",
                []
            )
        )
    ]

    if not edits:

        raise RuntimeError(
            "Model did not propose "
            "any edits."
        )

    allowed_files = set(
        context.files_inspected
    )
    with get_database() as database:

        for edit in edits:

            if (
                edit.file_path
                not in allowed_files
            ):

                raise RuntimeError(
                    "Model attempted to edit "
                    "a file that was not supplied "
                    "as repository context: "
                    f"{edit.file_path}"
                )

            row = database.execute(
                """
                SELECT qualified_name

                FROM code_symbols

                WHERE workspace_id = ?
                AND file_path = ?
                AND (
                        qualified_name = ?
                        OR name = ?
                )
                """,
                (
                    workspace_id,
                    edit.file_path,
                    edit.target_symbol,
                    edit.target_symbol,
                ),
            ).fetchone()

            if row is None:

                raise RuntimeError(
                    "Model selected an unknown "
                    "target symbol: "
                    f"{edit.target_symbol} "
                    f"in {edit.file_path}"
                )

    for edit in edits:

        if (
            edit.file_path
            not in allowed_files
        ):

            raise RuntimeError(
                "Model attempted to edit "
                "a file that was not supplied "
                "as repository context: "
                f"{edit.file_path}"
            )

    return (
        payload.get(
            "summary",
            "",
        ),

        edits,

        context,
    )