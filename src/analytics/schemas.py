from typing import Literal, Sequence

from pydantic import BaseModel


class BaselineAnalytics(BaseModel):
    storage_id: int
    storage_name: str
    baseline: float


class DownloadSpeedAnalytics(BaseModel):
    storage_id: int
    storage_name: str
    avg_download_speed: float


class StatusData(BaseModel):
    status: Literal["Healthy", "Warning", "Critical"]
    count: int


class StatusAnalytics(BaseModel):
    storage_name: str
    storage_id: int
    statuses: list[StatusData]


class Analytics(BaseModel):
    baseline: Sequence[BaselineAnalytics]
    download_speed: Sequence[DownloadSpeedAnalytics]
    statuses: Sequence[StatusAnalytics]
