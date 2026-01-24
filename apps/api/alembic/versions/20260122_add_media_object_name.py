from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260122_media_storage_fields"
down_revision = "2466277e6062"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Переименования: owner_id -> user_id, object_name -> object_key
    with op.batch_alter_table("media") as batch:
        # owner_id -> user_id
        batch.alter_column("owner_id", new_column_name="user_id")
        # object_name -> object_key
        batch.alter_column("object_name", new_column_name="object_key")

    # 2) Добавляем недостающие колонки (если их ещё нет)
    # (Alembic "if not exists" не поддерживает кросс-СУБД одинаково, поэтому здесь ожидается,
    #  что таблица в текущем состоянии соответствует старой миграции.
    #  Если у тебя таблица уже другая — скажи, я дам вариант с инспекцией.)
    with op.batch_alter_table("media") as batch:
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="uploaded"))
        batch.add_column(sa.Column("checksum_sha256", sa.String(length=64), nullable=True))

    # 3) Индексы/уникальность на объект хранения
    op.create_unique_constraint("uq_media_bucket_object_key", "media", ["bucket", "object_key"])
    op.create_index("ix_media_user_id_created_at", "media", ["user_id", "created_at"])


def downgrade():
    # Снимаем индексы/уникальность
    op.drop_index("ix_media_user_id_created_at", table_name="media")
    op.drop_constraint("uq_media_bucket_object_key", "media", type_="unique")

    # Удаляем добавленные колонки
    with op.batch_alter_table("media") as batch:
        batch.drop_column("checksum_sha256")
        batch.drop_column("status")

    # Возвращаем старые имена (на случай отката)
    with op.batch_alter_table("media") as batch:
        batch.alter_column("user_id", new_column_name="owner_id")
        batch.alter_column("object_key", new_column_name="object_name")