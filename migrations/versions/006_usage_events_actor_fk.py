"""Drop usage_events.actor_id FK — dev tokens may not exist in users table."""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("usage_events_actor_id_fkey", "usage_events", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "usage_events_actor_id_fkey",
        "usage_events",
        "users",
        ["actor_id"],
        ["id"],
    )
