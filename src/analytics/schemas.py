from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, field_validator


class BaselineAnalytics(BaseModel):
    storage_id: int
    storage_name: str
    baseline: float

    @field_validator("baseline", mode="after")
    @classmethod
    def round_baseline(cls, value: float) -> float:
        return round(value, 2)


class DownloadSpeedAnalytics(BaseModel):
    storage_id: int
    storage_name: str
    avg_download_speed: float

    @field_validator("avg_download_speed", mode="after")
    @classmethod
    def round_avg_download_speed(cls, value: float) -> float:
        return round(value, 2)


class MissingBitrateAnalytics(BaseModel):
    storage_id: int
    storage_name: str
    videos_without_bitrate: int
    videos_total: int


class FailureBreakdown(BaseModel):
    """A count of failed probes for one storage and one reason."""

    storage_id: int
    storage_name: str
    reason: str
    count: int
    affects_health: bool


class StatusData(BaseModel):
    status: Literal["Healthy", "Warning", "Critical", "Failed"]
    count: int


class StatusAnalytics(BaseModel):
    storage_name: str
    storage_id: int
    statuses: list[StatusData]


class Analytics(BaseModel):
    baseline: Sequence[BaselineAnalytics]
    download_speed: Sequence[DownloadSpeedAnalytics]
    statuses: Sequence[StatusAnalytics]
    missing_bitrate: Sequence[MissingBitrateAnalytics]
    failures: Sequence[FailureBreakdown]
