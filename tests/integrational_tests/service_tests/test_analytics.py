from datetime import timedelta, timezone, datetime

import pytest

from src.analytics.analytics_service import AnalyticsService
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
