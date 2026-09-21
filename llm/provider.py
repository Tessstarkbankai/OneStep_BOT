from dataclasses import dataclass


class LLMError(
    RuntimeError
):
    pass


@dataclass
class LLMResponse:
    data: dict

    model: str

    prompt_tokens: (
        int | None
    ) = None

    completion_tokens: (
        int | None
    ) = None
@dataclass
class ToolChatResponse:
    message: dict

    model: str

    prompt_tokens: (
        int | None
    ) = None

    completion_tokens: (
        int | None
    ) = None
