import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import admin_routes, auth_routes, chat_routes, doc_routes, tool_routes
from .config import get_settings
from .observability.logging import configure_logging, request_id_var
from .rag import service as rag_service
from .tools.mock_tools import build_registry


def create_app() -> FastAPI:
    get_settings()  # fail fast on invalid configuration
    configure_logging()
    app = FastAPI(title="Nova", version="0.1.0")

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = str(uuid.uuid4())
        request.state.request_id = rid
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    @app.middleware("http")
    async def upload_size_guard(request: Request, call_next):
        # Reject oversized uploads from the header, before the multipart body is read and spooled.
        if request.method == "POST" and request.url.path == "/api/v1/documents":
            cl = request.headers.get("content-length")
            if cl is None:
                return JSONResponse({"detail": "Content-Length required"}, status_code=411)
            if not cl.isdigit() or int(cl) > get_settings().max_upload_bytes + 65536:
                return JSONResponse({"detail": "Upload too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok"}

    app.state.retriever = rag_service.retrieve
    app.state.tools = build_registry()
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(doc_routes.router)
    app.include_router(tool_routes.router)
    app.include_router(admin_routes.router)
    return app


app = create_app()
