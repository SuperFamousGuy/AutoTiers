"""players.draft_round + draft_pick columns

Revision ID: 014
Revises: 013
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("draft_round", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("draft_pick", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "draft_pick")
    op.drop_column("players", "draft_round")
