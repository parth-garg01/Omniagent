import uuid

from fastapi import FastAPI, Request

from .api import auth_routes
from .config import get_settings


def create_app() -> FastAPI:
    get_settings()  # fail fast on invalid configuration
    app = FastAPI(title="Nova", version="0.1.0")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(auth_routes.router)
    return app


app = create_app()
