from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .admin_feedback import register_feedback
from .admin_models import AdminAudit
from .admin_operations import register_operations, source_view
from .admin_security import (ACTOR, audit, begin_write, binding, client_ip, create_session, digest,
                             password, public_origin, read_session, secret, set_cookie, take_quota)
from .models import Source, now_utc


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(max_length=512)


def register_admin(router: APIRouter, session_dep, error) -> None:
    def require_origin(request: Request) -> None:
        origin = public_origin()
        if not origin or request.headers.get("origin") != origin:
            raise error(403, "forbidden", "请从本站管理页操作。")

    def guard(request: Request, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        principal = read_session(session, request)
        if principal is None:
            raise error(401, "unauthorized", "请先登录管理后台。")
        if request.method not in {"GET", "HEAD"}:
            require_origin(request)
            provided = request.headers.get("x-csrf-token", "")
            if not provided.isascii() or not hmac.compare_digest(provided, principal.csrf):
                raise error(403, "forbidden", "操作凭据已失效，请刷新管理页。")
        return principal

    protected = [Depends(guard)]

    @router.post("/admin/login")
    def login(body: Login, request: Request, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        key, expected = secret(), password()
        if not (public_origin() and key and expected):
            raise error(503, "admin_unconfigured", "管理员登录尚未配置。")
        require_origin(request)
        begin_write(session)
        address = digest(key, "admin-ip-v1", client_ip(request))
        now = now_utc()
        if not take_quota(session, {"login:all": 50, f"login:{address}": 10}, seconds=900, now=now):
            raise error(429, "rate_limited", "登录尝试过多，请稍后重试。")
        if not hmac.compare_digest(binding(key, body.password), binding(key, expected)):
            session.commit()
            raise error(401, "invalid_password", "管理员密码错误。")
        previous = read_session(session, request)
        if previous:
            session.delete(previous)
        token, csrf = create_session(session, key, expected, now)
        audit(session, "auth.login")
        session.commit()
        set_cookie(response, token)
        return {"actor": ACTOR, "csrf": csrf}

    @router.get("/admin/session")
    def get_session(principal=Depends(guard)):
        return {"actor": ACTOR, "csrf": principal.csrf}

    @router.post("/admin/logout", status_code=204)
    def logout(response: Response, principal=Depends(guard), session: Session = Depends(session_dep)):
        session.delete(principal)
        audit(session, "auth.logout")
        session.commit()
        set_cookie(response, "", clear=True)

    @router.get("/admin/sources", dependencies=protected)
    def source_list(session: Session = Depends(session_dep)):
        return {"rows": [source_view(source) for source in session.scalars(select(Source).order_by(Source.slug))]}

    @router.get("/admin/sources/{source_id}", dependencies=protected)
    def source_detail(source_id: UUID, session: Session = Depends(session_dep)):
        source = session.get(Source, str(source_id))
        if source is None:
            raise error(404, "not_found", "信源不存在。")
        return source_view(source)

    @router.get("/admin/audit", dependencies=protected)
    def audit_list(page: int = 1, session: Session = Depends(session_dep)):
        page = min(max(page, 1), 100_000)
        query = select(AdminAudit).order_by(AdminAudit.id.desc()).limit(50).offset((page - 1) * 50)
        return {"page": page, "rows": [
            {"id": row.id, "actor": row.actor, "action": row.action, "subject": row.subject,
             "reason": row.reason, "changes": row.changes, "created_at": row.created_at}
            for row in session.scalars(query)
        ]}

    register_feedback(router, session_dep, guard, error)
    register_operations(router, session_dep, guard, error)
