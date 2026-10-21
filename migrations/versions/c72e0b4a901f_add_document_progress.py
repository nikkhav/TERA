"""Track completed documents independently of model requests."""

import sqlalchemy as sa
from alembic import op

revision = "c72e0b4a901f"
down_revision = "9b8f6b9d1e20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "summary_jobs",
        sa.Column("completed_documents", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade():
    op.drop_column("summary_jobs", "completed_documents")
