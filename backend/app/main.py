import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.comments import router as comments_router
from app.api.videos import router as videos_router
from app.api.semantic_search import router as semantic_search_router
from app.api.replies import comment_reply_router, reply_router
from app.api.opportunities import router as opportunities_router
from app.api.public_settings import router as public_settings_router
from app.api.dashboard import router as dashboard_router
from app.api.channels import router as channels_router
from app.api.quick_analyze import router as quick_analyze_router
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(ingestion_router)
app.include_router(comments_router)
app.include_router(videos_router)
app.include_router(semantic_search_router)
app.include_router(comment_reply_router)
app.include_router(reply_router)
app.include_router(opportunities_router)
app.include_router(public_settings_router)
app.include_router(dashboard_router)
app.include_router(channels_router)
app.include_router(quick_analyze_router)
