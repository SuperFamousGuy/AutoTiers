"""Drop account/auth/linked-league/favorites/profiles tables.

Part of the v1 "anonymous, login-free" teardown (see
docs/superpowers/plans/2026-07-21-strip-accounts-league-linking-ses.md).
Settings profiles and favorites moved to browser localStorage; there are no
more accounts, sessions, OAuth links, or per-user favorites server-side.

FK-safe drop order (derived from the tables' *creating* migrations, not
guessed):

  - `feedback.user_id` -> `users.id` (012_feedback.py; unnamed inline
    ForeignKey, so Postgres auto-named it `feedback_user_id_fkey` per its
    default `<table>_<column>_fkey` convention — no `naming_convention` is
    configured on `Base.metadata` in app/database.py, so there is no other
    candidate name).
  - `users.last_active_profile_id` -> `profiles.id`, named explicitly
    `fk_users_last_active_profile` (004_users_and_profiles.py). This is the
    one back-reference that makes users<->profiles circular, so it must be
    dropped before `profiles` can go.
  - `profiles.user_id` -> `users.id` CASCADE (004_users_and_profiles.py),
    plus `uq_profiles_user_name` and `ix_profiles_user_id` (dropped
    automatically with the table).
  - `linked_leagues.profile_id` -> `profiles.id` CASCADE, and IS also its
    primary key (006_linked_leagues.py) — must go before `profiles`.
  - `user_favorites.user_id` -> `users.id` CASCADE, and is its primary key
    (008_user_favorites.py) — must go before `users`.
  - `auth_tokens.user_id` -> `users.id` CASCADE, unnamed inline FK
    (010_auth_tokens_and_email_verified.py), plus `uq_auth_tokens_token_hash`
    and `ix_auth_tokens_user_id_token_type` (dropped automatically with the
    table) — must go before `users`.

Resulting order: feedback FK/columns -> users->profiles back-reference FK ->
linked_leagues -> profiles -> user_favorites -> auth_tokens -> users.

`op.batch_alter_table` is used for every column/constraint drop (not just
`op.drop_table`) so this migration also runs on SQLite, which cannot execute
`ALTER TABLE ... DROP CONSTRAINT`/`DROP COLUMN` directly and instead rebuilds
the table under the hood when run inside a batch context.

Revision ID: 015
Revises: 014a
Create Date: 2026-07-21
"""
from alembic import op

revision = "015"
down_revision = "014a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Feedback keeps its rows; only the user linkage goes. The FK name is
    #    Postgres's default auto-generated name for an unnamed inline
    #    ForeignKey column constraint (`<table>_<column>_fkey`) — confirmed
    #    by grepping 012_feedback.py, which passes no explicit `name=` to
    #    `sa.ForeignKey(...)`.
    with op.batch_alter_table("feedback") as batch:
        batch.drop_constraint("feedback_user_id_fkey", type_="foreignkey")
        batch.drop_column("user_id")
        batch.drop_column("submitter_email")

    # 2. Drop the users -> profiles back-reference FIRST. This is what makes
    #    users and profiles mutually referential; without dropping it here,
    #    `DROP TABLE profiles` fails on Postgres with "other objects depend
    #    on it" (the FK on `users`).
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_last_active_profile", type_="foreignkey")

    # 3. Drop dependents before parents (FK-safe order).
    op.drop_table("linked_leagues")   # FK -> profiles (and its own PK)
    op.drop_table("profiles")         # FK -> users
    op.drop_table("user_favorites")   # FK -> users (and its own PK)
    op.drop_table("auth_tokens")      # FK -> users
    op.drop_table("users")


def downgrade() -> None:
    # Best-effort, data-less. Account data is unrecoverable after upgrade.
    raise NotImplementedError(
        "irreversible teardown; restore from DB snapshot instead"
    )
