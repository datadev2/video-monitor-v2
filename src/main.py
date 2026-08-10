from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from prometheus_client import generate_latest
from starlette.responses import Response

from src.analytics.coros import calculate_analytics_and_push_to_redis
from src.infrastructure.prometheus import update_metrics
from src.video_probe.router import router as probe_router
from src.link_generator.router import router as link_generator_router
from src.analytics.router import router as analytics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Publish analytics once on startup.

    The metrics endpoint only reads what analytics left in Redis, so an
    empty cache means an empty dashboard until Celery beat next fires -
    up to a full interval after every deploy. Everything published here
    is derived from Postgres and costs no requests to the storages, so
    it is safe to recompute unconditionally.

    A failure here must never keep the container from starting: the
    scheduled run will publish the same data later.
    """
    try:
        await calculate_analytics_and_push_to_redis()
        logger.info("Analytics warmed up on startup")
    except Exception as exc:
        logger.warning(f"Could not warm up analytics on startup: {exc}")

    yield


app = FastAPI(title="Accessibility Analysis API", lifespan=lifespan)

app.include_router(probe_router)
app.include_router(link_generator_router)
app.include_router(analytics_router)


@app.get("/metrics")
def metrics() -> Response:
    update_metrics()
    return Response(
        generate_latest(),
        media_type="text/plain",
    )


@app.get("/health")
def healthcheck():
    return {"status": "OK"}
