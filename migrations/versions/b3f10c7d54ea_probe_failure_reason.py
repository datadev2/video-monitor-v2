"""probe failure reason

Revision ID: b3f10c7d54ea
Revises: 5ac4df32eb1d
Create Date: 2026-08-07 16:40:11.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b3f10c7d54ea"
down_revision: Union[str, Sequence[str], None] = "5ac4df32eb1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FAILURE_REASONS = (
    "FileMissingOnNode",
    "FileMissingInCatalog",
    "StorageError",
    "StorageUnreachable",
    "InvalidMetadata",
    "LinkRejected",
    "IpBlocked",
    "RateLimited",
    "VideoTooSmall",
    "Unknown",
)


def upgrade() -> None:
    """Upgrade schema."""
    # Failed probes are now persisted, so they need a status of their own.
    # ADD VALUE cannot be used in the same transaction that adds it, which is
    # fine here: nothing in this migration writes probe rows.
    op.execute("ALTER TYPE probe_status ADD VALUE IF NOT EXISTS 'Failed'")

    failure_reason = postgresql.ENUM(
        *FAILURE_REASONS,
        name="probe_failure_reason",
    )
    failure_reason.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "probes",
        sa.Column(
            "failure_reason",
            postgresql.ENUM(
                *FAILURE_REASONS,
                name="probe_failure_reason",
                create_type=False,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Failed probes carry no speed and would skew averages once the code
    # that filters them out is gone.
    op.execute("DELETE FROM probes WHERE download_speed_mbps IS NULL")

    op.drop_column("probes", "failure_reason")

    postgresql.ENUM(name="probe_failure_reason").drop(op.get_bind(), checkfirst=True)

    # 'Failed' is intentionally left in probe_status: removing a value from a
    # postgres enum requires recreating the type, and it is harmless to keep.
