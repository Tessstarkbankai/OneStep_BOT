import json
import re

import httpx

from app.config import (
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
)

from llm.provider import (
    LLMError,
    LLMResponse,
)


def _base_url() -> str:

    return LLM_BASE_URL.rstrip(
        "/"
    )


def get_llm_health() -> dict:

    try:

        response = httpx.get(
            f"{_base_url()}/health",

            timeout=10.0,
        )

        return {
            "reachable": (
                response.status_code
                < 500
            ),

            "status_code": (
                response.status_code
            ),

            "body": response.text[
                :500
            ],
        }

    except Exception as error:

        return {
            "reachable": False,

            "status_code": None,

            "body": str(error),
        }


def get_model_id() -> str:

    if LLM_MODEL != "auto":
        return LLM_MODEL

    try:

        response = httpx.get(
            (
                f"{_base_url()}"
                "/v1/models"
            ),

            timeout=15.0,
        )

        response.raise_for_status()

        data = response.json()

        models = data.get(
            "data",
            [],
        )

        if not models:

            raise LLMError(
                "llama.cpp returned no "
                "models from /v1/models."
            )

        return models[0]["id"]

    except LLMError:
        raise

    except Exception as error:

        raise LLMError(
            "Unable to determine "
            f"llama.cpp model: {error}"
        ) from error


def _repair_truncated_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None

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

    parsed = _parse(text)
    if parsed is not None:
        return parsed

    last_brace = text.rfind("}")
    if last_brace > 0:
        parsed = _parse(text[:last_brace + 1])
        if parsed is not None:
            return parsed

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

    if in_string:
        repaired += '"'

    repaired = re.sub(r",\s*$", "", repaired)
    repaired = re.sub(r":\s*$", ": null", repaired)
    repaired = re.sub(r',\s*"[^"]*"\s*:\s*$', "", repaired)
    repaired = re.sub(r'"[^"]*"\s*:\s*$', "", repaired)
    repaired = re.sub(r",\s*$", "", repaired)

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
        "LLM did not return valid JSON. "
        f"Response: {content[:1000]}"
    )


def chat_json(
    messages: list[dict],

    schema: dict,

    max_tokens: int | None = None,
) -> LLMResponse:

    model_id = get_model_id()

    request_body = {
        "model": model_id,

        "messages": messages,

        "temperature": (
            LLM_TEMPERATURE
        ),

        "repeat_penalty": 1.15,

        "max_tokens": (
            max_tokens
            or LLM_MAX_TOKENS
        ),

        "stream": False,

        "response_format": {
            "type": "json_schema",

            "schema": schema,
        },
    }

    try:

        response = httpx.post(
            (
                f"{_base_url()}"
                "/v1/chat/completions"
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
            "llama.cpp request failed: "
            f"{error}"
        ) from error

    choices = payload.get(
        "choices",
        [],
    )

    if not choices:

        raise LLMError(
            "llama.cpp returned no "
            "completion choices."
        )

    message = choices[0].get(
        "message",
        {},
    )

    content = message.get(
        "content",
        "",
    )

    if not content:

        raise LLMError(
            "llama.cpp returned an "
            "empty message."
        )

    data = _extract_json(
        content
    )

    usage = payload.get(
        "usage",
        {},
    )

    return LLMResponse(
        data=data,

        model=model_id,

        prompt_tokens=(
            usage.get(
                "prompt_tokens"
            )
        ),

        completion_tokens=(
            usage.get(
                "completion_tokens"
            )
        ),
    )
