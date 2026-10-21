"""Record generation time separately from queue time."""

import sqlalchemy as sa
from alembic import op

revision = "d84f3a2c105b"
down_revision = "c72e0b4a901f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("summary_jobs", sa.Column("started_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("summary_jobs", "started_at")
