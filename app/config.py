from pathlib import Path


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
