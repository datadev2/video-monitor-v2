from src.analytics.coros import calculate_analytics_and_push_to_redis
from src.celery_app import celery_app
from src.utils import run_async
from src.video_probe.coros import run_video_probes


async def _run_monitoring_and_analytics() -> None:
    """
    Probe every eligible video, then publish analytics over the results.

    Both steps share one event loop and one connection pool: analytics
    reads what the probe run just wrote, so splitting them across loops
    would only add a pool teardown between two halves of the same job.
    """
    await run_video_probes()
    await calculate_analytics_and_push_to_redis()


@celery_app.task(name="run_monitoring_and_calculate_analytics_task")
def run_monitoring_and_calculate_analytics_task() -> None:
    run_async(_run_monitoring_and_analytics())
