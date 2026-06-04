from sqlalchemy import select, func

from src.config import config
from src.entities.probe.enums import ProbeStatus
from src.entities.probe.model import Probe
from src.entities.storage.model import Storage
from src.entities.video.model import Video


class BaselineCalculator:
    """
    Calculates storage download speed baselines.

    Baselines are used to evaluate probe results and determine
    whether a storage is performing below its expected download speed.
    """

    def __init__(self, session):
        self.session = session

    async def calculate_baseline(self, storage_id: int) -> float:
        """
        Calculate the baseline download speed for a storage.

        The baseline is defined as the average download speed of all
        healthy probes associated with the specified storage.

        To avoid unrealistic thresholds for new or sparsely probed
        storages, the calculated value is never allowed to fall below
        the configured minimum baseline speed.

        Args:
            storage_id: Storage identifier.

        Returns:
            float: Calculated baseline download speed in Mbps.
        """
        stmt = (
            select(func.avg(Probe.download_speed_mbps))
            .join(Video, Video.id == Probe.video_id)
            .join(Storage, Storage.id == Video.storage_id)
            .where(Probe.status == ProbeStatus.HEALTHY, Storage.id == storage_id)
        )
        result = await self.session.execute(stmt)
        return max(result.scalar() or 0, config.min_baseline_speed_mbps)
