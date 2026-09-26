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
from patching.applier import (
    resolve_symbol,
)
from storage.database import (
    get_database,
)
from retrieval.lexical import (
    extract_search_terms,
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
                    "operation": {
                        "type": "string",
                        "enum": [
                            "replace_symbol",
                            "insert_after_symbol",
                            "insert_inside_symbol",
                            "append_file",
                        ],
                    },

                    "file_path": {
                        "type": "string",
                    },

                    "target_symbol": {
                        "type": [
                            "string",
                            "null",
                        ],
                    },

                    "new_text": {
                        "type": "string",
                    },

                    "reason": {
                        "type": "string",
                    },
                },

                "required": [
                    "operation",
                    "file_path",
                    "target_symbol",
                    "new_text",
                ],
            },
        },
    },

    "required": [
        "summary",
        "edits",
    ],
}


PATCH_SYSTEM_PROMPT_BASE = """
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
   qualified name (except for append_file, where
   target_symbol must be null).

   Example:
   PricingService.calculateOffer

3. new_text must contain ONLY the complete replacement
   source for that symbol, or the single new source
   being inserted/appended.

4. Preserve the language's indentation and syntax.

5. Do NOT include markdown code fences (e.g. ```php or ```).
   Return raw code only.

6. Do NOT include language opening or closing tags like
   <?php or ?>. Existing repository files already open
   them. Inserting <?php inside a PHP file causes fatal
   syntax errors.

7. Do not leave trailing whitespace on any line.

8. Do not create or delete files.

9. Prefer existing company helpers rather than
   duplicating functionality.

10. Change only the smallest relevant symbol.

11. Do not modify unrelated formatting.

12. Do not add dependencies unless explicitly asked.

Python will locate the original implementation from
the repository index. Do NOT return old_text.

Return JSON matching the requested schema.
""".strip()

PATCH_EDIT_RULES = """
PATCH EDIT CONTRACT

Every edit MUST use exactly one operation:

1. replace_symbol
   Use ONLY when modifying the internal logic of an EXISTING symbol.
   target_symbol MUST be an EXISTING symbol from the symbol inventory.
   new_text is ONLY the complete replacement code for that symbol.
   NEVER use replace_symbol to add new sibling functions or methods!

2. insert_after_symbol
   Use when ADDING or CREATING a NEW sibling function, method, or class.
   target_symbol MUST be an EXISTING symbol that the new code should be inserted after.
   new_text is ONLY the single new function/method being added. Do NOT repeat target_symbol or surrounding code.

3. insert_inside_symbol
   Use when ADDING a NEW method/member inside an EXISTING class.
   target_symbol MUST be the EXISTING class name.
   new_text is ONLY the single new method/member being added inside the class. Do NOT repeat the class declaration.

4. append_file
   Use when adding new top-level code at the end of the file.
   target_symbol MUST be null.
   new_text is ONLY the new code to append to the end of the file.

CRITICAL RULES FOR new_text AND target_symbol:
- If the task asks to "add", "create", or "implement" a new function:
  Do NOT use replace_symbol! Use insert_after_symbol (anchored to the relevant symbol) or append_file.
- target_symbol is NEVER the name of newly-created code. Choose an EXISTING anchor from the symbol inventory.
- new_text MUST contain ONLY the specific symbol being modified or added.
- NEVER include surrounding, preceding, or subsequent functions in new_text.
- NEVER echo or repeat unchanged code from the file.
- NEVER include <?php or ?> tags. Files are already PHP files.
- NEVER loop or repeat definitions. Once the target code is written, terminate the JSON string immediately.
""".strip()

PATCH_SYSTEM_PROMPT = (
    PATCH_SYSTEM_PROMPT_BASE
    + "\n\n"
    + PATCH_EDIT_RULES
)


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
    task: str = "",
) -> str:
    files = list(
        context.files_inspected
    )

    if not files:
        return ""

    snippet_ranges_by_file = {}
    for snippet in getattr(context, "snippets", []):
        snippet_ranges_by_file.setdefault(snippet.file_path, []).append(
            (snippet.start_line, snippet.end_line)
        )

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
          AND kind IN ('class', 'function', 'method', 'interface', 'trait')

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

    if not rows:
        return ""

    task_terms = [t.lower() for t in extract_search_terms(task)] if task else []

    relevant_symbols = []
    other_symbols = []

    for row in rows:
        fpath = row["file_path"]
        s_start = row["start_line"]
        s_end = row["end_line"]
        name_lower = (row["name"] or "").lower()
        qname_lower = (row["qualified_name"] or "").lower()

        ranges = snippet_ranges_by_file.get(fpath, [])
        is_near_snippet = any(
            (s_start <= r_end + 30 and s_end >= r_start - 30)
            for r_start, r_end in ranges
        )
        matches_task_keyword = any(
            len(term) >= 4 and (term in name_lower or term in qname_lower)
            for term in task_terms
        )

        if is_near_snippet or matches_task_keyword:
            relevant_symbols.append(row)
        else:
            other_symbols.append(row)

    # Sort relevant symbols so direct task term matches are at the very top
    def _relevance_key(r):
        nl = (r["name"] or "").lower()
        ql = (r["qualified_name"] or "").lower()
        match_count = sum(1 for t in task_terms if len(t) >= 4 and (t in nl or t in ql))
        return -match_count

    relevant_symbols.sort(key=_relevance_key)

    sections = []
    if relevant_symbols:
        relevant_text = "\n".join(
            (
                f"- file={row['file_path']} "
                f"name={row['qualified_name']} "
                f"kind={row['kind']} "
                f"lines={row['start_line']}-{row['end_line']} "
                f"signature={(row['signature'] or '')[:100]}"
            )
            for row in relevant_symbols[:25]
        )
        sections.append(
            "PRIMARY ANCHOR SYMBOLS (Most relevant to the retrieved code and task):\n"
            + relevant_text
        )

    remaining_budget = max(0, 35 - len(relevant_symbols[:25]))
    if other_symbols and remaining_budget > 0:
        other_text = "\n".join(
            (
                f"- file={row['file_path']} "
                f"name={row['qualified_name']} "
                f"kind={row['kind']} "
                f"lines={row['start_line']}-{row['end_line']} "
                f"signature={(row['signature'] or '')[:100]}"
            )
            for row in other_symbols[:remaining_budget]
        )
        sections.append(
            "OTHER SYMBOLS IN FILE(S):\n"
            + other_text
        )

    symbol_inventory = "\n\n".join(sections)

    return (
        f"""
EXACT EXISTING SYMBOL INVENTORY

{symbol_inventory}

For any operation except append_file,
target_symbol MUST match one of the symbol names above.
""".strip()
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
            task=task,
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

        max_tokens=1500,
    )

    payload = response.data

    edits = []
    for item in payload.get("edits", []):
        if not isinstance(item, dict):
            continue
        if "reason" not in item or item["reason"] is None:
            item["reason"] = ""
        try:
            edits.append(ProposedEdit(**item))
        except Exception as error:
            raise RuntimeError(
                f"Model proposed an invalid edit structure: {error}"
            ) from error

    if not edits:

        raise RuntimeError(
            "Model did not propose "
            "any edits."
        )

    allowed_files = set(
        context.files_inspected
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

        if edit.operation == "append_file":

            if edit.target_symbol is not None:

                raise RuntimeError(
                    "append_file operation must "
                    "have a null target_symbol, "
                    f"got: {edit.target_symbol}"
                )

            # No symbol lookup needed: append_file
            # targets the file itself, not a symbol.
            continue

        if edit.target_symbol is None:

            raise RuntimeError(
                "Operation "
                f"'{edit.operation}' requires a "
                "non-null target_symbol."
            )

        try:
            resolved = resolve_symbol(
                workspace_id=workspace_id,
                file_path=edit.file_path,
                target_symbol=edit.target_symbol,
            )

            # Normalize edit.target_symbol to canonical qualified_name
            if resolved:
                target_qname = resolved["qualified_name"] if "qualified_name" in resolved else None
                if target_qname:
                    edit.target_symbol = target_qname

        except Exception as error:
            raise RuntimeError(str(error)) from error

    return (
        payload.get(
            "summary",
            "",
        ),

        edits,

        context,
    )