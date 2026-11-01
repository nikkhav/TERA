"""Support administrator-issued password recovery links and session revocation."""

import sqlalchemy as sa
from alembic import op

revision = "f06b5c4e307d"
down_revision = "e95a4b3d206c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("users", sa.Column("reset_token_hash", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("reset_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"], unique=True)


def downgrade():
    op.drop_index("ix_users_reset_token_hash", table_name="users")
    op.drop_column("users", "reset_expires_at")
    op.drop_column("users", "reset_token_hash")
    op.drop_column("users", "auth_version")
