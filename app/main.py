from fastapi import FastAPI

app = FastAPI(
    title="OutrightBot",
    description="Local company-aware coding agent",
    version="0.1.0",
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
