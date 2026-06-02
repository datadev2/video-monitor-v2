import pytest

from src.entities.probe.enums import ProbeStatus
from src.entities.probe.schemas import ProbeCreate
from src.entities.probe.services import ProbeService


@pytest.mark.asyncio
class TestProbeService:
    async def test_create_probe(self, async_session):
        service = ProbeService(async_session)

        payload = ProbeCreate(
            video_id=1,
            download_speed_mbps=12.5,
            status=ProbeStatus.CRITICAL,
        )

        result = await service.create(payload)

        assert result.video_id == 1
        assert result.download_speed_mbps == 12.5
        assert result.status == ProbeStatus.CRITICAL
