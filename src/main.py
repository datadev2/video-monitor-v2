from fastapi import FastAPI

from prometheus_client import make_asgi_app

from src.video_probe.router import router as probe_router
from src.link_generator.router import router as link_generator_router
from src.analytics.router import router as analytics_router


app = FastAPI(title="Video Monitor API")

app.include_router(probe_router)
app.include_router(link_generator_router)
app.include_router(analytics_router)

metrics_app = make_asgi_app()

app.mount("/metrics", metrics_app)


@app.get("/health")
def healthcheck():
    return {"status": "OK"}
