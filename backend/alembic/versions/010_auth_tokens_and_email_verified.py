"""Add auth_tokens table and email_verified + password_changed_at to users.

Revision ID: 010
Revises: 009
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to users table.
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Create auth_tokens table.
    op.create_table(
        "auth_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("token_type", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
    )
    op.create_index(
        "ix_auth_tokens_user_id_token_type",
        "auth_tokens",
        ["user_id", "token_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_tokens_user_id_token_type", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "email_verified")
