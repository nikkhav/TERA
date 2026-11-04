"""Scope employees and their trips to individual accounts."""

import sqlalchemy as sa
from alembic import op

revision = "a17c6d5e408f"
down_revision = "f06b5c4e307d"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows have no reliable creator information. Leave them unassigned
    # and inaccessible until an administrator assigns their verified owner.
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_employees_user_id_users", "users", ["user_id"], ["id"])
        batch.create_index("ix_employees_user_id", ["user_id"])


def downgrade():
    with op.batch_alter_table("employees") as batch:
        batch.drop_index("ix_employees_user_id")
        batch.drop_constraint("fk_employees_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
