from sqlalchemy import Engine, inspect

from .database import Base
from .models import Application, ImportedApplication


def initialize_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        # Serialize startup across workers and make SQLite DDL and data copies atomic.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        for model in (Application, ImportedApplication):
            table = model.__table__
            name = table.name
            inspector = inspect(connection)
            if not inspector.has_table(name):
                continue
            old_columns = [column["name"] for column in inspector.get_columns(name)]
            if "user_id" in old_columns:
                continue
            previous = f"{name}_before_auth"
            connection.exec_driver_sql(f"ALTER TABLE {name} RENAME TO {previous}")
            Base.metadata.tables["users"].create(connection, checkfirst=True)
            table.create(connection)
            columns = ", ".join(column.name for column in table.columns if column.name in old_columns)
            connection.exec_driver_sql(f"INSERT INTO {name} ({columns}) SELECT {columns} FROM {previous}")
            connection.exec_driver_sql(f"DROP TABLE {previous}")
        Base.metadata.create_all(connection)
