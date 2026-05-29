from src.celery_app import celery_app
from src.utils import event_loop
from src.video_probe.coros import probe_video, run_video_probes


@celery_app.task(name="probe_video_task")
def probe_video_task(video_link: str) -> None:
    loop = event_loop()
    loop.run_until_complete(probe_video(video_link))


@celery_app.task(name="run_video_probes_task")
def run_video_probes_task() -> None:
    loop = event_loop()
    loop.run_until_complete(run_video_probes())
