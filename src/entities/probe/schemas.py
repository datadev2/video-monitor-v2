from datetime import datetime, timezone

from pydantic import Field, BaseModel

from src.entities.probe.enums import ProbeFailureReason, ProbeStatus


class ProbeCreate(BaseModel):
    video_id: int
    download_speed_mbps: float | None = None
    status: ProbeStatus
    failure_reason: ProbeFailureReason | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class ProbeRead(BaseModel):
    id: int
    video_id: int
    download_speed_mbps: float | None = None
    status: ProbeStatus
    failure_reason: ProbeFailureReason | None = None
    created_at: datetime

    class Config:
        from_attributes = True
