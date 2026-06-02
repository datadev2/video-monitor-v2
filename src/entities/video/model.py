from datetime import datetime

from sqlalchemy import ForeignKey, Text, Float, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    storage_id: Mapped[int] = mapped_column(
        ForeignKey("storages.id"), index=True, nullable=True
    )
    kvs_id: Mapped[int] = mapped_column(Integer, unique=True)
    server_group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    video_format: Mapped[str] = mapped_column(Text, nullable=False)

    bitrate_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)

    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_bad: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    probes: Mapped[list["Probe"]] = relationship(back_populates="video")  # noqa: F821
    storage: Mapped["Storage | None"] = relationship(back_populates="videos")  # noqa: F821
