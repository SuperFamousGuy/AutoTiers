"""player_stats.fumbles_lost + two_pt_conversions columns

Revision ID: 013
Revises: 012
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("player_stats", sa.Column("fumbles_lost", sa.Integer(), nullable=True))
    op.add_column("player_stats", sa.Column("two_pt_conversions", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_stats", "two_pt_conversions")
    op.drop_column("player_stats", "fumbles_lost")
