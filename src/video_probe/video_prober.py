import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

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
from src.video_probe.schemas import VideoMetadata, VideoProbe, VideoSample


class VideoProber:
    """
    Core primitive for video CDN probing.

    Responsibilities:
    - download the head of a video exactly once
    - measure effective throughput
    - reject tiny videos
    - read metadata out of the downloaded sample via ffprobe

    Every probe costs a single request to the storage. Metadata used to be
    fetched by pointing ffprobe at the URL, which doubled the traffic and
    made each probe count twice against the KVS anti-hotlink limiter.
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
        - downloading the head of the file, measuring throughput;
        - validating the full file size reported by the server;
        - reading metadata out of the downloaded sample.

        Args:
            url: Video URL to probe.

        Returns:
            VideoProbe: Collected metadata and download statistics.

        Raises:
            VideoTooSmallError: If the video size is below the configured
                threshold. Raised before any payload is transferred.
            VideoMetadataError: If the server does not report a file size.
            VideoDownloadError: If the download fails.
        """
        sample = await self._download_sample(url)

        size_mb = sample.total_size_bytes / 1024 / 1024
        metadata = await self._extract_metadata(sample, url)

        return VideoProbe(
            url=url,
            size_mb=round(size_mb, 2),
            duration_seconds=metadata.duration_seconds,
            bitrate_mbps=metadata.bitrate_mbps,
            download_speed_mbps=sample.download_speed_mbps,
            downloaded_bytes=sample.downloaded_bytes,
            download_duration_seconds=sample.duration_seconds,
        )

    @retry(
        retry=retry_if_exception_type(RetryableProbeError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=1, max=30),
        reraise=True,
    )
    async def _download_sample(self, url: str) -> VideoSample:
        """
        Download the head of the video and measure throughput.

        The full file size comes from `Content-Length` on this same
        response, so no separate request is needed to learn it. Videos
        below the size threshold are rejected as soon as the headers
        arrive, before any payload is transferred.

        Args:
            url: Video URL.

        Returns:
            VideoSample: Downloaded bytes and transfer statistics.

        Raises:
            VideoTooSmallError: If the file is below the size threshold.
            VideoMetadataError: If the server reports no file size.
            RetryableProbeError: If nothing answered at all.
            VideoDownloadError: For any answered but failed download.
        """
        max_bytes = self.DOWNLOAD_SIZE_MB * 1024 * 1024
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        headers = {"User-Agent": self._user_agent}

        chunks: list[bytes] = []
        downloaded = 0

        started_at = time.monotonic()

        try:
            async with aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session:
                async with session.get(url) as response:
                    response.raise_for_status()

                    total_size_bytes = response.content_length

                    if total_size_bytes is None:
                        raise VideoMetadataError(
                            "Server reported no Content-Length",
                            reason=ProbeFailureReason.INVALID_METADATA,
                            status_code=response.status,
                        )

                    self._reject_if_too_small(total_size_bytes)

                    async for chunk in response.content.iter_chunked(1024 * 256):
                        chunks.append(chunk)
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

        except (VideoTooSmallError, VideoMetadataError):
            raise

        except Exception as exc:
            # Nothing answered - no status, no headers. This is the only
            # case worth retrying: any HTTP status is a definite verdict,
            # and a 410 in particular means our IP is banned, where extra
            # requests only extend the ban.
            logger.warning(f"Download failed for {url}: {exc}")
            raise RetryableProbeError(
                str(exc),
                reason=ProbeFailureReason.STORAGE_UNREACHABLE,
            ) from exc

        elapsed = time.monotonic() - started_at

        if elapsed <= 0:
            raise VideoDownloadError("Invalid elapsed time")

        speed_mbps = (downloaded * 8) / elapsed / 1024 / 1024

        return VideoSample(
            data=b"".join(chunks),
            total_size_bytes=total_size_bytes,
            downloaded_bytes=downloaded,
            download_speed_mbps=round(speed_mbps, 2),
            duration_seconds=round(elapsed, 2),
        )

    def _reject_if_too_small(self, total_size_bytes: int) -> None:
        """
        Reject a file that is too small to measure a speed against.

        Args:
            total_size_bytes: Full file size reported by the server.

        Raises:
            VideoTooSmallError: If the file is below the threshold.
        """
        size_mb = total_size_bytes / 1024 / 1024

        if size_mb < self.MIN_SIZE_MB:
            raise VideoTooSmallError(
                f"Video too small: {size_mb:.2f} MB "
                f"(minimum: {self.MIN_SIZE_MB} MB)"
            )

    async def _extract_metadata(self, sample: VideoSample, url: str) -> VideoMetadata:
        """
        Read metadata out of the downloaded sample.

        ffprobe is pointed at a temporary file holding the sample rather
        than at the URL, so this costs no extra request. The sample is
        only the head of the file, which is enough for any video with its
        moov atom at the front - the layout used for streaming. If it is
        not, metadata is simply unavailable and the probe still reports
        the download speed it measured, which is what the service is for.

        Bitrate is derived from the full size and duration rather than
        taken from ffprobe, whose own value describes the truncated
        sample and would understate long videos.

        Args:
            sample: Downloaded sample.
            url: Video URL, used only to pick a file suffix.

        Returns:
            VideoMetadata: Parsed metadata, with empty fields if the
                sample could not be parsed.
        """
        suffix = Path(urlparse(url).path.rstrip("/")).suffix or ".mp4"

        handle, path = tempfile.mkstemp(suffix=suffix)
        os.close(handle)

        try:
            await asyncio.to_thread(Path(path).write_bytes, sample.data)
            payload = await self._run_ffprobe(path)
        finally:
            await asyncio.to_thread(Path(path).unlink, True)

        if payload is None:
            logger.warning(
                f"NO METADATA: ffprobe could not parse the first "
                f"{sample.downloaded_bytes} bytes of {url} - the moov atom is "
                f"most likely at the end of the container, so neither duration "
                f"nor bitrate can be derived from the sample"
            )
            return VideoMetadata()

        format_data = payload.get("format", {})
        duration_raw = format_data.get("duration")

        duration_seconds = float(duration_raw) if duration_raw is not None else None
        bitrate_mbps = None

        if duration_seconds:
            bitrate_bps = sample.total_size_bytes * 8 / duration_seconds
            bitrate_mbps = round(bitrate_bps / 1024 / 1024, 2)

        return VideoMetadata(
            bitrate_mbps=bitrate_mbps,
            duration_seconds=duration_seconds,
        )

    @staticmethod
    async def _run_ffprobe(path: str) -> dict | None:
        """
        Run ffprobe against a local file.

        Args:
            path: Path to the file to inspect.

        Returns:
            dict | None: Parsed ffprobe output, or None if it failed.
        """
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.debug(f"ffprobe failed: {stderr.decode(errors='replace').strip()!r}")
            return None

        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError:
            logger.debug("ffprobe returned invalid JSON")
            return None

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
