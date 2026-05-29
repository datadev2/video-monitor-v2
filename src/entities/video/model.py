from sqlalchemy import ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    storage_id: Mapped[int] = mapped_column(
        ForeignKey("storages.id"), index=True, nullable=True
    )
    url: Mapped[str] = mapped_column(Text, unique=True)
    bitrate_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
