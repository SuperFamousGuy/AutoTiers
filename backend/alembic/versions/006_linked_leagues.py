"""linked_leagues table

Revision ID: 006_linked_leagues
Revises: 005_user_google_subject
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "006_linked_leagues"
down_revision = "005_user_google_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linked_leagues",
        sa.Column("profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("league_id", sa.String(), nullable=False),
        sa.Column("username_or_swid", sa.String(), nullable=False),
        sa.Column("credentials_encrypted", sa.String(), nullable=True),
        sa.Column("league_metadata_json", JSONB(), nullable=False),
        sa.Column("keepers_json", JSONB(), nullable=False),
        sa.Column("adp_json", JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("linked_leagues")
