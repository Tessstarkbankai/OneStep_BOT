from functools import lru_cache

from tree_sitter import Language, Parser

import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript


SUPPORTED_LANGUAGES = {
    "python",
    "javascript",
    "typescript",
    "tsx",
}


@lru_cache(maxsize=None)
def get_language(language_name: str) -> Language:
    if language_name == "python":
        return Language(
            tspython.language()
        )

    if language_name == "javascript":
        return Language(
            tsjavascript.language()
        )

    if language_name == "typescript":
        return Language(
            tstypescript.language_typescript()
        )

    if language_name == "tsx":
        return Language(
            tstypescript.language_tsx()
        )

    raise ValueError(
        f"Unsupported parser language: {language_name}"
    )


def get_parser(language_name: str) -> Parser:
    return Parser(
        get_language(language_name)
    )


def is_language_supported(language_name: str) -> bool:
    return language_name in SUPPORTED_LANGUAGES
