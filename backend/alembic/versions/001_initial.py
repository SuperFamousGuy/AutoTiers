"""initial

Revision ID: 001
Revises:
Create Date: 2026-05-20

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'players',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('position', sa.String(length=10), nullable=False),
        sa.Column('team', sa.String(length=5), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('years_exp', sa.Integer(), nullable=True),
        sa.Column('last_updated', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'team_context',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('team', sa.String(length=5), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('off_line_grade', sa.Float(), nullable=True),
        sa.Column('new_head_coach', sa.Boolean(), nullable=False),
        sa.Column('coaching_scheme', sa.String(length=50), nullable=True),
        sa.Column('last_updated', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team', 'season', name='uq_team_season'),
    )
    op.create_table(
        'adp_data',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.String(), nullable=False),
        sa.Column('format', sa.String(length=20), nullable=False),
        sa.Column('adp', sa.Float(), nullable=False),
        sa.Column('adp_source', sa.String(length=30), nullable=False),
        sa.Column('last_updated', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'format', 'adp_source', name='uq_adp'),
    )
    op.create_table(
        'player_stats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.String(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('targets', sa.Integer(), nullable=True),
        sa.Column('receptions', sa.Integer(), nullable=True),
        sa.Column('rec_yards', sa.Float(), nullable=True),
        sa.Column('rec_tds', sa.Integer(), nullable=True),
        sa.Column('rush_att', sa.Integer(), nullable=True),
        sa.Column('rush_yards', sa.Float(), nullable=True),
        sa.Column('rush_tds', sa.Integer(), nullable=True),
        sa.Column('pass_att', sa.Integer(), nullable=True),
        sa.Column('pass_yards', sa.Float(), nullable=True),
        sa.Column('pass_tds', sa.Integer(), nullable=True),
        sa.Column('interceptions', sa.Integer(), nullable=True),
        sa.Column('snaps', sa.Integer(), nullable=True),
        sa.Column('snap_pct', sa.Float(), nullable=True),
        sa.Column('carry_share', sa.Float(), nullable=True),
        sa.Column('target_share', sa.Float(), nullable=True),
        sa.Column('games_played', sa.Integer(), nullable=True),
        sa.Column('red_zone_looks', sa.Integer(), nullable=True),
        sa.Column('actual_tds', sa.Integer(), nullable=True),
        sa.Column('expected_tds', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'season', name='uq_player_season'),
    )
    op.create_table(
        'projections',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('player_id', sa.String(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('scoring_format', sa.String(length=20), nullable=False),
        sa.Column('projected_points', sa.Float(), nullable=False),
        sa.Column('last_updated', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'source', 'scoring_format', name='uq_projection'),
    )


def downgrade() -> None:
    op.drop_table('projections')
    op.drop_table('player_stats')
    op.drop_table('adp_data')
    op.drop_table('team_context')
    op.drop_table('players')
