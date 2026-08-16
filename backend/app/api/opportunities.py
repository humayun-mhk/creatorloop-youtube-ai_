from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.schemas.opportunity import OpportunityRead, OpportunityRebuildResponse
from app.schemas.brief import ContentBriefRead
from app.services.brief_generator import BriefProviderError, InvalidGeneratedBriefError
from app.services.content_briefs import BriefThresholdError, ContentBriefService, OpportunityNotFoundError
from app.services.embeddings import EmbeddingProviderError
from app.services.opportunities import OpportunitiesService

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


def get_opportunities_service(
    db: Annotated[Session, Depends(get_db)],
) -> OpportunitiesService:
    return OpportunitiesService(db, get_settings())


def get_content_brief_service(
    db: Annotated[Session, Depends(get_db)],
) -> ContentBriefService:
    return ContentBriefService(db, get_settings())


@router.post("/{opportunity_id}/brief", response_model=ContentBriefRead)
def generate_content_brief(
    opportunity_id: int,
    service: Annotated[ContentBriefService, Depends(get_content_brief_service)],
) -> ContentBriefRead:
    try:
        return ContentBriefRead.model_validate(service.generate(opportunity_id).brief)
    except OpportunityNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "opportunity_not_found", "message": "Opportunity not found"}) from exc
    except BriefThresholdError as exc:
        raise HTTPException(status_code=409, detail={"code": "brief_not_eligible", "message": str(exc)}) from exc
    except InvalidGeneratedBriefError as exc:
        raise HTTPException(status_code=502, detail={"code": "invalid_model_response", "message": str(exc)}) from exc
    except BriefProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": "brief_generation_unavailable", "message": str(exc)}) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail={"code": "database_error", "message": "Unable to generate content brief"}) from exc


@router.post("/rebuild", response_model=OpportunityRebuildResponse)
def rebuild_opportunities(
    service: Annotated[OpportunitiesService, Depends(get_opportunities_service)],
) -> OpportunityRebuildResponse:
    try:
        result = service.rebuild()
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "embedding_unavailable", "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_error", "message": "Unable to rebuild opportunities"},
        ) from exc
    return OpportunityRebuildResponse(
        status="rebuilt",
        eligible_comments=result.eligible_comments,
        opportunities_created=result.opportunities_created,
    )


@router.get("", response_model=list[OpportunityRead])
def list_opportunities(
    service: Annotated[OpportunitiesService, Depends(get_opportunities_service)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[OpportunityRead]:
    return [
        OpportunityRead.model_validate(item)
        for item in service.list_opportunities(offset, limit)
    ]


@router.get("/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(
    opportunity_id: int,
    service: Annotated[OpportunitiesService, Depends(get_opportunities_service)],
) -> OpportunityRead:
    opportunity = service.get(opportunity_id)
    if opportunity is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "opportunity_not_found", "message": "Opportunity not found"},
        )
    return OpportunityRead.model_validate(opportunity)
