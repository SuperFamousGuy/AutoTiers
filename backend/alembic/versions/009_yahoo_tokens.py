"""Add yahoo_access_token and yahoo_refresh_token to users.

Revision ID: 009
Revises: 008
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("yahoo_access_token", sa.String(), nullable=True))
    op.add_column("users", sa.Column("yahoo_refresh_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "yahoo_refresh_token")
    op.drop_column("users", "yahoo_access_token")
