import json
import re

import httpx

from app.config import (
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_NUM_CTX,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
)

from llm.provider import (
    LLMError,
    LLMResponse,
    ToolChatResponse,
)


def _base_url() -> str:

    return LLM_BASE_URL.rstrip(
        "/"
    )


def get_llm_health() -> dict:

    try:

        response = httpx.get(
            f"{_base_url()}/api/tags",
            timeout=10.0,
        )

        response.raise_for_status()

        payload = response.json()

        available_models = [
            model.get(
                "name",
                ""
            )

            for model in payload.get(
                "models",
                []
            )
        ]

        model_available = any(
            (
                name == LLM_MODEL
                or name.startswith(
                    LLM_MODEL + ":"
                )
            )

            for name in (
                available_models
            )
        )

        return {
            "reachable": True,

            "provider": "ollama",

            "base_url": (
                LLM_BASE_URL
            ),

            "configured_model": (
                LLM_MODEL
            ),

            "model_available": (
                model_available
            ),

            "available_models": (
                available_models
            ),
        }

    except Exception as error:

        return {
            "reachable": False,

            "provider": "ollama",

            "base_url": (
                LLM_BASE_URL
            ),

            "configured_model": (
                LLM_MODEL
            ),

            "model_available": False,

            "available_models": [],

            "error": str(error),
        }


def _repair_truncated_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None

    # Find first opening brace
    start = text.find("{")
    if start == -1:
        return None
    text = text[start:]

    def _parse(s: str) -> dict | None:
        for strict in (True, False):
            try:
                res = json.loads(s, strict=strict)
                if isinstance(res, dict):
                    return res
            except Exception:
                pass
        return None

    # 1. Direct parse
    parsed = _parse(text)
    if parsed is not None:
        return parsed

    # 2. Balanced slice between first and last closing brace
    last_brace = text.rfind("}")
    if last_brace > 0:
        parsed = _parse(text[:last_brace + 1])
        if parsed is not None:
            return parsed

    # 3. Structural repair for truncated JSON
    repaired = text
    in_string = False
    escape = False
    stack = []

    for ch in repaired:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ("{", "["):
                stack.append("}" if ch == "{" else "]")
            elif ch in ("}", "]"):
                if stack and stack[-1] == ch:
                    stack.pop()

    # If cutoff inside an open string literal, close it
    if in_string:
        repaired += '"'

    # Remove trailing unclosed key-values or dangling commas
    repaired = re.sub(r",\s*$", "", repaired)
    repaired = re.sub(r":\s*$", ": null", repaired)
    repaired = re.sub(r',\s*"[^"]*"\s*:\s*$', "", repaired)
    repaired = re.sub(r'"[^"]*"\s*:\s*$', "", repaired)
    repaired = re.sub(r",\s*$", "", repaired)

    # Re-calculate remaining stack on cleaned text
    in_string = False
    escape = False
    final_stack = []
    for ch in repaired:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ("{", "["):
                final_stack.append("}" if ch == "{" else "]")
            elif ch in ("}", "]"):
                if final_stack and final_stack[-1] == ch:
                    final_stack.pop()

    repaired += "".join(reversed(final_stack))

    parsed = _parse(repaired)
    if parsed is not None:
        return parsed

    # 4. Fallback: progressively back up to previous complete element/object
    for pos in range(len(text) - 1, 0, -1):
        if text[pos] in (",", "{", "[", "}"):
            candidate = text[:pos].rstrip(",").strip()
            if not candidate:
                continue
            sub_stack = []
            in_s = False
            esc = False
            for c in candidate:
                if esc:
                    esc = False
                    continue
                if c == "\\":
                    esc = True
                    continue
                if c == '"':
                    in_s = not in_s
                    continue
                if not in_s:
                    if c in ("{", "["):
                        sub_stack.append("}" if c == "{" else "]")
                    elif c in ("}", "]") and sub_stack and sub_stack[-1] == c:
                        sub_stack.pop()
            candidate += "".join(reversed(sub_stack))
            parsed = _parse(candidate)
            if parsed is not None:
                return parsed

    return None


def _extract_json(
    content: str,
) -> dict:

    repaired = _repair_truncated_json(content)
    if isinstance(repaired, dict):
        return repaired

    raise LLMError(
        "Ollama did not return valid JSON. "
        f"Response: {content[:1000]}"
    )


def chat_json(
    messages: list[dict],

    schema: dict,

    max_tokens: int | None = None,
) -> LLMResponse:

    request_body = {
        "model": LLM_MODEL,

        "messages": messages,

        "stream": False,

        #
        # Qwen3 thinking is disabled
        # for normal repository Q&A.
        #
        # Later the patch/reasoning agent
        # can optionally enable it.
        #
        "think": False,

        #
        # Ollama accepts JSON Schema
        # directly in "format".
        #
        "format": schema,

        "options": {
            "temperature": (
                LLM_TEMPERATURE
            ),

            "repeat_penalty": 1.15,

            "num_ctx": (
                LLM_NUM_CTX
            ),

            "num_predict": (
                max_tokens
                or LLM_MAX_TOKENS
            ),
        },

        #
        # Avoid unloading Qwen after
        # every developer question.
        #
        "keep_alive": "30m",
    }

    try:

        response = httpx.post(
            (
                f"{_base_url()}"
                "/api/chat"
            ),

            json=request_body,

            timeout=(
                LLM_TIMEOUT_SECONDS
            ),
        )

        response.raise_for_status()

        payload = (
            response.json()
        )

    except Exception as error:

        raise LLMError(
            "Ollama request failed: "
            f"{error}"
        ) from error

    message = payload.get(
        "message",
        {},
    )

    content = message.get(
        "content",
        "",
    )

    if not content:

        raise LLMError(
            "Ollama returned an "
            "empty response."
        )

    data = _extract_json(
        content
    )

    return LLMResponse(
        data=data,

        model=payload.get(
            "model",
            LLM_MODEL,
        ),

        prompt_tokens=(
            payload.get(
                "prompt_eval_count"
            )
        ),

        completion_tokens=(
            payload.get(
                "eval_count"
            )
        ),
    )
def chat_with_tools(
    messages: list[dict],

    tools: list[dict],

    max_tokens: int = 512,
) -> ToolChatResponse:

    request_body = {
        "model": LLM_MODEL,

        "messages": messages,

        "tools": tools,

        "stream": False,

        "think": False,

        "options": {
            "temperature": (
                LLM_TEMPERATURE
            ),

            "num_ctx": (
                LLM_NUM_CTX
            ),

            #
            # Tool decisions should
            # be short and fast.
            #
            "num_predict": (
                max_tokens
            ),
        },

        "keep_alive": "30m",
    }

    try:

        response = httpx.post(
            (
                f"{_base_url()}"
                "/api/chat"
            ),

            json=request_body,

            timeout=(
                LLM_TIMEOUT_SECONDS
            ),
        )

        response.raise_for_status()

        payload = response.json()

    except Exception as error:

        raise LLMError(
            "Ollama tool request failed: "
            f"{error}"
        ) from error

    message = payload.get(
        "message",
        {},
    )

    if not message:

        raise LLMError(
            "Ollama returned no "
            "tool-chat message."
        )

    return ToolChatResponse(
        message=message,

        model=payload.get(
            "model",
            LLM_MODEL,
        ),

        prompt_tokens=(
            payload.get(
                "prompt_eval_count"
            )
        ),

        completion_tokens=(
            payload.get(
                "eval_count"
            )
        ),
    )
