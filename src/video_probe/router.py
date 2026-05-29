from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from src.video_probe.dependencies import probe_dependencies
from src.video_probe.schemas import VideoProbe, VideoLink
from src.video_probe.tasks import probe_video_task, run_video_probes_task

router = APIRouter(
    prefix="/probe",
    tags=["probe"],
)


@router.post("/", response_model=VideoProbe, status_code=201)
async def probe(
    video_probe: Annotated[VideoProbe, Depends(probe_dependencies.probe_video)],
) -> VideoProbe:
    return video_probe


@router.post("/task")
async def probe_task(video_link: VideoLink) -> JSONResponse:
    task = probe_video_task.delay(video_link.url)
    return JSONResponse(content={"task": task.id}, status_code=201)


@router.post("/probe-videos")
async def video_probes() -> JSONResponse:
    task = run_video_probes_task.delay()
    return JSONResponse(content={"task": task.id}, status_code=201)
