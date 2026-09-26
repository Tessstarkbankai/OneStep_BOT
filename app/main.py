from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.workspaces import router as workspaces_router
from storage.database import initialize_database
from api.indexing import router as indexing_router
from api.dependencies import router as dependencies_router
from api.calls import router as calls_router
from api.relations import router as relations_router
from api.repository import (
    router as repository_router,
)
from api.retrieval import (
    router as retrieval_router,
)
from api.semantic import (
    router as semantic_router,
)
from api.ask import (
    router as ask_router,
)
from api.agent import (
    router as agent_router,
)
from api.assistant import (
    router as assistant_router,
)
from api.patches import (
    router as patches_router,
)
from api.index_state import (
    router as index_state_router,
)
from api.ui import (
    router as ui_router,
)
@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()

    yield


app = FastAPI(
    title="OutrightBot",
    description="Local company-aware coding agent",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(
    ui_router
)

app.include_router(workspaces_router)
app.include_router(indexing_router)
app.include_router(dependencies_router)
app.include_router(calls_router)
app.include_router(relations_router)
app.include_router(
    repository_router
)
app.include_router(
    index_state_router
)
app.include_router(
    retrieval_router
)
app.include_router(
    semantic_router
)
app.include_router(
    ask_router
)
app.include_router(
    agent_router
)
app.include_router(
    assistant_router
)
app.include_router(
    patches_router
)
@app.get("/")
def root():
    return {
        "name": "OutrightBot",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }
