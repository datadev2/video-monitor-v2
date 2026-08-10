from datetime import UTC, datetime

from pydantic import BaseModel, Field


class VideoLink(BaseModel):
    url: str


class VideoProbe(BaseModel):
    url: str

    size_mb: float
    bitrate_mbps: float | None = None
    duration_seconds: float | None = None

    download_speed_mbps: float

    downloaded_bytes: int
    download_duration_seconds: float

    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class VideoMetadata(BaseModel):
    bitrate_mbps: float
    size_bytes: int
    duration_seconds: float | None = None


class DownloadResult(BaseModel):
    download_speed_mbps: float
    downloaded_bytes: int
    duration_seconds: float
