from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.probe.dao import ProbeDAO
from src.entities.probe.schemas import ProbeCreate, ProbeRead


class ProbeService:
    """Service for managing video probe records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dao = ProbeDAO(self.session)

    async def create(self, probe: ProbeCreate) -> ProbeRead:
        """
        Create a new probe record.

        Args:
            probe: Probe data to persist.

        Returns:
            ProbeRead: Created probe record.
        """
        result = await self.dao.create(**probe.model_dump())
        await self.session.commit()
        return ProbeRead.model_validate(result)
