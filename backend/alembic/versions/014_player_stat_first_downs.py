"""player_stats.first_down_rush + first_down_rec columns

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
    op.add_column("player_stats", sa.Column("first_down_rush", sa.Integer(), nullable=True))
    op.add_column("player_stats", sa.Column("first_down_rec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_stats", "first_down_rec")
    op.drop_column("player_stats", "first_down_rush")
