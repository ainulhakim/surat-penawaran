import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.seed import seed_initial_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    version="0.1.0",
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
