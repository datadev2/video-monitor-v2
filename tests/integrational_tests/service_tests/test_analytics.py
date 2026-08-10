from datetime import timedelta, timezone, datetime

import pytest
import sqlalchemy as sa

from src.analytics.analytics_service import UNSPECIFIED_REASON, AnalyticsService
from src.entities.probe.enums import ProbeFailureReason, ProbeStatus
from src.entities.probe.model import Probe
from src.entities.video.model import Video


class MockAnalyticsService(AnalyticsService):
    @staticmethod
    def _analytics_period_start() -> datetime:
        """Return the beginning of the analytics time window."""
        return datetime.now(timezone.utc) - timedelta(days=3650)


@pytest.mark.asyncio
class TestAnalyticsService:
    async def test_baselines_analytics(self, async_session):
        service = MockAnalyticsService(async_session)

        result = await service.get_baselines()

        assert len(result) > 0

        for item in result:
            assert item.storage_id
            assert item.storage_name
            assert item.baseline > 0

    async def test_get_download_speed(self, async_session):
        service = MockAnalyticsService(async_session)

        result = await service.get_download_speed()

        assert len(result) > 0

        for item in result:
            assert item.avg_download_speed > 0

    async def test_get_missing_bitrate(self, async_session):
        service = MockAnalyticsService(async_session)

        result = await service.get_missing_bitrate()

        assert len(result) > 0

        for item in result:
            assert item.storage_id
            assert item.storage_name
            assert item.videos_total > 0
            assert 0 <= item.videos_without_bitrate <= item.videos_total

    async def test_get_missing_bitrate_counts_null_bitrate(self, async_session):
        """A storage keeps reporting zero rather than dropping out."""
        service = MockAnalyticsService(async_session)

        before = {item.storage_id: item for item in await service.get_missing_bitrate()}

        video = Video(
            storage_id=1,
            kvs_id=999001,
            server_group_id=10,
            video_format="_1080p.mp4",
            bitrate_mbps=None,
            is_bad=False,
        )
        async_session.add(video)
        await async_session.commit()

        after = {item.storage_id: item for item in await service.get_missing_bitrate()}

        assert after[1].videos_without_bitrate == before[1].videos_without_bitrate + 1
        assert after[1].videos_total == before[1].videos_total + 1

    async def test_get_missing_bitrate_ignores_excluded_videos(self, async_session):
        service = MockAnalyticsService(async_session)

        before = {item.storage_id: item for item in await service.get_missing_bitrate()}

        video = Video(
            storage_id=1,
            kvs_id=999002,
            server_group_id=10,
            video_format="_1080p.mp4",
            bitrate_mbps=None,
            is_bad=True,
        )
        async_session.add(video)
        await async_session.commit()

        after = {item.storage_id: item for item in await service.get_missing_bitrate()}

        assert after[1].videos_without_bitrate == before[1].videos_without_bitrate
        assert after[1].videos_total == before[1].videos_total

    async def test_get_health_statuses_sql(self, async_session):
        service = MockAnalyticsService(async_session)

        rows = await service._get_health_statuses_sql()

        assert len(rows) > 0

        row = rows[0]

        assert "count" in row
        assert "storage_id" in row
        assert "storage_name" in row
        assert "status" in row

    async def test_get_health_statuses(self, async_session):
        service = MockAnalyticsService(async_session)

        result = await service.get_health_statuses()

        assert len(result) > 0

        for storage in result:
            assert storage.storage_id
            assert storage.storage_name
            assert len(storage.statuses) > 0

            for status in storage.statuses:
                assert status.status in (
                    "Healthy",
                    "Warning",
                    "Critical",
                )
                assert status.count > 0


def _failed_count(statuses) -> int:
    """Number of probes reported as Failed for one storage."""
    return sum(s.count for s in statuses if s.status == "Failed")


async def _add_failed_probe(session, reason: ProbeFailureReason) -> None:
    """Record a failed probe against video 1, which belongs to storage 1."""
    session.add(
        Probe(
            video_id=1,
            download_speed_mbps=None,
            status=ProbeStatus.FAILED,
            failure_reason=reason,
        )
    )
    await session.commit()


@pytest.mark.asyncio
class TestHealthStatusExcludesNonQualityFailures:
    """
    The health gauge grades how well a storage serves files.

    A probe that failed for a reason unrelated to serving quality - the
    video was deleted, our IP was blocked - must not land next to
    Warning and Critical, or a content cleanup would read as an outage.
    """

    async def _failed_for_storage_1(self, service) -> int:
        result = await service.get_health_statuses()
        by_id = {s.storage_id: s for s in result}

        if 1 not in by_id:
            return 0

        return _failed_count(by_id[1].statuses)

    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.FILE_MISSING_ON_NODE,
            ProbeFailureReason.FILE_MISSING_IN_CATALOG,
            ProbeFailureReason.INVALID_METADATA,
            ProbeFailureReason.LINK_REJECTED,
            ProbeFailureReason.IP_BLOCKED,
            ProbeFailureReason.RATE_LIMITED,
            ProbeFailureReason.VIDEO_TOO_SMALL,
            ProbeFailureReason.UNKNOWN,
        ],
    )
    async def test_excluded_reasons_do_not_count_as_failed(self, async_session, reason):
        service = MockAnalyticsService(async_session)

        before = await self._failed_for_storage_1(service)
        await _add_failed_probe(async_session, reason)
        after = await self._failed_for_storage_1(service)

        assert after == before, f"{reason.value} must not appear in the health gauge"

    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.STORAGE_ERROR,
            ProbeFailureReason.STORAGE_UNREACHABLE,
            ProbeFailureReason.ORIGIN_UNREACHABLE,
            ProbeFailureReason.ORIGIN_TLS_ERROR,
        ],
    )
    async def test_delivery_failures_still_count_as_failed(self, async_session, reason):
        """Excluding deleted videos must not hide a storage that is down."""
        service = MockAnalyticsService(async_session)

        before = await self._failed_for_storage_1(service)
        await _add_failed_probe(async_session, reason)
        after = await self._failed_for_storage_1(service)

        assert after == before + 1

    async def test_healthy_probes_are_untouched(self, async_session):
        """The filter must only ever drop failures, never graded probes."""
        service = MockAnalyticsService(async_session)

        def healthy(result):
            by_id = {s.storage_id: s for s in result}
            return sum(s.count for s in by_id[1].statuses if s.status == "Healthy")

        before = healthy(await service.get_health_statuses())
        await _add_failed_probe(async_session, ProbeFailureReason.FILE_MISSING_ON_NODE)
        after = healthy(await service.get_health_statuses())

        assert after == before


@pytest.mark.asyncio
class TestFailureBreakdown:
    """Nothing dropped from the health gauge may vanish from the metrics."""

    async def _reasons_for_storage_1(self, service) -> dict[str, int]:
        result = await service.get_failure_breakdown()
        return {f.reason: f.count for f in result if f.storage_id == 1}

    @pytest.mark.parametrize(
        "reason",
        [
            ProbeFailureReason.FILE_MISSING_IN_CATALOG,
            ProbeFailureReason.IP_BLOCKED,
            ProbeFailureReason.STORAGE_ERROR,
        ],
    )
    async def test_every_failure_is_reported_by_reason(self, async_session, reason):
        service = MockAnalyticsService(async_session)

        before = await self._reasons_for_storage_1(service)
        await _add_failed_probe(async_session, reason)
        after = await self._reasons_for_storage_1(service)

        assert after.get(reason.value, 0) == before.get(reason.value, 0) + 1

    async def test_failure_without_a_reason_is_still_counted(self, async_session):
        """
        A failed probe must never be invisible everywhere.

        Rows written before failure_reason existed are dropped by the
        health gauge (an unattributable failure is not evidence about
        the storage), so the breakdown has to be the place they land.
        """
        service = MockAnalyticsService(async_session)

        await async_session.execute(
            sa.text(
                "INSERT INTO probes"
                " (video_id, download_speed_mbps, status, failure_reason, created_at)"
                " VALUES (1, NULL, 'Failed', NULL, now())"
            )
        )
        await async_session.commit()

        reported = {
            f.reason: f
            for f in await service.get_failure_breakdown()
            if f.storage_id == 1
        }

        assert UNSPECIFIED_REASON in reported
        assert reported[UNSPECIFIED_REASON].count == 1
        assert reported[UNSPECIFIED_REASON].affects_health is False

    async def test_breakdown_flags_whether_health_is_affected(self, async_session):
        service = MockAnalyticsService(async_session)

        await _add_failed_probe(async_session, ProbeFailureReason.FILE_MISSING_ON_NODE)
        await _add_failed_probe(async_session, ProbeFailureReason.STORAGE_ERROR)

        flags = {
            f.reason: f.affects_health
            for f in await service.get_failure_breakdown()
            if f.storage_id == 1
        }

        assert flags[ProbeFailureReason.FILE_MISSING_ON_NODE.value] is False
        assert flags[ProbeFailureReason.STORAGE_ERROR.value] is True
