import asyncio

from loguru import logger

from src.config import config
from src.db import get_session
from src.entities.probe.enums import ProbeFailureReason, ProbeStatus
from src.entities.probe.schemas import ProbeCreate
from src.entities.probe.services import ProbeService
from src.entities.video.schemas import VideoRead, VideoUpdate
from src.entities.video.services import VideoService
from src.exc import ProbeError
from src.link_generator.link_generator import video_link_generator
from src.video_probe.baseline_calculator import BaselineCalculator
from src.video_probe.schemas import VideoProbe
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


async def _record_failed_probe(
    probe_service: ProbeService,
    video: VideoRead,
    reason: ProbeFailureReason,
) -> None:
    """
    Persist a probe that produced no speed measurement.

    Failed probes used to be dropped entirely, which meant a storage
    defect left no trace beyond a log line. Storing them with a reason
    keeps the finding queryable after the video is excluded from
    further probing.

    Args:
        probe_service: Service used to persist the probe.
        video: Video the probe was run for.
        reason: Classified failure reason.
    """
    await probe_service.create(
        ProbeCreate(
            video_id=video.id,
            download_speed_mbps=None,
            status=ProbeStatus.FAILED,
            failure_reason=reason,
        )
    )


def _warn_no_bitrate(video: VideoRead, url: str, result: VideoProbe) -> None:
    """
    Shout about a probe that could not establish a bitrate.

    Without a bitrate the CRITICAL rule (speed below twice the bitrate)
    cannot run, so the probe silently degrades to baseline comparison
    only. That is easy to miss in a wall of INFO lines, hence the banner.

    Args:
        video: Video that was probed.
        url: Generated video URL.
        result: Probe result that came back without a bitrate.
    """
    logger.warning(
        "\n"
        "!!!=====================================================!!!\n"
        "!!!  NO BITRATE - CRITICAL CHECK SKIPPED FOR THIS PROBE  !!!\n"
        "!!!=====================================================!!!\n"
        f"  video_id={video.id} kvs_id={video.kvs_id} "
        f"storage_id={video.storage_id}\n"
        f"  format={video.video_format} "
        f"size_mb={result.size_mb} duration={result.duration_seconds}\n"
        f"  measured speed={result.download_speed_mbps} Mbps "
        f"from {result.downloaded_bytes} bytes\n"
        "  cause: ffprobe could not read the downloaded head of the file\n"
        "         (moov atom is most likely at the end of the container)\n"
        "         and no bitrate was stored by an earlier run\n"
        "  effect: probe is graded on the storage baseline alone\n"
        f"  url: {url}\n"
        "!!!=====================================================!!!"
    )


def _log_probe_failure(video: VideoRead, url: str, error: ProbeError) -> None:
    """
    Log a probe failure, naming whose problem it is.

    Args:
        video: Video the probe was run for.
        url: Generated video URL.
        error: Raised probe error carrying the classified reason.
    """
    reason = error.reason

    if reason is ProbeFailureReason.VIDEO_TOO_SMALL:
        hint = "video is too small to measure against, excluding it"
    elif reason is ProbeFailureReason.LINK_REJECTED:
        hint = (
            "link rejected at the edge - check that this server's IP is still "
            "in the KVS anti-hotlink whitelist"
        )
    elif reason is ProbeFailureReason.IP_BLOCKED:
        hint = "this server's IP is blocked by KVS anti-hotlink"
    elif reason is ProbeFailureReason.RATE_LIMITED:
        hint = "probing too often for this IP"
    elif reason is ProbeFailureReason.FILE_MISSING_ON_NODE:
        hint = "file is missing on the storage node it was redirected to"
    elif reason is ProbeFailureReason.FILE_MISSING_IN_CATALOG:
        hint = "KVS could not resolve the file at all"
    elif reason is ProbeFailureReason.ORIGIN_TLS_ERROR:
        hint = "Cloudflare could not validate the origin's SSL certificate"
    elif reason is ProbeFailureReason.ORIGIN_UNREACHABLE:
        hint = "Cloudflare could not reach the origin server"
    else:
        hint = "storage did not serve the file"

    logger.warning(
        f"Probe failed reason={reason.value} "
        f"storage_fault={reason.is_storage_fault} "
        f"video_id={video.id} kvs_id={video.kvs_id} "
        f"({hint}): {url}: {error}"
    )


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
                try:
                    result = await video_prober.probe(url)
                    logger.info(f"Successfully probed {url}")
                except ProbeError as e:
                    _log_probe_failure(video, url, e)
                    errors.append(url)
                    await _record_failed_probe(probe_service, video, e.reason)

                    if e.reason.makes_video_unusable:
                        await video_service.mark_video_with_error(video)
                    elif e.reason.is_storage_fault:
                        await video_service.register_storage_failure(video)
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
                        duration_seconds=result.duration_seconds
                        or video.duration_seconds,
                        bitrate_mbps=result.bitrate_mbps or video.bitrate_mbps,
                        size_mb=result.size_mb,
                    )
                    await video_service.update_video_metadata(video.id, video_data)
                warning_threshold = min(
                    download_speed_baseline / 2,
                    config.warning_speed_threshold_mbps,
                )
                # Metadata can be missing when the sample was unparsable, so
                # fall back to whatever a previous run stored for this video.
                bitrate_mbps = result.bitrate_mbps or video.bitrate_mbps

                if not bitrate_mbps:
                    _warn_no_bitrate(video, url, result)

                if bitrate_mbps and result.download_speed_mbps < bitrate_mbps * 2:
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
            finally:
                await asyncio.sleep(config.probe_delay_seconds)

        logger.info(f"Found {len(errors)} errors: {errors}")
