"""T10 — non-superuser application role.

The bootstrap user (`interview`) is a superuser in the dev image and
superusers bypass RLS unconditionally. The application must connect as
`app_user` (NOSUPERUSER) for RLS to bind; migrations keep running as the
owner via MIGRATIONS_DATABASE_URL.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE ROLE app_user LOGIN PASSWORD 'app_user_dev_pass'
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user")
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE interview IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE interview IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO app_user"
    )


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (CLAUDE.md engineering standards)")
