from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel


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

    created_at: datetime = datetime.now(timezone.utc)


class VideoMetadata(BaseModel):
    bitrate_mbps: float | None = None
    duration_seconds: float | None = None


@dataclass
class VideoSample:
    """
    The downloaded head of a video plus the transfer statistics.

    A plain dataclass rather than a pydantic model: `data` holds tens of
    megabytes and there is nothing here worth validating.
    """

    data: bytes
    total_size_bytes: int
    downloaded_bytes: int
    download_speed_mbps: float
    duration_seconds: float
