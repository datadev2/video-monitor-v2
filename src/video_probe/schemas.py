from datetime import datetime, timezone

from pydantic import BaseModel


class VideoLink(BaseModel):
    url: str


class VideoProbe(BaseModel):
    url: str

    size_mb: float
    bitrate_mbps: float
    duration_seconds: float

    download_speed_mbps: float

    downloaded_bytes: int
    download_duration_seconds: float

    created_at: datetime = datetime.now(timezone.utc)


class VideoMetadata(BaseModel):
    bitrate_mbps: float
    size_bytes: int
    duration_seconds: float | None = None


class DownloadResult(BaseModel):
    download_speed_mbps: float
    downloaded_bytes: int
    duration_seconds: float
