import json

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
    # Defensive fallback.
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

    max_tokens: int = 160,
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
