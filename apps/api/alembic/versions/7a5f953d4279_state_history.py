from alembic import op
import sqlalchemy as sa

revision = "7a5f953d4279"
down_revision = "875af58bbbd8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "state_history",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("from_state", sa.String(), nullable=True),
        sa.Column("to_state", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
    )
    op.create_index("ix_state_history_product_id", "state_history", ["product_id"])
    op.create_index("ix_state_history_actor_id", "state_history", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_state_history_actor_id", table_name="state_history")
    op.drop_index("ix_state_history_product_id", table_name="state_history")
    op.drop_table("state_history")
