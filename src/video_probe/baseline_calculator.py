from sqlalchemy import select, func

from src.config import config
from src.entities.probe.enums import ProbeStatus
from src.entities.probe.model import Probe
from src.entities.storage.model import Storage
from src.entities.video.model import Video


class BaselineCalculator:
    def __init__(self, session):
        self.session = session

    async def calculate_baseline(self, storage_id: int) -> int:
        stmt = (
            select(func.avg(Probe.download_speed_mbps))
            .join(Video, Video.id == Probe.video_id)
            .join(Storage, Storage.id == Video.storage_id)
            .where(Probe.status == ProbeStatus.HEALTHY, Storage.id == storage_id)
        )
        result = await self.session.execute(stmt)
        return max(result.scalar() or 0, config.min_baseline_speed_mbps)
