from datetime import datetime, timezone

from pydantic import Field, BaseModel

from src.entities.probe.enums import ProbeStatus


class ProbeCreate(BaseModel):
    video_id: int
    download_speed_mbps: float
    status: ProbeStatus
    created_at: datetime = Field(default=datetime.now(tz=timezone.utc))


class ProbeRead(BaseModel):
    id: int
    video_id: int
    download_speed_mbps: float
    status: ProbeStatus
    created_at: datetime

    class Config:
        from_attributes = True
