"""storage server group id

Revision ID: d2e8f5a61c47
Revises: c7a4e1b90d32
Create Date: 2026-09-18 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d2e8f5a61c47"
down_revision: Union[str, Sequence[str], None] = "c7a4e1b90d32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The KVS API lists videos by server group, never by storage, so the
# video loader needs this mapping to know which storage a video fills.
STORAGE_SERVER_GROUPS = {
    "st1.pimpbunny.com": 3,
    "st2.pimpbunny.com": 4,
    "st3.pimpbunny.com": 5,
    "st5.pimpbunny.com": 7,
    "st7.pimpbunny.com": 15,
    "st8.pimpbunny.com": 16,
    "st9.pimpbunny.com": 11,
    "st10.pimpbunny.com": 12,
    "st11.pimpbunny.com": 17,
    "st12.pimpbunny.com": 18,
    "st13.pimpbunny.com": 19,
    "st14.pimpbunny.com": 20,
    "st15.pimpbunny.com": 21,
    "st16.pimpbunny.com": 22,
    "st17.pimpbunny.com": 23,
    "st22.pimpbunny.com": 29,
    "st23.pimpbunny.com": 30,
    "st24.pimpbunny.com": 31,
    "st28.pimpbunny.com": 35,
    "st29.pimpbunny.com": 36,
    "st30.pimpbunny.com": 37,
    "st31.pimpbunny.com": 38,
    "st32.pimpbunny.com": 39,
    "st33.pimpbunny.com": 40,
    "st34.pimpbunny.com": 41,
    "st35.pimpbunny.com": 42,
    "st36.pimpbunny.com": 43,
    "st37.pimpbunny.com": 44,
    "st38.pimpbunny.com": 45,
    "st39.pimpbunny.com": 46,
    "st40.pimpbunny.com": 47,
    "st41.pimpbunny.com": 48,
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("storages", sa.Column("server_group_id", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        "uq_storages_server_group_id", "storages", ["server_group_id"]
    )

    stmt = sa.text(
        "INSERT INTO storages (name, server_group_id) "
        "VALUES (:name, :server_group_id) "
        "ON CONFLICT (name) DO UPDATE "
        "SET server_group_id = EXCLUDED.server_group_id"
    )
    op.get_bind().execute(
        stmt,
        [
            {"name": name, "server_group_id": server_group_id}
            for name, server_group_id in STORAGE_SERVER_GROUPS.items()
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Storages inserted by the upgrade are left in place: videos may already
    # reference them, and a storage without a server group is still valid.
    op.drop_constraint("uq_storages_server_group_id", "storages", type_="unique")
    op.drop_column("storages", "server_group_id")
