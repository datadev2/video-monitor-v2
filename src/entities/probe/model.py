from datetime import datetime

from sqlalchemy import ForeignKey, Float, DateTime, func
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


from src.db import Base
from src.entities.probe.enums import ProbeStatus


class Probe(Base):
    __tablename__ = "probes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), index=True)
    download_speed_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[ProbeStatus] = mapped_column(
        PgEnum(
            ProbeStatus,
            name="probe_status",
            values_callable=lambda obj: [e.value for e in obj],
            create_type=False,
        ),
        default=ProbeStatus.HEALTHY.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    video: Mapped["Video"] = relationship(  # noqa: F821
        back_populates="probes",
    )
