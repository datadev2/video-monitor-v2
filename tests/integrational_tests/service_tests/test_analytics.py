from datetime import timedelta, timezone, datetime

import pytest

from src.analytics.analytics_service import AnalyticsService


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
