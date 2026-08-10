from typing import Annotated

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.analytics_service import AnalyticsService
from src.analytics.schemas import Analytics
from src.auth import basic_auth
from src.db import get_async_session

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(basic_auth)],
)


@router.get("/")
async def get_analytics(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Analytics:
    analytics_service = AnalyticsService(session)

    analytics = Analytics(
        baseline=await analytics_service.get_baselines(),
        download_speed=await analytics_service.get_download_speed(),
        statuses=await analytics_service.get_health_statuses(),
        missing_bitrate=await analytics_service.get_missing_bitrate(),
        failures=await analytics_service.get_failure_breakdown(),
    )
    logger.info(analytics)

    return analytics
