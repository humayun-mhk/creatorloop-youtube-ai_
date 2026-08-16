from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.dashboard import DashboardMetrics
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_dashboard_service(db: Annotated[Session, Depends(get_db)]) -> DashboardService:
    return DashboardService(db)


@router.get("/summary", response_model=DashboardMetrics)
def dashboard_summary(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardMetrics:
    try:
        return service.metrics()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "database_error", "message": "Unable to load dashboard metrics"},
        ) from exc
