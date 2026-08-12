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


_FAILURE_HINTS: dict[ProbeFailureReason, str] = {
    ProbeFailureReason.VIDEO_TOO_SMALL: (
        "video is too small to measure against, excluding it"
    ),
    ProbeFailureReason.LINK_REJECTED: (
        "link rejected at the edge - check that this server's IP is still "
        "in the KVS anti-hotlink whitelist"
    ),
    ProbeFailureReason.IP_BLOCKED: "this server's IP is blocked by KVS anti-hotlink",
    ProbeFailureReason.RATE_LIMITED: "probing too often for this IP",
    ProbeFailureReason.FILE_MISSING_ON_NODE: (
        "file is missing on the storage node it was redirected to"
    ),
    ProbeFailureReason.FILE_MISSING_IN_CATALOG: "KVS could not resolve the file at all",
    ProbeFailureReason.ORIGIN_TLS_ERROR: (
        "Cloudflare could not validate the origin's SSL certificate"
    ),
    ProbeFailureReason.ORIGIN_UNREACHABLE: "Cloudflare could not reach the origin server",
}

_DEFAULT_FAILURE_HINT = "storage did not serve the file"


def _log_probe_failure(video: VideoRead, url: str, error: ProbeError) -> None:
    """
    Log a probe failure, naming whose problem it is.

    Args:
        video: Video the probe was run for.
        url: Generated video URL.
        error: Raised probe error carrying the classified reason.
    """
    reason = error.reason
    hint = _FAILURE_HINTS.get(reason, _DEFAULT_FAILURE_HINT)

    logger.warning(
        f"Probe failed reason={reason.value} "
        f"storage_fault={reason.is_storage_fault} "
        f"video_id={video.id} kvs_id={video.kvs_id} "
        f"({hint}): {url}: {error}"
    )


def _grade_probe(
    result: VideoProbe,
    bitrate_mbps: float | None,
    baseline_mbps: float,
) -> ProbeStatus:
    """
    Grade a measured download speed.

    Two independent things make a probe CRITICAL.

    The first is the node itself being too slow to be usable at all,
    below `min_baseline_speed_mbps`. This check ignores the bitrate on
    purpose. What is measured is the node's throughput, and a node
    serves whatever happens to sit on it: bitrates are mixed across the
    same node, so wherever there is a 480p file there is a 1440p file
    too. A node dribbling out a small low-bitrate video - one that would
    have arrived instantly under any healthy condition - will dribble
    out a large one at exactly the same rate. Grading that as acceptable
    because the file it was asked for happened to be small would hide a
    node that is failing every other file on it.

    The second is the speed being below twice the video's own bitrate,
    which cannot sustain playback however well the storage normally
    performs. This one needs a bitrate, and falls away without it.

    Args:
        result: Successful probe result.
        bitrate_mbps: Video bitrate, or None if it was never established.
        baseline_mbps: Baseline download speed for the storage.

    Returns:
        ProbeStatus: Health status for this probe.
    """
    warning_threshold = min(
        baseline_mbps / 2,
        config.warning_speed_threshold_mbps,
    )

    # Deliberately independent of the bitrate - see the docstring. The
    # setting does double duty as the floor under a computed baseline
    # and as the line below which a node is unusable, so tuning it moves
    # both; that is intended, they are the same judgement.
    #
    # It also backstops the bitrate rule below, which is skipped when the
    # bitrate is unknown. That is rare - pointing ffprobe at the URL
    # normally yields one - but when it happens the rule is the only
    # other route to CRITICAL.
    if result.download_speed_mbps < config.min_baseline_speed_mbps:
        return ProbeStatus.CRITICAL

    if bitrate_mbps and result.download_speed_mbps < bitrate_mbps * 2:
        return ProbeStatus.CRITICAL

    if result.download_speed_mbps <= warning_threshold:
        return ProbeStatus.WARNING

    return ProbeStatus.HEALTHY


async def _handle_probe_failure(
    video: VideoRead,
    url: str,
    error: ProbeError,
    video_service: VideoService,
    probe_service: ProbeService,
) -> None:
    """
    Record a failed probe and apply its verdict to the video.

    Args:
        video: Video the probe was run for.
        url: Generated video URL.
        error: Raised probe error carrying the classified reason.
        video_service: Service used to update the video.
        probe_service: Service used to persist the probe.
    """
    _log_probe_failure(video, url, error)
    await _record_failed_probe(probe_service, video, error.reason)

    if error.reason.makes_video_unusable:
        await video_service.mark_video_with_error(video)
    elif error.reason.is_storage_fault:
        await video_service.register_storage_failure(video)


async def _probe_one_video(
    video: VideoRead,
    url: str,
    video_service: VideoService,
    probe_service: ProbeService,
    baseline_calculator: BaselineCalculator,
) -> bool:
    """
    Probe a single video and persist the outcome.

    Args:
        video: Video to probe.
        url: Generated video URL.
        video_service: Service used to update the video.
        probe_service: Service used to persist the probe.
        baseline_calculator: Calculator for the storage baseline.

    Returns:
        bool: True if the probe yielded a speed measurement.
    """
    try:
        result = await video_prober.probe(url)
    except ProbeError as e:
        await _handle_probe_failure(video, url, e, video_service, probe_service)
        return False

    logger.info(f"Successfully probed {url}")

    baseline_mbps = await baseline_calculator.calculate_baseline(video.storage_id)
    logger.info(f"{video.storage_id=} {baseline_mbps=}")

    if not (video.size_mb and video.bitrate_mbps and video.duration_seconds):
        await video_service.update_video_metadata(
            video.id,
            VideoUpdate(
                duration_seconds=result.duration_seconds or video.duration_seconds,
                bitrate_mbps=result.bitrate_mbps or video.bitrate_mbps,
                size_mb=result.size_mb,
            ),
        )

    # Metadata can be missing when the sample was unparsable, so
    # fall back to whatever a previous run stored for this video.
    bitrate_mbps = result.bitrate_mbps or video.bitrate_mbps

    if not bitrate_mbps:
        _warn_no_bitrate(video, url, result)

    await probe_service.create(
        ProbeCreate(
            video_id=video.id,
            download_speed_mbps=result.download_speed_mbps,
            status=_grade_probe(result, bitrate_mbps, baseline_mbps),
        )
    )
    return True


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

    Every video is followed by a fixed delay, successful or not, so a
    run paces itself against the storages instead of bursting.
    """
    async with get_session() as session:
        video_service = VideoService(session)
        probe_service = ProbeService(session)
        baseline_calculator = BaselineCalculator(session)

        videos = await video_service.get_videos_for_probe()
        errors: list[str] = []

        for video in videos:
            url = video_link_generator.generate_kvs_link(
                server_group_id=video.server_group_id,
                video_id=video.kvs_id,
                video_format=video.video_format,
            )

            try:
                succeeded = await _probe_one_video(
                    video,
                    url,
                    video_service,
                    probe_service,
                    baseline_calculator,
                )
                if not succeeded:
                    errors.append(url)
            finally:
                await asyncio.sleep(config.probe_delay_seconds)

        logger.info(f"Found {len(errors)} errors: {errors}")
