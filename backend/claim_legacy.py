import argparse

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError

from .database import lock_schema, make_engine
from .migrations import initialize_schema
from .models import Application, ImportedApplication, User


def assign_legacy(engine: Engine, email: str) -> None:
    with engine.begin() as connection:
        lock_schema(connection)
        user_id = connection.scalar(select(User.id).where(User.email == email))
        if user_id is None:
            raise ValueError("Register the intended account before assigning legacy records.")
        owner_id = connection.scalar(select(User.id).where(User.legacy_access.is_(True)))
        if owner_id and owner_id != user_id:
            raise ValueError("Legacy records were already assigned to another account.")
        for model in (Application, ImportedApplication):
            connection.execute(update(model).where(model.user_id.is_(None)).values(user_id=user_id))
        connection.execute(update(User).where(User.id == user_id).values(legacy_access=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign legacy database and browser records to one account.")
    parser.add_argument("email", help="Email of the intended, already registered owner")
    args = parser.parse_args()
    try:
        email = validate_email(args.email, check_deliverability=False).normalized.casefold()
    except EmailNotValidError:
        parser.error("Enter a valid email address.")
    engine = make_engine()
    try:
        initialize_schema(engine)
        assign_legacy(engine, email)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    except IntegrityError:
        parser.exit(1, "An application ID conflicts with this account's records. No legacy data was assigned.\n")
    finally:
        engine.dispose()
    print("Legacy records are now available to the designated account.")


if __name__ == "__main__":
    main()
