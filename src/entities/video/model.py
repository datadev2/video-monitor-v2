from sqlalchemy import ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base

from src.entities.probe.model import Probe
from src.entities.storage.model import Storage  # noqa: F401


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

    storage: Mapped["Storage | None"] = relationship(
        back_populates="videos",
    )

    probes: Mapped[list["Probe"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="Probe.created_at.desc()",
    )
