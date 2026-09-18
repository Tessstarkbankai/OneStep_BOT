from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.workspaces import router as workspaces_router
from storage.database import initialize_database
from api.indexing import router as indexing_router
from api.dependencies import router as dependencies_router

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


app.include_router(workspaces_router)
app.include_router(indexing_router)
app.include_router(dependencies_router)
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
