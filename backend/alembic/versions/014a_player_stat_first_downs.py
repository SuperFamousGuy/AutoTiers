"""player_stats.first_down_rush + first_down_rec columns

This file originally declared `revision = "014"` with `down_revision = "013"`,
the same identifiers as `014_player_draft_capital.py` — both were authored
against the same base independently, producing two files with an identical,
ambiguous revision id. `alembic heads` warned "Revision 014 is present more
than once" and reported two `014 (head)`s, an invalid branched chain.

Fixed by linearizing: `014_player_draft_capital.py` keeps `revision = "014"`
(down_revision = "013"), and this file is renumbered to the unique id `014a`,
chained after it (down_revision = "014"). The two migrations only ADD
independent columns to different tables (players vs. player_stats), so this
ordering choice is arbitrary and has no functional effect either way.

CAUTION: prod's `alembic_version` table may currently record "014" for a run
that actually corresponds to what is now split across 014/014a. Renaming this
revision id can desync a prod DB that already applied the old "014" content
for player_stats — reconcile prod's `alembic_version` row explicitly during
the gated migration-run step (see the plan's Phase 5) rather than assuming a
plain `alembic upgrade head` resolves it.

Revision ID: 014a
Revises: 014
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "014a"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("player_stats", sa.Column("first_down_rush", sa.Integer(), nullable=True))
    op.add_column("player_stats", sa.Column("first_down_rec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_stats", "first_down_rec")
    op.drop_column("player_stats", "first_down_rush")
