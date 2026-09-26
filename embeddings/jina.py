import os
from functools import (
    lru_cache,
)

from sentence_transformers import (
    SentenceTransformer,
)

# Optimize PyTorch CPU multi-threading on CPU-only machines
try:
    import torch
    cpu_count = os.cpu_count() or 4
    torch.set_num_threads(min(cpu_count, 8))
except Exception:
    pass


MODEL_NAME = (
    "jinaai/"
    "jina-embeddings-v2-base-code"
)


MAX_SEQUENCE_LENGTH = 1024
CPU_BATCH_SIZE = 32


@lru_cache(maxsize=1)
def get_embedding_model():
    model = SentenceTransformer(
        MODEL_NAME,

        trust_remote_code=True,

        device="cpu",
    )

    model.max_seq_length = (
        MAX_SEQUENCE_LENGTH
    )

    return model


def embed_texts(
    texts: list[str],

    batch_size: int = CPU_BATCH_SIZE,
) -> list[list[float]]:

    if not texts:
        return []

    model = get_embedding_model()

    embeddings = model.encode(
        texts,

        batch_size=batch_size,

        show_progress_bar=True,

        normalize_embeddings=True,

        convert_to_numpy=True,
    )

    return [
        vector.astype(
            "float32"
        ).tolist()

        for vector in embeddings
    ]


def build_embedding_text(
    file_path: str,

    language: str,

    symbol_name: str | None,

    symbol_kind: str | None,

    content: str,
) -> str:

    parts = [
        f"File: {file_path}",

        f"Language: {language}",
    ]

    if symbol_name:

        parts.append(
            f"Symbol: {symbol_name}"
        )

    if symbol_kind:

        parts.append(
            f"Kind: {symbol_kind}"
        )

    parts.append(
        "Code:\n" + content
    )

    return "\n".join(
        parts
    )
