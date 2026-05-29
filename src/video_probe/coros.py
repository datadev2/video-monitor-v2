from loguru import logger

from src.db import get_session
from src.entities.probe.enums import ProbeStatus
from src.entities.probe.schemas import ProbeCreate
from src.entities.probe.services import ProbeService
from src.entities.video.schemas import VideoUpdate
from src.entities.video.services import VideoService
from src.video_probe.baseline_calculator import BaselineCalculator
from src.video_probe.video_prober import video_prober


async def probe_video(video_link: str) -> None:
    probe = await video_prober.probe(video_link)
    logger.info(f"Probed {probe}")


async def run_video_probes() -> None:
    async with get_session() as session:
        video_service = VideoService(session)
        probe_service = ProbeService(session)
        baseline_calculator = BaselineCalculator(session)
        videos = await video_service.get_videos_for_probe()
        for video in videos:
            try:
                result = await video_prober.probe(video.url)
                logger.info(result)
            except Exception as e:
                logger.warning(f"Probed {video.url} failed: {e}")
                continue
            download_speed_baseline = await baseline_calculator.calculate_baseline(
                video.storage_id
            )
            logger.info(f"{video.storage_id=} {download_speed_baseline=}")
            if (
                (not video.size_mb)
                or (not video.bitrate_mbps)
                or (not video.duration_seconds)
            ):
                video_data = VideoUpdate(
                    duration_seconds=result.duration_seconds,
                    bitrate_mbps=result.bitrate_mbps,
                    size_mb=result.size_mb,
                )
                await video_service.update_video_metadata(video.id, video_data)
            if result.download_speed_mbps < result.bitrate_mbps * 2:
                status = ProbeStatus.CRITICAL
            elif result.download_speed_mbps <= download_speed_baseline / 2:
                status = ProbeStatus.WARNING
            else:
                status = ProbeStatus.HEALTHY
            probe = ProbeCreate(
                video_id=video.id,
                download_speed_mbps=result.download_speed_mbps,
                status=status,
            )
            await probe_service.create(probe)
