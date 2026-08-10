from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.entities.probe.enums import ProbeFailureReason, ProbeStatus


class ProbeCreate(BaseModel):
    video_id: int
    download_speed_mbps: float | None = None
    status: ProbeStatus
    failure_reason: ProbeFailureReason | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ProbeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    download_speed_mbps: float | None = None
    status: ProbeStatus
    failure_reason: ProbeFailureReason | None = None
    created_at: datetime
