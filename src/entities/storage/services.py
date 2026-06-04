from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.storage.dao import StorageDAO
from src.entities.storage.schemas import StorageRead, StorageCreate


class StorageService:
    """Service for managing video storage records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dao = StorageDAO(self.session)

    async def get_by_name(self, name: str) -> StorageRead | None:
        """
        Retrieve a storage by its name.

        Args:
            name: Storage name.

        Returns:
            StorageRead | None: Storage record if found, otherwise None.
        """
        result = await self.dao.find_one(name=name)
        if result is not None:
            return StorageRead.model_validate(result)
        return None

    async def create(self, storage: StorageCreate) -> StorageRead:
        """
        Create a new storage record.

        Args:
            storage: Storage data to persist.

        Returns:
            StorageRead: Created storage record.
        """
        result = await self.dao.create(**storage.model_dump())
        await self.session.commit()
        return StorageRead.model_validate(result)
