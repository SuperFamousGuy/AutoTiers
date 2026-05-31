"""relax linked_leagues NOT NULL on league_id + metadata + keepers

Allows a profile to link a provider account (Sleeper username, ESPN cookies)
without selecting a specific league. Future features that pull auth-gated
data from these providers don't always need a league.

Revision ID: 007
Revises: 006
Create Date: 2026-05-31
"""
from alembic import op


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("linked_leagues", "league_id", nullable=True)
    op.alter_column("linked_leagues", "league_metadata_json", nullable=True)
    op.alter_column("linked_leagues", "keepers_json", nullable=True)


def downgrade() -> None:
    # Backfill any rows that ended up with NULL so the NOT NULL re-add succeeds.
    op.execute("UPDATE linked_leagues SET league_id = '' WHERE league_id IS NULL")
    op.execute("UPDATE linked_leagues SET league_metadata_json = '{}'::jsonb WHERE league_metadata_json IS NULL")
    op.execute("UPDATE linked_leagues SET keepers_json = '[]'::jsonb WHERE keepers_json IS NULL")
    op.alter_column("linked_leagues", "league_id", nullable=False)
    op.alter_column("linked_leagues", "league_metadata_json", nullable=False)
    op.alter_column("linked_leagues", "keepers_json", nullable=False)
