import asyncio
import json
import time
from typing import Final

import aiohttp

from src.config import config
from src.exc import VideoDownloadError, VideoMetadataError, VideoTooSmallError
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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    async def probe(self, url: str) -> VideoProbe:
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

    async def _fetch_metadata(self, url: str) -> VideoMetadata:
        """
        Uses ffprobe because media containers are messy
        and ffprobe is extremely battle-tested.
        """

        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise VideoMetadataError(f"ffprobe failed: {stderr.decode().strip()}")

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

    async def _measure_download_speed(
        self,
        url: str,
    ) -> DownloadResult:
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
