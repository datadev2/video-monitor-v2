from loguru import logger

from src.config import config
from src.db import get_session
from src.entities.probe.enums import ProbeStatus
from src.entities.probe.schemas import ProbeCreate
from src.entities.probe.services import ProbeService
from src.entities.video.schemas import VideoUpdate
from src.entities.video.services import VideoService
from src.exc import (
    VideoDownloadError,
    VideoMetadataError,
    VideoTooSmallError,
    RetryableVideoMetadataError,
)
from src.link_generator.link_generator import video_link_generator
from src.video_probe.baseline_calculator import BaselineCalculator
from src.video_probe.video_prober import video_prober


async def probe_video(video_link: str) -> None:
    """
    Probe a single video URL and log the result.

    This helper is primarily intended for manual testing
    and debugging of the video probing pipeline.

    Args:
        video_link: Video URL to probe.
    """
    probe = await video_prober.probe(video_link)
    logger.info(f"Probed {probe}")


async def run_video_probes() -> None:
    """
    Execute the scheduled video monitoring workflow.

    The workflow performs the following steps:

    - retrieves videos eligible for probing;
    - generates protected KVS download URLs;
    - probes video availability and download performance;
    - updates missing video metadata;
    - calculates storage-specific performance baselines;
    - evaluates probe health status;
    - persists probe results;
    - tracks videos with repeated probe failures.

    Videos that fail probing three times are automatically
    marked as bad and excluded from future probe runs.
    """
    async with get_session() as session:
        video_service = VideoService(session)
        probe_service = ProbeService(session)
        baseline_calculator = BaselineCalculator(session)
        videos = await video_service.get_videos_for_probe()
        errors = []
        for video in videos:
            url = video_link_generator.generate_kvs_link(
                server_group_id=video.server_group_id,
                video_id=video.kvs_id,
                video_format=video.video_format,
            )

            try:
                result = await video_prober.probe(url)
                logger.info(result)
            except (
                VideoMetadataError,
                VideoTooSmallError,
                VideoDownloadError,
            ) as e:
                logger.warning(f"Probed {url} failed: {e}")
                errors.append(url)
                await video_service.mark_video_with_error(video)
                continue

            except RetryableVideoMetadataError as e:
                logger.warning(f"Probed {url} failed: {e}")
                errors.append(url)
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
            warning_threshold = min(
                download_speed_baseline / 2,
                config.warning_speed_threshold_mbps,
            )
            if result.download_speed_mbps < result.bitrate_mbps * 2:
                status = ProbeStatus.CRITICAL
            elif result.download_speed_mbps <= warning_threshold:
                status = ProbeStatus.WARNING
            else:
                status = ProbeStatus.HEALTHY
            probe = ProbeCreate(
                video_id=video.id,
                download_speed_mbps=result.download_speed_mbps,
                status=status,
            )
            await probe_service.create(probe)

        logger.info(f"Found {len(errors)} errors: {errors}")
