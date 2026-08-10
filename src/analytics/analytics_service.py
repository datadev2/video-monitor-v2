from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import RowMapping, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.schemas import (
    BaselineAnalytics,
    DownloadSpeedAnalytics,
    FailureBreakdown,
    MissingBitrateAnalytics,
    StatusAnalytics,
    StatusData,
)
from src.entities.probe.enums import HEALTH_AFFECTING_REASONS, ProbeStatus
from src.entities.probe.model import Probe
from src.entities.storage.model import Storage
from src.entities.video.model import Video

#: Label used for failed probes stored before reasons were recorded.
UNSPECIFIED_REASON = "Unspecified"


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
            .where(
                Probe.created_at > dt,
                Probe.download_speed_mbps.is_not(None),
            )
            .group_by(Storage.id)
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()
        return [DownloadSpeedAnalytics(**row) for row in rows]

    async def get_missing_bitrate(self) -> Sequence[MissingBitrateAnalytics]:
        """
        Count videos in rotation that have no known bitrate.

        Without a bitrate the CRITICAL rule cannot run and the probe is
        graded on the storage baseline alone, so a storage where this
        creeps up is being monitored more weakly than it looks.

        Videos already excluded from probing are ignored - they are not
        being graded either way. Every storage is reported, including
        those with a count of zero, so the gauge never keeps a stale
        value after a storage recovers.

        Returns:
            Sequence[MissingBitrateAnalytics]: Per-storage counts.
        """
        stmt = (
            select(
                Storage.id.label("storage_id"),
                Storage.name.label("storage_name"),
                func.count(Video.id)
                .filter(Video.bitrate_mbps.is_(None))
                .label("videos_without_bitrate"),
                func.count(Video.id).label("videos_total"),
            )
            .join(Video, Video.storage_id == Storage.id)
            .where(Video.is_bad.is_(False))
            .group_by(Storage.id)
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all()
        return [MissingBitrateAnalytics(**row) for row in rows]

    async def get_failure_breakdown(self) -> Sequence[FailureBreakdown]:
        """
        Count failed probes per storage, split by reason.

        This is where failures land regardless of whose fault they are,
        including the ones the health gauge deliberately ignores. A run
        of missing files or a blocked IP is still worth acting on - it
        is just not a verdict on the storage's performance, so it gets
        reported as its own finding instead of inflating Failed.

        Returns:
            Sequence[FailureBreakdown]: Per-storage, per-reason counts.
        """
        dt = self._analytics_period_start()
        stmt = (
            select(
                Storage.id.label("storage_id"),
                Storage.name.label("storage_name"),
                Probe.failure_reason.label("reason"),
                func.count(Probe.id).label("count"),
            )
            .join(Video, Video.id == Probe.video_id)
            .join(Storage, Storage.id == Video.storage_id)
            .where(
                Probe.created_at > dt,
                Probe.status == ProbeStatus.FAILED,
            )
            .group_by(Storage.id, Probe.failure_reason)
        )
        result = await self.session.execute(stmt)

        return [
            FailureBreakdown(
                storage_id=row["storage_id"],
                storage_name=row["storage_name"],
                # Rows predating the failure_reason column carry no reason.
                # They are still reported: a failure the health gauge drops
                # and the breakdown filters out would be counted nowhere.
                reason=row["reason"].value if row["reason"] else UNSPECIFIED_REASON,
                count=row["count"],
                affects_health=bool(row["reason"])
                and row["reason"].affects_storage_health,
            )
            for row in result.mappings().all()
        ]

    async def get_health_statuses(self) -> Sequence[StatusAnalytics]:
        """
        Count probes per status, grouped by storage.

        Returns:
            Sequence[StatusAnalytics]: One entry per storage that has
                probes in the analytics window.
        """
        rows = await self._get_health_statuses_sql()

        names: dict[int, str] = {}
        counts: defaultdict[int, list[StatusData]] = defaultdict(list)

        # Keyed access throughout: `row.count` would resolve to the
        # Sequence.count method rather than the labelled column.
        for row in rows:
            storage_id = row["storage_id"]
            names[storage_id] = row["storage_name"]
            counts[storage_id].append(
                StatusData(status=row["status"].value, count=row["count"])
            )

        return [
            StatusAnalytics(
                storage_id=storage_id,
                storage_name=names[storage_id],
                statuses=statuses,
            )
            for storage_id, statuses in counts.items()
        ]

    async def _get_health_statuses_sql(self) -> Sequence[RowMapping]:
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
            .where(
                Probe.created_at > dt,
                # A graded probe always counts. A failed one only counts
                # when the storage failed to serve a file it should have
                # had - a deleted video is not a quality signal.
                or_(
                    Probe.status != ProbeStatus.FAILED,
                    Probe.failure_reason.in_(HEALTH_AFFECTING_REASONS),
                ),
            )
            .group_by(
                Probe.status,
                Storage.id,
            )
        )
        result = await self.session.execute(stmt)

        return result.mappings().all()

    @staticmethod
    def _analytics_period_start() -> datetime:
        """Return the beginning of the analytics time window."""
        return datetime.now(UTC) - timedelta(days=1)
