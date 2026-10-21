"""Snapshot reusable extraction results for incremental reports."""

import sqlalchemy as sa
from alembic import op

revision = "e95a4b3d206c"
down_revision = "d84f3a2c105b"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("summary_jobs", sa.Column("processing_snapshot", sa.JSON(), nullable=True))
    op.add_column(
        "summary_jobs",
        sa.Column("reused_documents", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade():
    op.drop_column("summary_jobs", "reused_documents")
    op.drop_column("summary_jobs", "processing_snapshot")
