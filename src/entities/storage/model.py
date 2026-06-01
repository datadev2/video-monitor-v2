from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Storage(Base):
    __tablename__ = "storages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    videos: Mapped[list["Video"]] = relationship(  # noqa: F821
        back_populates="storage",
    )
