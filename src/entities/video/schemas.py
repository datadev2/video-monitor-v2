from pydantic import BaseModel


class VideoRead(BaseModel):
    id: int
    storage_id: int | None = None
    url: str
    bitrate_mbps: float | None = None
    duration_seconds: float | None = None
    size_mb: float | None = None

    class Config:
        from_attributes = True


class VideoCreate(BaseModel):
    storage_id: int | None = None
    url: str


class VideoUpdate(BaseModel):
    bitrate_mbps: float | None = None
    duration_seconds: float | None = None
    size_mb: float | None = None
