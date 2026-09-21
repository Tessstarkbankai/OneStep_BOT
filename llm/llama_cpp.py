import json

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


def _extract_json(
    content: str,
) -> dict:

    content = content.strip()

    try:

        return json.loads(
            content
        )

    except json.JSONDecodeError:
        pass

    #
    # Defensive fallback in case a
    # model surrounds JSON with text.
    #
    start = content.find("{")
    end = content.rfind("}")

    if (
        start >= 0
        and end > start
    ):

        try:

            return json.loads(
                content[
                    start:end + 1
                ]
            )

        except json.JSONDecodeError:
            pass

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
