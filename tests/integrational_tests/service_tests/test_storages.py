import pytest

from src.entities.storage.model import Storage
from src.entities.storage.schemas import StorageCreate
from src.entities.storage.services import StorageService


@pytest.mark.asyncio
class TestStorageService:
    async def test_get_by_name_found(self, async_session):
        service = StorageService(async_session)

        result = await service.get_by_name("st1.pimpbunny.com")

        assert result is not None
        assert result.name == "st1.pimpbunny.com"

    async def test_get_by_name_not_found(self, async_session):
        service = StorageService(async_session)

        result = await service.get_by_name("MissingStorage")

        assert result is None

    async def test_create_storage(self, async_session):
        service = StorageService(async_session)

        payload = StorageCreate(name="NewStorage")

        result = await service.create(payload)

        assert result.name == "NewStorage"
        assert result.id is not None

        db_obj = await async_session.get(Storage, result.id)
        assert db_obj is not None
        assert db_obj.name == "NewStorage"
