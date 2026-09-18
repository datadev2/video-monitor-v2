from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base

if TYPE_CHECKING:
    from src.entities.video.model import Video


class Storage(Base):
    __tablename__ = "storages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    server_group_id: Mapped[int | None] = mapped_column(
        Integer, unique=True, nullable=True
    )

    videos: Mapped[list[Video]] = relationship(
        back_populates="storage",
    )
