from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.schemas import (
    BaselineAnalytics,
    DownloadSpeedAnalytics,
    StatusAnalytics,
    StatusData,
)
from src.entities.probe.enums import ProbeStatus
from src.entities.probe.model import Probe
from src.entities.storage.model import Storage
from src.entities.video.model import Video


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_baselines(self) -> Sequence[BaselineAnalytics]:
        dt = self._analytics_period_start()
        stmt = (
            select(
                func.avg(Probe.download_speed_mbps).label("baseline"),
                Storage.id.label("storage_id"),
                Storage.name.label("storage_name"),
            )
            .join(Video, Video.id == Probe.video_id)
            .join(Storage, Storage.id == Video.storage_id)
            .where(Probe.status == ProbeStatus.HEALTHY, Probe.created_at > dt)
            .group_by(Storage.id)
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()
        return [BaselineAnalytics(**row) for row in rows]

    async def get_download_speed(self) -> Sequence[DownloadSpeedAnalytics]:
        dt = self._analytics_period_start()
        stmt = (
            select(
                func.avg(Probe.download_speed_mbps).label("avg_download_speed"),
                Storage.id.label("storage_id"),
                Storage.name.label("storage_name"),
            )
            .join(Video, Video.id == Probe.video_id)
            .join(Storage, Storage.id == Video.storage_id)
            .where(Probe.created_at > dt)
            .group_by(Storage.id)
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()
        return [DownloadSpeedAnalytics(**row) for row in rows]

    async def get_health_statuses(self) -> Sequence[StatusAnalytics]:
        mappings = await self._get_health_statuses_sql()
        pre_computed_data: defaultdict = defaultdict(dict)
        for data in mappings:
            storage_id = data.storage_id
            storage_name = data["storage_name"]
            status = data["status"].value
            pre_computed_data[storage_id][status] = data["count"]
            pre_computed_data[storage_id]["storage_name"] = storage_name
        result = []
        for key, value in pre_computed_data.items():
            data = StatusAnalytics(
                storage_id=key,
                storage_name=value.pop("storage_name"),
                statuses=[StatusData(status=k, count=v) for k, v in value.items()],
            )
            result.append(data)
        return result

    async def _get_health_statuses_sql(self) -> Sequence:
        dt = self._analytics_period_start()

        stmt = (
            select(
                func.count(Probe.status).label("count"),
                Storage.id.label("storage_id"),
                Storage.name.label("storage_name"),
                Probe.status.label("status"),
            )
            .join(Video, Video.id == Probe.video_id)
            .join(Storage, Storage.id == Video.storage_id)
            .where(Probe.created_at > dt)
            .group_by(
                Probe.status,
                Storage.id,
            )
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()

        return rows

    @staticmethod
    def _analytics_period_start() -> datetime:
        """Return the beginning of the analytics time window."""
        return datetime.now(timezone.utc) - timedelta(days=1)
