from collections import defaultdict
from pathlib import Path

from patching.models import (
    ProposedEdit,
)

from storage.database import (
    get_database,
)


class PatchApplyError(
    RuntimeError
):
    pass


def _resolve_symbol(
    workspace_id: str,
    edit: ProposedEdit,
):

    with get_database() as database:

        rows = database.execute(
            """
            SELECT
                file_path,
                name,
                qualified_name,
                kind,
                start_line,
                end_line

            FROM code_symbols

            WHERE workspace_id = ?
              AND file_path = ?
              AND (
                    qualified_name = ?
                    OR name = ?
              )

            ORDER BY start_line
            """,
            (
                workspace_id,
                edit.file_path,
                edit.target_symbol,
                edit.target_symbol,
            ),
        ).fetchall()

    if not rows:

        raise PatchApplyError(
            "Target symbol was not found "
            "in the repository index: "
            f"{edit.target_symbol} "
            f"in {edit.file_path}. "
            "Re-index the repository if "
            "the source recently changed."
        )

    if len(rows) > 1:

        matches = [
            row["qualified_name"]
            for row in rows
        ]

        raise PatchApplyError(
            "Target symbol is ambiguous: "
            f"{edit.target_symbol}. "
            f"Matches: {matches}"
        )

    return rows[0]


def _safe_target(
    sandbox: Path,
    file_path: str,
) -> Path:

    sandbox = sandbox.resolve()

    target = (
        sandbox / file_path
    ).resolve()

    try:

        target.relative_to(
            sandbox
        )

    except ValueError:

        raise PatchApplyError(
            "Patch attempted to access "
            "outside sandbox."
        )

    if not target.exists():

        raise PatchApplyError(
            "Patch target does not exist: "
            f"{file_path}"
        )

    return target

def _preserve_first_line_indent(
    old_segment: str,
    replacement: str,
) -> str:

    old_lines = old_segment.splitlines(
        keepends=True
    )

    new_lines = replacement.splitlines(
        keepends=True
    )

    if not old_lines or not new_lines:
        return replacement

    old_first = old_lines[0]

    original_indent = old_first[
        :len(old_first)
        - len(old_first.lstrip(" \t"))
    ]

    #
    # Always force the replacement
    # symbol's first line to use the
    # original symbol indentation.
    #
    new_lines[0] = (
        original_indent
        + new_lines[0].lstrip(" \t")
    )

    return "".join(
        new_lines
    )
def apply_edits(
    workspace_id: str,
    sandbox: Path,
    edits: list[ProposedEdit],
):

    resolved = []

    for edit in edits:

        symbol = _resolve_symbol(
            workspace_id,
            edit,
        )

        resolved.append(
            {
                "edit": edit,
                "start_line": int(
                    symbol["start_line"]
                ),
                "end_line": int(
                    symbol["end_line"]
                ),
                "qualified_name": (
                    symbol[
                        "qualified_name"
                    ]
                ),
            }
        )

    #
    # Check for overlapping edits.
    #
    by_file = defaultdict(list)

    for item in resolved:

        by_file[
            item["edit"].file_path
        ].append(item)

    for file_path, items in (
        by_file.items()
    ):

        ordered = sorted(
            items,
            key=lambda item:
            item["start_line"],
        )

        previous_end = 0

        for item in ordered:

            if (
                item["start_line"]
                <= previous_end
            ):

                raise PatchApplyError(
                    "Patch contains overlapping "
                    "symbol edits in "
                    f"{file_path}."
                )

            previous_end = (
                item["end_line"]
            )

    changed = []

    for file_path, items in (
        by_file.items()
    ):

        target = _safe_target(
            sandbox,
            file_path,
        )

        source = target.read_text(
            encoding="utf-8",
            errors="replace",
        )

        lines = source.splitlines(
            keepends=True
        )

        #
        # Process bottom-to-top so an
        # earlier replacement cannot
        # shift later indexed ranges.
        #
        items = sorted(
            items,
            key=lambda item:
            item["start_line"],
            reverse=True,
        )

        for item in items:

            start = (
                item["start_line"] - 1
            )

            end = item["end_line"]

            if (
                start < 0
                or end > len(lines)
                or start >= end
            ):

                raise PatchApplyError(
                    "Indexed symbol range is "
                    "invalid for "
                    f"{item['qualified_name']} "
                    f"in {file_path}. "
                    "Re-index the repository."
                )

            old_segment = "".join(
                lines[start:end]
            )

            replacement = (
                item["edit"].new_text
            )
            replacement = (
                _preserve_first_line_indent(
                    old_segment,
                    replacement,
                )
            )
            #
            # Preserve normal file newline
            # behavior at the replaced
            # symbol boundary.
            #
            if (
                old_segment.endswith("\n")
                and not replacement.endswith(
                    "\n"
                )
            ):

                replacement += "\n"

            replacement_lines = (
                replacement.splitlines(
                    keepends=True
                )
            )

            lines[start:end] = (
                replacement_lines
            )

        target.write_text(
            "".join(lines),
            encoding="utf-8",
        )

        changed.append(
            file_path
        )

    return sorted(changed)