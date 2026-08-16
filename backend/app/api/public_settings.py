from fastapi import APIRouter

from app.config import get_settings
from app.schemas.public_settings import PublicSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/public", response_model=PublicSettings)
def public_settings() -> PublicSettings:
    settings = get_settings()
    return PublicSettings(
        semantic_match_threshold=settings.semantic_match_threshold,
        content_brief_threshold=settings.content_brief_threshold,
    )
