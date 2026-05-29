from fastapi import FastAPI

from src.video_probe.router import router as probe_router


app = FastAPI(title="Video Monitor API")

app.include_router(probe_router)


@app.get("/health")
def healthcheck():
    return {"status": "OK"}
