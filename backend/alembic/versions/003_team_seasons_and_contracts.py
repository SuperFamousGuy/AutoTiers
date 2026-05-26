"""team_seasons and player_contracts tables

Revision ID: 003
Revises: 002_data_pipeline
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002_data_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_seasons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("team", sa.String(5), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("points_scored", sa.Integer(), nullable=False),
        sa.Column("points_rank", sa.Integer(), nullable=True),
        sa.Column("last_updated", sa.Date(), nullable=True),
        sa.UniqueConstraint("team", "season", name="uq_team_seasons_team_season"),
    )
    op.create_index("ix_team_seasons_season", "team_seasons", ["season"])

    op.create_table(
        "player_contracts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.String(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("cap_hit", sa.Float(), nullable=False),
        sa.Column("base_salary", sa.Float(), nullable=True),
        sa.Column("signing_bonus", sa.Float(), nullable=True),
        sa.Column("last_updated", sa.Date(), nullable=True),
        sa.UniqueConstraint("player_id", "season", name="uq_player_contracts_player_season"),
    )
    op.create_index("ix_player_contracts_season", "player_contracts", ["season"])


def downgrade() -> None:
    op.drop_index("ix_player_contracts_season", table_name="player_contracts")
    op.drop_table("player_contracts")
    op.drop_index("ix_team_seasons_season", table_name="team_seasons")
    op.drop_table("team_seasons")
