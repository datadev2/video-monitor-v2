from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, Generic, Type

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession


class HasId(Protocol):
    id: Any


T = TypeVar("T", bound=HasId)


class BaseDAO(Generic[T]):
    model: Type[T]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> T:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, id: Any) -> T | None:
        return await self.session.get(self.model, id)

    async def find_one(self, **filters) -> T | None:
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
        **filters,
    ) -> Sequence[T]:
        stmt = select(self.model).filter_by(**filters)

        if limit:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, id: Any, **values) -> T | None:
        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .values(**values)
            .returning(self.model)
        )

        result = await self.session.execute(stmt)
        await self.session.flush()

        return result.scalar_one_or_none()

    async def delete(self, id: Any) -> None:
        stmt = delete(self.model).where(self.model.id == id)
        await self.session.execute(stmt)

    async def add_many(self, items: list[dict]) -> None:
        objs = [self.model(**item) for item in items]
        self.session.add_all(objs)
        await self.session.flush()
