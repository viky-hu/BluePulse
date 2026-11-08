from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .admin_models import AdminAudit, AdminRateEvent, AdminSession
from .agent_access import site_origin
from .models import now_utc


COOKIE = "bluepulse_admin"
COOKIE_PATH = "/"
SESSION_DAYS = 30
ACTOR = "admin:local"
UA_PATTERN = re.compile(r"Chrome|Safari|Firefox|Edg|MicroMessenger|Mobile|Android|iPhone|iPad|Mac OS X|Windows")


def secret() -> str | None:
    value = os.environ.get("BLUEPULSE_ADMIN_SESSION_SECRET", "")
    return value if len(value) >= 32 else None


def password() -> str | None:
    value = os.environ.get("BLUEPULSE_ADMIN_PASSWORD", "")
    return value if len(value) >= 12 else None


def digest(key: str, domain: str, value: str) -> str:
    return hmac.new(key.encode(), f"{domain}\x00{value}".encode(), hashlib.sha256).hexdigest()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def binding(key: str, value: str) -> str:
    return digest(key, "admin-password-v1", value)


def audit(session: Session, action: str, subject: str | None = None, *,
          reason: str | None = None, changes: dict | None = None) -> None:
    session.add(AdminAudit(actor=ACTOR, action=action, subject=subject,
                           reason=reason, changes=changes))


def begin_write(session: Session) -> None:
    """Take the SQLite write reservation before quota or optimistic checks."""
    connection = session.connection()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    if os.environ.get("BLUEPULSE_TRUST_PROXY") == "1" and peer in {"127.0.0.1", "::1"}:
        forwarded = request.headers.get("x-real-ip", "")
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer


def source_hash(request: Request, key: str) -> str:
    family = " ".join(UA_PATTERN.findall(request.headers.get("user-agent", "")[:512])[:4])
    return digest(key, "feedback-source-v1", f"{client_ip(request)}|{family}")


def take_quota(session: Session, scopes: dict[str, int], *, seconds: int, now: datetime) -> bool:
    """Call in a short write transaction. All limits apply before any attempts are added."""
    cutoff = now - timedelta(seconds=seconds)
    session.execute(delete(AdminRateEvent).where(AdminRateEvent.created_at <= now - timedelta(minutes=15)))
    counts = dict(session.execute(
        select(AdminRateEvent.scope, func.count()).where(
            AdminRateEvent.scope.in_(scopes), AdminRateEvent.created_at > cutoff,
        ).group_by(AdminRateEvent.scope),
    ).all())
    if any(counts.get(scope, 0) >= limit for scope, limit in scopes.items()):
        return False
    session.add_all(AdminRateEvent(scope=scope, created_at=now) for scope in scopes)
    return True


def public_origin() -> str | None:
    return site_origin(os.environ.get("BLUEPULSE_SITE_ORIGIN"))


def set_cookie(response: Response, token: str, *, clear: bool = False) -> None:
    response.set_cookie(COOKIE, token, max_age=0 if clear else SESSION_DAYS * 86400,
                        path=COOKIE_PATH, secure=bool((public_origin() or "").startswith("https://")),
                        httponly=True, samesite="lax")


def read_session(session: Session, request: Request) -> AdminSession | None:
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    record = session.get(AdminSession, token_hash(token))
    if record is None:
        return None
    expires = record.expires_at.replace(tzinfo=UTC) if record.expires_at.tzinfo is None else record.expires_at
    key, expected = secret(), password()
    if not (key and expected and expires > now_utc() and
            hmac.compare_digest(binding(key, expected), record.binding)):
        session.delete(record)
        session.commit()
        return None
    return record


def create_session(session: Session, key: str, expected: str, now: datetime) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    session.execute(delete(AdminSession).where(AdminSession.expires_at <= now))
    session.add(AdminSession(token_hash=token_hash(token), binding=binding(key, expected),
                             csrf=csrf, expires_at=now + timedelta(days=SESSION_DAYS)))
    return token, csrf
