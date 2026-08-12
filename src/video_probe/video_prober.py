import asyncio
import json
import time
from typing import Final

import aiohttp
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import config
from src.entities.probe.enums import ProbeFailureReason
from src.exc import (
    RetryableProbeError,
    VideoDownloadError,
    VideoMetadataError,
    VideoTooSmallError,
)
from src.video_probe.schemas import DownloadResult, VideoMetadata, VideoProbe


def describe_exception(exc: BaseException) -> str:
    """
    Render an exception so the log never shows an empty message.

    Several of the failures worth reporting carry no message at all -
    `str(TimeoutError())` is the empty string, and so are
    ClientPayloadError, ClientOSError and ConnectionResetError. Logging
    the bare text turns the most interesting failures into a line that
    ends in a colon and tells nobody anything.

    Args:
        exc: Exception to describe.

    Returns:
        str: The exception type, plus its message when it has one.
    """
    message = str(exc).strip()

    if message:
        return f"{type(exc).__name__}: {message}"

    return type(exc).__name__


class VideoProber:
    """
    Core primitive for video CDN probing.

    Responsibilities:
    - fetch video metadata via ffprobe
    - reject tiny videos
    - partially download video
    - measure effective throughput

    Metadata is read by pointing ffprobe at the URL rather than at an
    already-downloaded sample. ffprobe issues range requests and can seek
    to the end of the container, which is what makes metadata readable
    for files whose moov atom sits at the tail. Reading a downloaded head
    instead would save a request per probe, but left one video in two or
    three without a bitrate.
    """

    MIN_SIZE_MB: Final[int] = config.video_min_size_mb
    DOWNLOAD_SIZE_MB: Final[int] = config.videos_download_size_mb

    def __init__(
        self,
        timeout_seconds: int = 120,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) "
            "Gecko/20100101 Firefox/139.0"
        ),
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    async def probe(self, url: str) -> VideoProbe:
        """
        Probe a video URL and collect performance metrics.

        The probing process consists of:
        - fetching video metadata via ffprobe;
        - validating the video size;
        - downloading a portion of the file;
        - measuring effective download speed.

        Args:
            url: Video URL to probe.

        Returns:
            VideoProbe: Collected metadata and download statistics.

        Raises:
            VideoTooSmallError: If the video size is below the configured
                threshold. Raised before the download starts.
            VideoMetadataError: If metadata extraction fails.
            VideoDownloadError: If download speed measurement fails.
        """
        metadata = await self._fetch_metadata(url)

        size_mb = metadata.size_bytes / 1024 / 1024

        if size_mb < self.MIN_SIZE_MB:
            raise VideoTooSmallError(
                f"Video too small: {size_mb:.2f} MB "
                f"(minimum: {self.MIN_SIZE_MB} MB)"
            )

        download_result = await self._measure_download_speed(url)

        return VideoProbe(
            url=url,
            size_mb=round(size_mb, 2),
            duration_seconds=metadata.duration_seconds,
            bitrate_mbps=metadata.bitrate_mbps,
            download_speed_mbps=download_result.download_speed_mbps,
            downloaded_bytes=download_result.downloaded_bytes,
            download_duration_seconds=download_result.duration_seconds,
        )

    @retry(
        retry=retry_if_exception_type(RetryableProbeError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=1, max=30),
        reraise=True,
    )
    async def _fetch_metadata(self, url: str) -> VideoMetadata:
        """
        Retrieve video metadata using ffprobe.

        Extracts file size, duration and bitrate from the remote media file.

        Args:
            url: Video URL.

        Returns:
            VideoMetadata: Parsed video metadata.

        Raises:
            RetryableProbeError: If nothing answered at all.
            VideoMetadataError: For any answered but failed request.
        """
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-user_agent",
            self._user_agent,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        stderr_text = stderr.decode(errors="replace")

        if process.returncode != 0:
            status, reason, headers = await self._probe_http_status(url)
            failure_reason = self._classify_failure(status, headers)
            logger.warning(
                f"ffprobe failed for {url}: "
                f"exit_code={process.returncode} "
                f"http_status={status} reason={reason!r} "
                f"failure_reason={failure_reason.value} "
                f"headers={headers} "
                f"stderr={stderr_text.strip()!r}"
            )

            # ffprobe can die without writing anything to stderr - killed
            # by a signal, or simply giving up quietly. Carry the exit
            # code instead so the raised error is never blank.
            detail = (
                stderr_text.strip() or f"ffprobe exited {process.returncode}, no stderr"
            )

            # Retry only when nothing answered at all. Any HTTP status is a
            # definite verdict - a 404 will stay a 404, a 5xx means the
            # storage is already struggling, and a 410 means our IP is
            # blocked, where retrying deepens the anti-hotlink ban.
            if status is None:
                raise RetryableProbeError(
                    f"{detail} (probe request: {reason})",
                    reason=ProbeFailureReason.STORAGE_UNREACHABLE,
                    status_code=status,
                )

            raise VideoMetadataError(
                detail,
                reason=failure_reason,
                status_code=status,
            )

        try:
            payload = json.loads(stdout.decode())
        except json.JSONDecodeError as exc:
            raise VideoMetadataError("Invalid ffprobe JSON output") from exc

        format_data = payload.get("format", {})

        bit_rate_raw = format_data.get("bit_rate")
        size_raw = format_data.get("size")
        duration_raw = format_data.get("duration")

        if not bit_rate_raw:
            raise VideoMetadataError("Missing bitrate")

        if not size_raw:
            raise VideoMetadataError("Missing size")

        bitrate_bps = int(bit_rate_raw)
        size_bytes = int(size_raw)

        duration_seconds = float(duration_raw) if duration_raw is not None else None

        bitrate_mbps = bitrate_bps / 1024 / 1024

        return VideoMetadata(
            bitrate_mbps=round(bitrate_mbps, 2),
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
        )

    async def _probe_http_status(
        self, url: str
    ) -> tuple[int | None, str, dict[str, str]]:
        """
        Issue a lightweight request to capture the real HTTP status code.

        ffprobe's own error output doesn't reveal the actual status code
        for unhandled 4xx responses (e.g. rate limiting), so this makes
        a minimal follow-up request. The status it returns drives both
        the failure classification and the retry decision.

        Args:
            url: Video URL.

        Returns:
            tuple[int | None, str, dict[str, str]]: HTTP status code
                (or None if the request itself failed), the reason/error
                text, and the response headers (empty if unavailable).
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": self._user_agent},
            ) as session:
                async with session.get(url, headers={"Range": "bytes=0-0"}) as response:
                    return (
                        response.status,
                        response.reason or "",
                        dict(response.headers),
                    )
        except Exception as exc:
            return None, describe_exception(exc), {}

    async def _measure_download_speed(self, url: str) -> DownloadResult:
        """
        Measure effective video download throughput.

        Downloads up to the configured number of megabytes and calculates
        the average transfer speed based on the amount of data received
        and the elapsed time.

        Args:
            url: Video URL.

        Returns:
            DownloadResult: Download statistics including throughput,
                transferred bytes and elapsed time.

        Raises:
            VideoDownloadError: If the download fails. Download failures are
                never retried: an HTTP status is a definite verdict, and a
                410 means our IP is banned by anti-hotlink, where each extra
                request only extends the ban.
        """
        max_bytes = self.DOWNLOAD_SIZE_MB * 1024 * 1024

        timeout = aiohttp.ClientTimeout(
            total=self._timeout_seconds,
        )

        headers = {
            "User-Agent": self._user_agent,
        }

        downloaded = 0

        started_at = time.monotonic()

        try:
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session:
                async with session.get(url) as response:
                    response.raise_for_status()

                    async for chunk in response.content.iter_chunked(1024 * 256):
                        downloaded += len(chunk)

                        if downloaded >= max_bytes:
                            break

        except aiohttp.ClientResponseError as exc:
            response_headers = dict(exc.headers) if exc.headers else {}
            failure_reason = self._classify_failure(exc.status, response_headers)
            logger.warning(
                f"Download failed for {url}: "
                f"http_status={exc.status} message={exc.message!r} "
                f"failure_reason={failure_reason.value} "
                f"headers={response_headers}"
            )
            raise VideoDownloadError(
                str(exc),
                reason=failure_reason,
                status_code=exc.status,
            ) from exc

        except Exception as exc:
            # Nothing here carries an HTTP status, and most of these
            # exceptions stringify to nothing at all - a bare
            # TimeoutError, ClientPayloadError or ConnectionResetError
            # all render as "". Log the type, and how far the transfer
            # got before it died: stalling at 30 MB of 32 is a slow
            # node, dying at 0 is a connection that never delivered.
            elapsed = time.monotonic() - started_at
            logger.warning(
                f"Download failed for {url}: "
                f"error={describe_exception(exc)} "
                f"downloaded_bytes={downloaded} "
                f"of_expected={max_bytes} "
                f"elapsed_seconds={elapsed:.1f} "
                f"timeout_seconds={self._timeout_seconds}"
            )
            raise VideoDownloadError(
                describe_exception(exc),
                reason=ProbeFailureReason.STORAGE_UNREACHABLE,
            ) from exc

        elapsed = time.monotonic() - started_at

        if elapsed <= 0:
            raise VideoDownloadError("Invalid elapsed time")

        speed_mbps = (downloaded * 8) / elapsed / 1024 / 1024

        return DownloadResult(
            download_speed_mbps=round(speed_mbps, 2),
            downloaded_bytes=downloaded,
            duration_seconds=round(elapsed, 2),
        )

    @staticmethod
    def _served_by_storage_node(headers: dict[str, str]) -> bool:
        """
        Determine whether the response came from a storage node.

        A request that KVS resolved is redirected straight to the
        storage node, bypassing Cloudflare, so its response carries
        no CF headers. A response that still carries them was produced
        by the main domain, i.e. KVS never got as far as a node.

        Args:
            headers: Response headers.

        Returns:
            bool: True if a storage node produced the response.
        """
        normalized = {key.lower(): value for key, value in headers.items()}

        return "cf-ray" not in normalized and "cloudflare" not in normalized.get(
            "server", ""
        )

    @classmethod
    def _classify_failure(
        cls,
        status: int | None,
        headers: dict[str, str] | None = None,
    ) -> ProbeFailureReason:
        """
        Map an HTTP status onto a failure reason.

        The two flavours of 404 are kept apart deliberately: a node 404
        means the file vanished from the disk it was supposed to be on,
        while a catalog 404 means KVS could not resolve it at all. They
        point the admin at different places.

        Args:
            status: HTTP status code, or None if the request itself failed.
            headers: Response headers, used to tell the responder apart.

        Returns:
            ProbeFailureReason: Classified reason.
        """
        if status is None:
            return ProbeFailureReason.STORAGE_UNREACHABLE

        if status == 404:
            if headers and cls._served_by_storage_node(headers):
                return ProbeFailureReason.FILE_MISSING_ON_NODE
            return ProbeFailureReason.FILE_MISSING_IN_CATALOG

        if status == 403:
            return ProbeFailureReason.LINK_REJECTED

        if status == 410:
            return ProbeFailureReason.IP_BLOCKED

        if status == 429:
            return ProbeFailureReason.RATE_LIMITED

        # 520-527 are Cloudflare's own codes for a broken edge-to-origin hop:
        # the request never reached KVS, so they point at the origin server
        # rather than at anything the application did.
        if status in (525, 526):
            return ProbeFailureReason.ORIGIN_TLS_ERROR

        if 520 <= status <= 527:
            return ProbeFailureReason.ORIGIN_UNREACHABLE

        if status >= 500:
            return ProbeFailureReason.STORAGE_ERROR

        return ProbeFailureReason.UNKNOWN


video_prober = VideoProber()
