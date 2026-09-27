from __future__ import annotations

import argparse
import re
import sys
from getpass import getpass

from argon2 import PasswordHasher
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from bluepulse_backend.db import create_database_engine
from bluepulse_backend.models import AdminAccount

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
PASSWORD_HASHER = PasswordHasher()


def bootstrap_admin() -> int:
    username = input("管理员用户名（3–64 位字母、数字、点、下划线或连字符）: ").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        print("用户名格式无效。", file=sys.stderr)
        return 2

    password = getpass("管理员密码（至少 12 个字符）: ")
    confirmation = getpass("再次输入密码: ")
    if len(password) < 12:
        print("密码至少需要 12 个字符。", file=sys.stderr)
        return 2
    if password != confirmation:
        print("两次输入的密码不一致。", file=sys.stderr)
        return 2

    try:
        engine = create_database_engine()
        try:
            with Session(engine) as session:
                with session.begin():
                    if session.get_bind().dialect.name == "postgresql":
                        session.execute(
                            text("SELECT pg_advisory_xact_lock(:lock_key)"),
                            {"lock_key": 7310042101},
                        )
                    existing = session.scalar(select(AdminAccount.id).limit(1))
                    if existing is not None:
                        print(
                            "管理员账户已存在；首次建号命令不会覆盖或新增账户。",
                            file=sys.stderr,
                        )
                        return 3

                    session.add(
                        AdminAccount(
                            username=username,
                            password_hash=PASSWORD_HASHER.hash(password),
                            is_active=True,
                        )
                    )
        finally:
            engine.dispose()
    except SQLAlchemyError as exc:
        print(
            "数据库操作失败。请确认 PostgreSQL 可连接且已执行 alembic upgrade head。",
            file=sys.stderr,
        )
        print(f"错误类型：{type(exc).__name__}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"管理员账户 {username} 已创建。密码仅以 Argon2id 哈希形式保存。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bluepulse-backend")
    parser.add_argument(
        "command",
        choices=("bootstrap-admin",),
        help="bootstrap-admin：在空管理员表中创建首个管理员",
    )
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        return bootstrap_admin()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
