import json
import re
import subprocess

from pathlib import Path

from retrieval.models import (
    LexicalMatch,
)


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "code",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "our",
    "please",
    "should",
    "that",
    "the",
    "their",
    "this",
    "to",
    "we",
    "what",
    "where",
    "which",
    "why",
    "with",
}


def extract_search_terms(
    query: str,
) -> list[str]:

    raw_tokens = re.findall(
        r"""
        [A-Za-z_]
        [A-Za-z0-9_
        .$:/\\-]*
        """,
        query,
        re.VERBOSE,
    )

    terms = []

    for token in raw_tokens:

        token = token.strip(
            ".,:;()[]{}'\""
        )

        if not token:
            continue

        variants = [token]

        pieces = re.split(
            r"[_\-.:/\\]+",
            token,
        )

        variants.extend(
            pieces
        )

        for piece in pieces:

            camel_parts = re.findall(
                r"""
                [A-Z]+(?=[A-Z][a-z]|\b)
                |
                [A-Z]?[a-z]+
                |
                [0-9]+
                """,
                piece,
                re.VERBOSE,
            )

            variants.extend(
                camel_parts
            )

        for variant in variants:

            variant = variant.strip()

            if not variant:
                continue

            lowered = (
                variant.lower()
            )

            if lowered in STOP_WORDS:
                continue

            if len(lowered) < 2:
                continue

            if lowered not in [
                item.lower()
                for item in terms
            ]:
                terms.append(
                    variant
                )

    #
    # Avoid producing a giant rg regex
    # from extremely long prompts.
    #
    return terms[:12]


def lexical_search(
    root_path: Path,
    known_files: set[str],
    terms: list[str],
    max_matches: int = 250,
    max_matches_per_file: int = 12,
) -> dict[str, list[LexicalMatch]]:

    if not terms:
        return {}

    pattern = "|".join(
        re.escape(term)
        for term in terms
    )

    command = [
        "rg",

        "--json",

        "--line-number",

        "--ignore-case",

        "--color",
        "never",

        "-e",
        pattern,

        ".",
    ]

    try:

        result = subprocess.run(
            command,

            cwd=root_path,

            capture_output=True,

            text=True,

            errors="replace",
        )

    except FileNotFoundError:

        raise RuntimeError(
            "ripgrep (rg) is not installed."
        )

    #
    # rg exit codes:
    #
    # 0 = matches
    # 1 = no matches
    # 2+ = error
    #
    if result.returncode == 1:
        return {}

    if result.returncode > 1:

        raise RuntimeError(
            "ripgrep search failed: "
            + result.stderr[:1000]
        )

    matches_by_file = {}

    total_matches = 0

    lowered_terms = [
        term.lower()
        for term in terms
    ]

    for output_line in (
        result.stdout.splitlines()
    ):

        try:
            event = json.loads(
                output_line
            )

        except json.JSONDecodeError:
            continue

        if event.get("type") != "match":
            continue

        data = event.get(
            "data",
            {},
        )

        path_text = (
            data.get(
                "path",
                {},
            ).get(
                "text"
            )
        )

        if not path_text:
            continue

        if path_text.startswith(
            "./"
        ):
            path_text = (
                path_text[2:]
            )

        path_text = (
            Path(path_text)
            .as_posix()
        )

        #
        # Very important:
        # only accept files that passed
        # our repository scanner.
        #
        if path_text not in known_files:
            continue

        current_matches = (
            matches_by_file.setdefault(
                path_text,
                [],
            )
        )

        if (
            len(current_matches)
            >= max_matches_per_file
        ):
            continue

        line_text = (
            data.get(
                "lines",
                {},
            ).get(
                "text",
                "",
            )
        ).rstrip()

        line_lower = (
            line_text.lower()
        )

        matched_terms = [
            terms[index]
            for index, lowered
            in enumerate(
                lowered_terms
            )
            if lowered in line_lower
        ]

        current_matches.append(
            LexicalMatch(
                line=data.get(
                    "line_number",
                    0,
                ),

                text=line_text[
                    :500
                ],

                matched_terms=(
                    matched_terms
                ),
            )
        )

        total_matches += 1

        if (
            total_matches
            >= max_matches
        ):
            break

    return matches_by_file
