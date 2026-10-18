import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.seed import seed_initial_data
from app.web.deps import Forbidden, NotAuthenticated
from app.web.routes import TEMPLATE_DIR, web_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.AUTO_CREATE_TABLES:
        import app.models  # noqa: F401  (register metadata)

        Base.metadata.create_all(bind=engine)
        logger.info("tabel dipastikan tersedia")
    try:
        seed_initial_data()
    except Exception as exc:  # pragma: no cover
        logger.warning("seed gagal: %s", exc)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.2.0",
    description="Web Apps Surat Penawaran Multi Wilayah (Pusat & Wilayah)",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENV}


app.include_router(api_router, prefix="/api/v1")


# ---------------------------- UI (Jinja2 + Bootstrap) ---------------------------- #
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(NotAuthenticated)
async def _not_authenticated(request: Request, exc: NotAuthenticated):
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(f"/login?next={target}", status_code=303)


@app.exception_handler(Forbidden)
async def _forbidden(request: Request, exc: Forbidden):
    from app.db.session import SessionLocal
    from app.models import User
    from app.web.routes import render_error
    from app.web.session import user_id_from_request

    user = None
    try:
        db = SessionLocal()
        try:
            uid = user_id_from_request(request)
            user = db.get(User, uid) if uid else None
        finally:
            db.close()
    except Exception:  # pragma: no cover
        user = None
    return render_error(request, 403, exc.message, user=user)


app.include_router(web_router)
