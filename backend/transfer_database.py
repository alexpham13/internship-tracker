"""Copy durable InternTrack records from SQLite into an empty PostgreSQL database."""

import argparse
import sqlite3
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, select
from sqlalchemy.exc import SQLAlchemyError

from .database import lock_schema, make_engine
from .migrations import require_current_schema
from .models import Application, AuthRateLimit, AuthSession, ImportedApplication, User

DURABLE_TABLES = (User.__table__, Application.__table__, ImportedApplication.__table__)
TARGET_TABLES = (*DURABLE_TABLES, AuthSession.__table__, AuthRateLimit.__table__)
BATCH_SIZE = 500


def copy_records(source: Connection, target: Connection) -> dict[str, int]:
    counts = {}
    for table in DURABLE_TABLES:
        # Keep public IDs and owners. PostgreSQL allocates its own internal row IDs.
        columns = [column for column in table.columns if column.name != "row_id"]
        statement = select(*columns)
        if "row_id" in table.c:
            statement = statement.order_by(table.c.row_id)
        count = 0
        for batch in source.execute(statement).mappings().partitions(BATCH_SIZE):
            target.execute(table.insert(), [dict(row) for row in batch])
            count += len(batch)
        counts[table.name] = count
    return counts


def transfer_sqlite(source_path: Path, target_engine: Engine) -> dict[str, int]:
    if target_engine.dialect.name != "postgresql":
        raise ValueError("Set DATABASE_URL to the destination PostgreSQL database.")
    source_path = source_path.resolve(strict=True)
    source_engine = create_engine(
        "sqlite://",
        creator=lambda: sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True),
        hide_parameters=True,
    )
    try:
        with source_engine.begin() as source, target_engine.begin() as target:
            source.exec_driver_sql("BEGIN")
            require_current_schema(source)
            lock_schema(target)
            require_current_schema(target)
            # Hold writes while checking emptiness and copying, including from any running API workers.
            names = ", ".join(table.name for table in TARGET_TABLES)
            target.exec_driver_sql(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE")
            if any(target.execute(select(1).select_from(table).limit(1)).first() for table in TARGET_TABLES):
                raise ValueError("The target database already contains InternTrack data. Use an empty migrated database.")
            return copy_records(source, target)
    finally:
        source_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to an Alembic-upgraded SQLite backup")
    args = parser.parse_args()
    engine = None
    try:
        engine = make_engine()
        counts = transfer_sqlite(args.source, engine)
    except FileNotFoundError:
        parser.exit(1, "The SQLite backup file does not exist. No records were copied.\n")
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    except SQLAlchemyError as error:
        parser.exit(1, f"Database transfer failed ({type(error).__name__}). Verify both database connections and schemas.\n")
    finally:
        if engine is not None:
            engine.dispose()
    for table, count in counts.items():
        print(f"{table}: {count} rows copied")


if __name__ == "__main__":
    main()
