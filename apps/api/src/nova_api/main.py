from fastapi import FastAPI

from .config import get_settings


def create_app() -> FastAPI:
    get_settings()  # fail fast on invalid configuration
    app = FastAPI(title="Nova", version="0.1.0")

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
