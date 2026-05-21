"""data pipeline schema changes

Revision ID: 002_data_pipeline
Revises: 001
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa


revision = "002_data_pipeline"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("players", sa.Column("gsis_id", sa.String(length=20), nullable=True))
    op.add_column("players", sa.Column("espn_id", sa.String(length=20), nullable=True))
    op.create_index("ix_players_gsis_id", "players", ["gsis_id"])
    op.create_index("ix_players_espn_id", "players", ["espn_id"])

    op.create_table(
        "data_source_status",
        sa.Column("source", sa.String(length=30), primary_key=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("last_attempted", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("data_source_status")
    op.drop_index("ix_players_espn_id", table_name="players")
    op.drop_index("ix_players_gsis_id", table_name="players")
    op.drop_column("players", "espn_id")
    op.drop_column("players", "gsis_id")
    op.drop_column("players", "active")
