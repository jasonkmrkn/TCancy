import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import select

from app import security

from app.db import SessionLocal
from app.models import User
from app.schemas import AlumniRegisterIn


def create_admin(username: str, password: str) -> User:
    """Create an active admin account. Raises ValueError on bad input or a taken username."""
    try:
        data = AlumniRegisterIn(username=username, password=password)
    except ValidationError as exc:
        raise ValueError(exc.errors()[0]["msg"].removeprefix("Value error, "))
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == data.username)) is not None:
            raise ValueError("username already taken")
        user = User(
            username=data.username,
            password_hash=security.hash_password(data.password),
            role="admin",
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def purge_expired_proofs() -> int:
    """Expire verification requests past their 14 days; returns how many expired."""
    from app import proof_purge

    with SessionLocal() as db:
        return proof_purge.purge_expired(db)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="TCancy admin tools")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="create an admin account (password is asked by prompt)")
    p.add_argument("--username", help="admin username (asked by prompt if omitted)")
    sub.add_parser(
        "purge-expired-proofs",
        help="expire verification requests older than 14 days and delete their proofs and packages",
    )
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        username = args.username or input("Username: ")
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            print("error: passwords do not match", file=sys.stderr)
            return 1
        try:
            user = create_admin(username, password)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Admin '{user.username}' created.")
    elif args.command == "purge-expired-proofs":
        count = purge_expired_proofs()
        print(f"Expired {count} verification request(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
