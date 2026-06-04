import asyncio
import json
import time
from typing import Final

import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import config
from src.exc import (
    VideoDownloadError,
    VideoMetadataError,
    VideoTooSmallError,
    RetryableVideoMetadataError,
    RetryableVideoDownloadError,
)
from src.video_probe.schemas import DownloadResult, VideoMetadata, VideoProbe


class VideoProber:
    """
    Core primitive for video CDN probing.

    Responsibilities:
    - fetch video metadata via ffprobe
    - reject tiny videos
    - partially download video
    - measure effective throughput
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
            VideoTooSmallError: If the video size is below the configured threshold.
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

        return VideoProbe(  # type: ignore
            url=url,
            size_mb=round(size_mb, 2),
            duration_seconds=metadata.duration_seconds,  # type: ignore
            bitrate_mbps=metadata.bitrate_mbps,
            download_speed_mbps=download_result.download_speed_mbps,
            downloaded_bytes=download_result.downloaded_bytes,
            download_duration_seconds=download_result.duration_seconds,
        )

    @retry(
        retry=retry_if_exception_type(RetryableVideoMetadataError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
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
            RetryableVideoMetadataError: For temporary network-related failures.
            VideoMetadataError: For unrecoverable metadata extraction errors.
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
            if (
                "Connection to tcp://" in stderr_text
                or "timed out" in stderr_text.lower()
                or "temporarily unavailable" in stderr_text.lower()
                or "but not one of 40{0,1,3,4}" in stderr_text.lower()
                or "cannot connect to hos" in stderr_text.lower()
            ):
                raise RetryableVideoMetadataError(stderr_text)

            raise VideoMetadataError(stderr_text)

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

    @retry(
        retry=retry_if_exception_type(RetryableVideoDownloadError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _measure_download_speed(
        self,
        url: str,
    ) -> DownloadResult:
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
            RetryableVideoDownloadError: For temporary download failures.
            VideoDownloadError: For unrecoverable download errors.
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

        except Exception as exc:
            if "410" in str(exc):
                raise RetryableVideoDownloadError(str(exc))
            raise VideoDownloadError(str(exc)) from exc

        elapsed = time.monotonic() - started_at

        if elapsed <= 0:
            raise VideoDownloadError("Invalid elapsed time")

        speed_mbps = (downloaded * 8) / elapsed / 1024 / 1024

        return DownloadResult(
            download_speed_mbps=round(speed_mbps, 2),
            downloaded_bytes=downloaded,
            duration_seconds=round(elapsed, 2),
        )


video_prober = VideoProber()
