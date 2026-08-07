"""origin failure reasons

Revision ID: c7a4e1b90d32
Revises: b3f10c7d54ea
Create Date: 2026-08-07 19:05:44.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c7a4e1b90d32"
down_revision: Union[str, Sequence[str], None] = "b3f10c7d54ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Cloudflare's 52x codes mean the edge never reached the origin, which is
    # a different defect from a 5xx the application itself produced.
    op.execute(
        "ALTER TYPE probe_failure_reason ADD VALUE IF NOT EXISTS 'OriginUnreachable'"
    )
    op.execute(
        "ALTER TYPE probe_failure_reason ADD VALUE IF NOT EXISTS 'OriginTlsError'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Removing a value from a postgres enum requires recreating the type and
    # rewriting every row that uses it. The spare values are harmless, so they
    # are left in place; only the rows carrying them are folded back.
    op.execute(
        "UPDATE probes SET failure_reason = 'StorageError' "
        "WHERE failure_reason IN ('OriginUnreachable', 'OriginTlsError')"
    )
