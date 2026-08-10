from src.celery_app import celery_app
from src.utils import run_async
from src.video_probe.coros import probe_video, run_video_probes


@celery_app.task(name="probe_video_task")
def probe_video_task(video_link: str) -> None:
    run_async(probe_video(video_link))


@celery_app.task(name="run_video_probes_task")
def run_video_probes_task() -> None:
    run_async(run_video_probes())
