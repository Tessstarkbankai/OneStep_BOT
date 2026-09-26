from collections import defaultdict
from pathlib import Path
import re
import textwrap
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


def _sanitize_new_text(
    new_text: str,
    file_path: str,
) -> str:
    if not new_text:
        return ""

    text = new_text

    # 1. Strip markdown code fences (e.g. ```php ... ``` or ``` ... ```)
    fence_match = re.match(
        r"^\s*```(?:[a-zA-Z0-9_-]+)?\r?\n([\s\S]*?)\r?\n\s*```\s*$",
        text,
    )
    if fence_match:
        text = fence_match.group(1)
    else:
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # 2. For PHP files: strip leading <?php / <? and trailing ?>
    is_php = file_path.lower().endswith(
        (".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".php8")
    )
    if is_php:
        text = re.sub(
            r"^\s*<\?(?:php)?\b[ \t]*\r?\n?",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\r?\n?[ \t]*\?>\s*$",
            "",
            text,
        )

    # 3. Strip trailing whitespace from every line
    lines = [
        line.rstrip(" \t\r")
        for line in text.splitlines()
    ]
    text = "\n".join(lines)

    return text

def _leading_indent(
    text: str,
) -> str:

    first_line = (
        text.splitlines()[0]
        if text.splitlines()
        else ""
    )

    return first_line[
        : len(first_line)
        - len(first_line.lstrip())
    ]


def _indent_block(
    text: str,
    indent: str,
) -> str:

    cleaned = textwrap.dedent(
        text
    ).strip("\n")

    if not cleaned:

        return ""

    lines = cleaned.splitlines()

    return "\n".join(
        (
            indent + line
            if line.strip()
            else ""
        )
        for line in lines
    )


def _insert_after_segment(
    source: str,
    start_line: int,
    end_line: int,
    new_text: str,
) -> str:

    lines = source.splitlines(
        keepends=True
    )

    start_index = max(
        0,
        start_line - 1,
    )

    end_index = max(
        start_index,
        end_line,
    )

    old_segment = "".join(
        lines[
            start_index:end_index
        ]
    )

    indent = _leading_indent(
        old_segment
    )

    insertion = _indent_block(
        new_text,
        indent,
    )

    if not insertion.endswith(
        "\n"
    ):

        insertion += "\n"

    before = "".join(
        lines[:end_index]
    )

    after = "".join(
        lines[end_index:]
    )

    if (
        before
        and not before.endswith(
            "\n"
        )
    ):

        before += "\n"

    return (
        before
        + insertion
        + after
    )


def _insert_inside_braced_symbol(
    source: str,
    start_line: int,
    end_line: int,
    new_text: str,
) -> str:

    lines = source.splitlines(
        keepends=True
    )

    start_index = max(
        0,
        start_line - 1,
    )

    end_index = max(
        start_index + 1,
        end_line,
    )

    segment = "".join(
        lines[
            start_index:end_index
        ]
    )

    closing_index = (
        segment.rfind(
            "}"
        )
    )

    if closing_index < 0:

        raise RuntimeError(
            "Target symbol has no closing "
            "brace for inside insertion."
        )

    class_indent = (
        _leading_indent(
            segment
        )
    )

    child_indent = (
        class_indent
        + "    "
    )

    insertion = _indent_block(
        new_text,
        child_indent,
    )

    if not insertion.endswith(
        "\n"
    ):

        insertion += "\n"

    before_closing = (
        segment[
            :closing_index
        ]
    )

    closing_and_after = (
        segment[
            closing_index:
        ]
    )

    if (
        before_closing
        and not before_closing.endswith(
            "\n"
        )
    ):

        before_closing += "\n"

    new_segment = (
        before_closing
        + insertion
        + class_indent
        + closing_and_after.lstrip()
    )

    return (
        "".join(
            lines[:start_index]
        )
        + new_segment
        + "".join(
            lines[end_index:]
        )
    )


def _append_to_file(
    source: str,
    new_text: str,
    file_path: str | None = None,
) -> str:

    # If it's a PHP file and ends with ?>, remove the closing tag before appending
    if file_path and file_path.lower().endswith(
        (".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".php8")
    ):
        stripped = source.rstrip()
        if stripped.endswith("?>"):
            source = stripped[:-2].rstrip() + "\n"

    addition = textwrap.dedent(
        new_text
    ).strip("\n")

    if not source.endswith(
        "\n"
    ):

        source += "\n"

    return (
        source
        + "\n"
        + addition
        + "\n"
    )


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


def _replace_symbol_range(
    source: str,
    start_line: int,
    end_line: int,
    replacement: str,
    symbol_name: str | None = None,
    file_path: str | None = None,
) -> str:

    lines = source.splitlines(
        keepends=True
    )

    start = start_line - 1

    end = end_line

    if (
        start < 0
        or end > len(lines)
        or start >= end
    ):

        raise PatchApplyError(
            "Indexed symbol range is "
            "invalid for "
            f"{symbol_name or '<unknown>'} "
            f"in {file_path or '<unknown>'}. "
            "Re-index the repository."
        )

    old_segment = "".join(
        lines[start:end]
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

    return "".join(lines)


def resolve_symbol(
    workspace_id: str,
    file_path: str,
    target_symbol: str,
):

    #
    # Load every indexed symbol for this
    # file so we can (a) attempt an exact
    # match, (b) attempt a safe qualified
    # -name fallback, and (c) build a
    # helpful "existing symbols" listing
    # if nothing matches.
    #
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

            ORDER BY start_line
            """,
            (
                workspace_id,
                file_path,
            ),
        ).fetchall()

    if not rows:

        raise PatchApplyError(
            "No indexed symbols were found "
            f"for file: {file_path}. "
            "Re-index the repository if "
            "the source recently changed."
        )

    requested = (
        target_symbol.strip()
    )

    exact = [
        row
        for row in rows
        if row["qualified_name"]
        == requested
        or row["name"] == requested
    ]

    if len(exact) == 1:

        return dict(exact[0])

    if len(exact) > 1:

        matches = [
            row["qualified_name"]
            for row in exact
        ]

        raise PatchApplyError(
            "Target symbol is ambiguous: "
            f"{requested}. "
            f"Matches: {matches}"
        )

    #
    # Safe qualified-name fallback:
    #
    # PricingService.calculateOffer
    #                 ?
    # calculateOffer
    #
    # Only applied when the shortened
    # name uniquely exists in this same
    # file. This is normalization, not
    # fuzzy matching: it never accepts a
    # symbol name that doesn't truly
    # exist.
    #
    short_name = (
        requested
        .replace("::", ".")
        .split(".")[-1]
    )

    short_matches = [
        row
        for row in rows
        if row["name"] == short_name
    ]

    if len(short_matches) == 1:

        return dict(short_matches[0])

    if len(short_matches) > 1:

        matches = [
            row["qualified_name"]
            for row in short_matches
        ]

        raise PatchApplyError(
            "Target symbol is ambiguous: "
            f"{requested}. "
            f"Matches: {matches}"
        )

    #
    # Truly unknown: give Qwen a
    # complete, exact listing of what
    # does exist in this file so its one
    # repair attempt has strong grounding.
    #
    available_names = [
        row["qualified_name"]
        or row["name"]
        for row in rows
    ]

    raise PatchApplyError(
        "Model selected an unknown "
        f"target symbol: {requested} "
        f"in {file_path}.\n"
        "Existing symbols:\n- "
        + "\n- ".join(
            available_names
        )
    )


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


def apply_edits(
    workspace_id: str,
    sandbox: Path,
    edits: list[ProposedEdit],
):

    #
    # Resolve every edit's operation and,
    # for symbol-based operations, its
    # indexed symbol range. append_file
    # edits have no symbol and are kept
    # with start_line/end_line = None.
    #
    by_file = defaultdict(list)

    for edit in edits:

        operation = (
            edit.operation
            or "replace_symbol"
        )

        if operation == "append_file":

            by_file[
                edit.file_path
            ].append(
                {
                    "edit": edit,
                    "operation": operation,
                    "start_line": None,
                    "end_line": None,
                    "qualified_name": None,
                }
            )

            continue

        if not edit.target_symbol:

            raise PatchApplyError(
                f"Operation {operation} "
                "requires target_symbol."
            )

        symbol = resolve_symbol(
            workspace_id=workspace_id,
            file_path=edit.file_path,
            target_symbol=(
                edit.target_symbol
            ),
        )

        if symbol is None:

            raise PatchApplyError(
                "Model selected an unknown "
                "target symbol: "
                f"{edit.target_symbol} "
                f"in {edit.file_path}"
            )

        by_file[
            edit.file_path
        ].append(
            {
                "edit": edit,
                "operation": operation,
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
    # Only symbol-anchored edits (i.e.
    # not append_file) participate,
    # since append_file has no range.
    #
    for file_path, items in (
        by_file.items()
    ):

        symbol_items = [
            item
            for item in items
            if item["start_line"]
            is not None
        ]

        ordered = sorted(
            symbol_items,
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

        raw_bytes = target.read_bytes()
        has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
        if has_bom:
            raw_bytes = raw_bytes[3:]

        has_crlf = b"\r\n" in raw_bytes

        source = raw_bytes.decode(
            "utf-8",
            errors="replace",
        ).replace("\r\n", "\n")

        symbol_items = [
            item
            for item in items
            if item["start_line"]
            is not None
        ]

        append_items = [
            item
            for item in items
            if item["start_line"]
            is None
        ]

        #
        # Process bottom-to-top so an
        # earlier replacement/insertion
        # cannot shift later indexed
        # ranges.
        #
        symbol_items = sorted(
            symbol_items,
            key=lambda item:
            item["start_line"],
            reverse=True,
        )

        for item in symbol_items:

            operation = item[
                "operation"
            ]

            edit = item["edit"]
            sanitized_text = _sanitize_new_text(
                edit.new_text,
                file_path,
            )

            if (
                operation
                == "replace_symbol"
            ):

                source = (
                    _replace_symbol_range(
                        source=source,
                        start_line=(
                            item[
                                "start_line"
                            ]
                        ),
                        end_line=(
                            item[
                                "end_line"
                            ]
                        ),
                        replacement=sanitized_text,
                        symbol_name=(
                            item[
                                "qualified_name"
                            ]
                        ),
                        file_path=(
                            file_path
                        ),
                    )
                )

            elif (
                operation
                == "insert_after_symbol"
            ):

                source = (
                    _insert_after_segment(
                        source=source,
                        start_line=(
                            item[
                                "start_line"
                            ]
                        ),
                        end_line=(
                            item[
                                "end_line"
                            ]
                        ),
                        new_text=sanitized_text,
                    )
                )

            elif (
                operation
                == "insert_inside_symbol"
            ):

                source = (
                    _insert_inside_braced_symbol(
                        source=source,
                        start_line=(
                            item[
                                "start_line"
                            ]
                        ),
                        end_line=(
                            item[
                                "end_line"
                            ]
                        ),
                        new_text=sanitized_text,
                    )
                )

            else:

                raise PatchApplyError(
                    "Unsupported patch "
                    f"operation: {operation}"
                )

        #
        # append_file edits don't depend
        # on line numbers, so apply them
        # last, in the order they were
        # given.
        #
        for item in append_items:

            sanitized_text = _sanitize_new_text(
                item["edit"].new_text,
                file_path,
            )

            source = _append_to_file(
                source,
                sanitized_text,
                file_path=file_path,
            )

        if has_crlf:
            source = source.replace("\r\n", "\n").replace("\n", "\r\n")

        output_bytes = source.encode("utf-8")
        if has_bom:
            output_bytes = b"\xef\xbb\xbf" + output_bytes

        target.write_bytes(output_bytes)

        changed.append(
            file_path
        )

    return sorted(changed)