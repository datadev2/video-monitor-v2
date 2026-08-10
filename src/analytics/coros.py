from loguru import logger

from src.analytics.analytics_service import AnalyticsService
from src.db import get_session
from src.infrastructure.redis_client import redis_cli


async def calculate_analytics_and_push_to_redis():
    async with get_session() as session:
        analytics_service = AnalyticsService(session)

        baselines = await analytics_service.get_baselines()
        avg_download_speeds = await analytics_service.get_download_speed()
        health_statuses = await analytics_service.get_health_statuses()
        missing_bitrate = await analytics_service.get_missing_bitrate()
        failures = await analytics_service.get_failure_breakdown()

        logger.info(
            f"{baselines=}, {avg_download_speeds=}, {health_statuses=}, "
            f"{missing_bitrate=}, {failures=}"
        )
        redis_cli.push("baselines", [b.model_dump() for b in baselines])
        redis_cli.push(
            "avg_download_speeds", [a.model_dump() for a in avg_download_speeds]
        )
        redis_cli.push("health_statuses", [s.model_dump() for s in health_statuses])
        redis_cli.push("missing_bitrate", [m.model_dump() for m in missing_bitrate])
        redis_cli.push("probe_failures", [f.model_dump() for f in failures])
