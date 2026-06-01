from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.analytics_service import AnalyticsService
from src.analytics.schemas import Analytics
from src.db import get_async_session

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/")
async def get_analytics(session: AsyncSession = Depends(get_async_session)):
    analytics_service = AnalyticsService(session)
    baselines = await analytics_service.get_baselines()
    logger.info(baselines)

    avg_download_speeds = await analytics_service.get_download_speed()
    logger.info(avg_download_speeds)

    health_statuses = await analytics_service.get_health_statuses()
    logger.info(health_statuses)
    return Analytics(
        baseline=baselines, download_speed=avg_download_speeds, statuses=health_statuses
    )
