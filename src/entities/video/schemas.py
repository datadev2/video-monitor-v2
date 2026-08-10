from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    storage_id: int
    kvs_id: int
    server_group_id: int
    video_format: str

    bitrate_mbps: float | None = None
    duration_seconds: float | None = None
    size_mb: float | None = None

    errors_count: int = 0
    last_error_date: datetime | None = None
    is_bad: bool = False


class VideoCreate(BaseModel):
    storage_id: int
    kvs_id: int
    server_group_id: int
    video_format: str


class VideoUpdate(BaseModel):
    bitrate_mbps: float | None = None
    duration_seconds: float | None = None
    size_mb: float | None = None

    errors_count: int = 0
    last_error_date: datetime | None = None
    is_bad: bool = False
