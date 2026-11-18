"""Explicit local bootstrap for the first admin; never creates or resets credentials."""

import argparse

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.data.session import engine
from app.schemas.users.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote an existing local Basalam account to admin")
    parser.add_argument("--mobile", required=True, help="Existing account mobile number")
    parser.add_argument("--confirm", action="store_true", help="Confirm the role change")
    args = parser.parse_args()
    url = make_url(settings().database_url.get_secret_value())
    if url.host not in ("localhost", "127.0.0.1") or url.database != "basalam":
        raise SystemExit("Admin bootstrap is allowed only for the local basalam database.")
    if not args.confirm:
        raise SystemExit("Pass --confirm to promote the existing account.")
    with Session(engine()) as session:
        if session.scalar(text("SELECT version_num FROM alembic_version")) != "0005_admin_role":
            raise SystemExit("Run uv run alembic upgrade head first.")
        user = session.scalar(select(User).where(User.mobile == args.mobile).with_for_update())
        if user is None or not user.is_active:
            raise SystemExit("An active account with that mobile number is required.")
        user.role = "admin"
        session.commit()
    print("Existing account promoted to admin. Its password, wallet, ledger, and cart were unchanged.")


if __name__ == "__main__":
    main()
