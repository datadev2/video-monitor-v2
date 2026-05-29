from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.storage.dao import StorageDAO
from src.entities.storage.schemas import StorageRead, StorageCreate


class StorageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dao = StorageDAO(self.session)

    async def get_by_name(self, name: str) -> StorageRead | None:
        result = await self.dao.find_one(name=name)
        if result is not None:
            return StorageRead.model_validate(result)
        return None

    async def create(self, storage: StorageCreate) -> StorageRead:
        result = await self.dao.create(**storage.model_dump())
        await self.session.commit()
        return StorageRead.model_validate(result)
