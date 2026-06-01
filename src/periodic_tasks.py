from loguru import logger

from src.analytics.analytics_service import AnalyticsService
from src.celery_app import celery_app
from src.db import get_session
from src.infrastructure.redis_client import redis_cli
from src.utils import event_loop


async def calculate_analytics_and_push_to_redis():
    async with get_session() as session:
        analytics_service = AnalyticsService(session)

        baselines = await analytics_service.get_baselines()
        avg_download_speeds = await analytics_service.get_download_speed()
        health_statuses = await analytics_service.get_health_statuses()

        logger.info(f"{baselines=}, {avg_download_speeds=}, {health_statuses=}")
        redis_cli.push("baselines", [b.model_dump() for b in baselines])
        redis_cli.push(
            "avg_download_speeds", [a.model_dump() for a in avg_download_speeds]
        )
        redis_cli.push("health_statuses", [s.model_dump() for s in health_statuses])


@celery_app.task(name="calculate_analytics_and_push_to_redis_task")
def calculate_analytics_and_push_to_redis_task():
    loop = event_loop()
    loop.run_until_complete(calculate_analytics_and_push_to_redis())
