from pathlib import Path
import os


LLM_BASE_URL = os.getenv(
    "OUTRIGHTBOT_LLM_BASE_URL",
    "http://127.0.0.1:11434",
)

LLM_MODEL = os.getenv(
    "OUTRIGHTBOT_LLM_MODEL",
    "qwen3:8b",
)

LLM_TIMEOUT_SECONDS = float(
    os.getenv(
        "OUTRIGHTBOT_LLM_TIMEOUT",
        "300",
    )
)

LLM_MAX_TOKENS = int(
    os.getenv(
        "OUTRIGHTBOT_LLM_MAX_TOKENS",
        "400",
    )
)

LLM_TEMPERATURE = float(
    os.getenv(
        "OUTRIGHTBOT_LLM_TEMPERATURE",
        "0.1",
    )
)

LLM_NUM_CTX = int(
    os.getenv(
        "OUTRIGHTBOT_LLM_NUM_CTX",
        "8192",
    )
)
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
WORKSPACES_DIR = BASE_DIR / "workspaces"

DATABASE_PATH = DATA_DIR / "outrightbot.db"
VECTOR_DIR = DATA_DIR / "vectors"

def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    VECTOR_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )   
