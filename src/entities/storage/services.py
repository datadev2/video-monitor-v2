from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import config
from src.entities.storage.dao import StorageDAO
from src.entities.storage.model import Storage
from src.entities.storage.schemas import StorageCreate, StorageRead, StorageSlots
from src.entities.video.model import Video


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

    async def get_slots(self) -> list[StorageSlots]:
        """
        Count how many probe videos each storage is missing.

        A storage keeps a pool of config.probes_per_storage videos. Only
        videos that are not marked as bad occupy a slot: a bad video is
        never probed again, so its slot is free to be refilled.

        Storages without a server group are left out, since there is no
        way to tell which KVS videos live on them.

        Returns:
            list[StorageSlots]: Every storage with a known server group,
                including those whose pool is already full.
        """
        active_videos = func.count(Video.id).filter(Video.is_bad.is_(False))
        stmt = (
            select(Storage.id, Storage.server_group_id, active_videos)
            .outerjoin(Video, Video.storage_id == Storage.id)
            .where(Storage.server_group_id.is_not(None))
            .group_by(Storage.id)
        )
        result = await self.session.execute(stmt)
        return [
            StorageSlots(
                storage_id=storage_id,
                server_group_id=server_group_id,
                free_slots=max(config.probes_per_storage - active, 0),
            )
            for storage_id, server_group_id, active in result.all()
        ]
