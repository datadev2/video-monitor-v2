from fastapi import FastAPI

from prometheus_client import generate_latest
from starlette.responses import Response

from src.infrastructure.prometheus import metrics_service
from src.video_probe.router import router as probe_router
from src.link_generator.router import router as link_generator_router
from src.analytics.router import router as analytics_router


app = FastAPI(title="Accessibility Analysis API")

app.include_router(probe_router)
app.include_router(link_generator_router)
app.include_router(analytics_router)


@app.get("/metrics")
def metrics():
    metrics_service.update_metrics()
    return Response(
        generate_latest(),
        media_type="text/plain",
    )


@app.get("/health")
def healthcheck():
    return {"status": "OK"}
