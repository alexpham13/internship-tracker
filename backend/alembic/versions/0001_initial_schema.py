"""Create the initial schema or adopt existing SQLite databases."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

AUTH_COLUMNS = {
    "users": {"id", "name", "email", "password_hash", "legacy_access"},
    "auth_sessions": {"token_hash", "user_id", "expires_at"},
    "auth_rate_limits": {"key", "expires_at", "attempts"},
}
APPLICATION_COLUMNS = {
    "applications": {"id", "company", "position", "location", "date_applied", "status"},
    "imported_applications": {"id"},
}


def create_auth(tables: set[str]) -> None:
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("legacy_access", sa.Boolean(), nullable=False),
        )
    if "auth_sessions" not in tables:
        op.create_table(
            "auth_sessions",
            sa.Column("token_hash", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("expires_at", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    if "auth_rate_limits" not in tables:
        op.create_table(
            "auth_rate_limits",
            sa.Column("key", sa.String(), primary_key=True),
            sa.Column("expires_at", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
        )
        op.create_index("ix_auth_rate_limits_expires_at", "auth_rate_limits", ["expires_at"])


def create_application_table(name: str) -> None:
    columns = [
        sa.Column("row_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("id", sa.String(128), nullable=False),
        sa.UniqueConstraint("user_id", "id"),
    ]
    if name == "applications":
        columns.extend([
            sa.Column("company", sa.String(), nullable=False),
            sa.Column("position", sa.String(), nullable=False),
            sa.Column("location", sa.String(), nullable=False),
            sa.Column("date_applied", sa.Date(), nullable=False),
            sa.Column("status", sa.Enum(
                "Applied", "Responded", "Interview", "Offer", "Rejected",
                name="applicationstatus", create_constraint=True, native_enum=False,
            ), nullable=False),
        ])
    op.create_table(name, *columns)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names()) & (AUTH_COLUMNS.keys() | APPLICATION_COLUMNS.keys())
    if tables and connection.dialect.name != "sqlite":
        raise RuntimeError("Found unversioned InternTrack tables. Use an empty PostgreSQL database for the initial migration.")

    for name in tables & AUTH_COLUMNS.keys():
        if {column["name"] for column in inspector.get_columns(name)} != AUTH_COLUMNS[name]:
            raise RuntimeError(f"Unrecognized SQLite table layout: {name}.")

    create_auth(tables)
    for name, legacy_columns in APPLICATION_COLUMNS.items():
        if name not in tables:
            create_application_table(name)
            continue
        columns = {column["name"] for column in inspector.get_columns(name)}
        if columns == legacy_columns | {"row_id", "user_id"}:
            continue
        if columns != legacy_columns:
            raise RuntimeError(f"Unrecognized SQLite table layout: {name}.")
        previous = f"{name}_before_0001"
        op.rename_table(name, previous)
        create_application_table(name)
        fields = ", ".join(sorted(legacy_columns))
        connection.exec_driver_sql(f"INSERT INTO {name} ({fields}) SELECT {fields} FROM {previous}")
        op.drop_table(previous)


def downgrade() -> None:
    raise RuntimeError("The baseline migration is irreversible. Restore a pre-upgrade backup if needed.")
