from __future__ import annotations

import io
import os
import re
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import JSONResponse

from .admin_models import Feedback, FeedbackBan, FeedbackScreenshot
from .admin_security import ACTOR, audit, begin_write, public_origin, secret, source_hash, take_quota
from .models import now_utc


MAX_BODY = 12 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_PIXELS = 60_000_000
IMAGE_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
FeedbackStatus = Literal["new", "triaged", "replied", "resolved", "spam"]


class FeedbackError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def invalid(message: str) -> FeedbackError:
    return FeedbackError(400, "invalid_request", message)


def screenshot_mime(data: bytes) -> str:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data), formats=tuple(IMAGE_MIME)) as image:
            mime = IMAGE_MIME[image.format]
            pixels = image.width * image.height
            if pixels > MAX_PIXELS:
                raise ValueError
            image.verify()
        with Image.open(io.BytesIO(data), formats=tuple(IMAGE_MIME)) as image:
            frame = 0
            while True:
                if pixels * (frame + 1) > MAX_PIXELS:
                    raise ValueError
                image.load()
                frame += 1
                try:
                    image.seek(frame)
                except EOFError:
                    break
        return mime
    except (KeyError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise invalid("截图无法识别或超过像素上限。") from exc


def clean_page(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) > 500 or any(ord(char) < 32 or char.isspace() or char == "\\" for char in value):
        raise invalid("关联页面地址无效。")
    try:
        parts = urlsplit(value)
        _ = parts.port
        relative = value.startswith("/") and not value.startswith("//") and not parts.netloc
        absolute = parts.scheme in {"http", "https"} and parts.hostname and not (parts.username or parts.password)
    except ValueError as exc:
        raise invalid("关联页面地址无效。") from exc
    if not (relative or absolute):
        raise invalid("关联页面地址无效。")
    return value


async def read_form(request: Request) -> tuple[str, str | None, str | None, bytes | None]:
    if not re.match(r"^multipart/form-data(?:;|$)", request.headers.get("content-type", ""), re.I):
        raise invalid("请使用反馈表单提交文字和截图。")
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or len(length) > 12 or int(length) > MAX_BODY):
        raise FeedbackError(413, "request_too_large", "反馈请求过大。")

    too_large = False

    async def bounded_stream():
        nonlocal too_large
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY:
                too_large = True
                # MultiPartParser closes any files it has already opened on this exception.
                raise MultiPartException("request too large")
            yield chunk

    try:
        form = await MultiPartParser(request.headers, bounded_stream(), max_files=1, max_fields=3,
                                     max_part_size=32 * 1024).parse()
    except MultiPartException as exc:
        if too_large:
            raise FeedbackError(413, "request_too_large", "反馈请求过大。") from exc
        raise invalid("反馈表单格式无效。") from exc
    except (ValueError, RuntimeError) as exc:
        raise invalid("反馈表单格式无效。") from exc
    try:
        pairs = form.multi_items()
        keys = set(form.keys())
        if len(keys) != len(pairs) or keys - {"content", "email", "pageUrl", "screenshot"}:
            raise invalid("反馈表单字段无效。")
        fields = [form.get(key, "") for key in ("content", "email", "pageUrl")]
        if not all(isinstance(value, str) for value in fields):
            raise invalid("反馈文字格式无效。")
        content, email, page_url = (value.strip() for value in fields)
        if not 2 <= len(content) <= 5000:
            raise invalid("反馈内容需为 2 至 5000 字。")
        if email and (len(email) > 200 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            raise invalid("邮箱格式不正确。")
        file = form.get("screenshot")
        if file is not None and not isinstance(file, UploadFile):
            raise invalid("截图上传格式无效。")
        data = await file.read(MAX_IMAGE + 1) if file is not None else None
        if data is not None and len(data) > MAX_IMAGE:
            raise FeedbackError(413, "request_too_large", "截图最大 8 MiB。")
        return content, email or None, clean_page(page_url), data
    finally:
        await form.close()


def save_feedback(session: Session, source: str, content: str, email: str | None,
                  page_url: str | None, data: bytes | None) -> int:
    begin_write(session)
    if session.get(FeedbackBan, source):
        raise FeedbackError(403, "forbidden", "暂时无法提交反馈。")
    if not take_quota(session, {f"feedback:{source}": 5}, seconds=60, now=now_utc()):
        raise FeedbackError(429, "rate_limited", "提交太频繁，请稍后再试。")
    # Persist admission separately so malformed images also consume the decode quota.
    session.commit()
    mime = screenshot_mime(data) if data is not None else None
    begin_write(session)
    if session.get(FeedbackBan, source):
        raise FeedbackError(403, "forbidden", "暂时无法提交反馈。")
    row = Feedback(content=content, email=email, page_url=page_url, source_hash=source)
    session.add(row)
    session.flush()
    if mime:
        session.add(FeedbackScreenshot(feedback_id=row.id, mime=mime, data=data))
    identifier = row.id
    session.commit()
    return identifier


class FeedbackPatch(BaseModel):
    version: int = Field(ge=1)
    status: FeedbackStatus | None = None
    note: str | None = Field(default=None, max_length=5000)


class Reason(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class Ban(Reason):
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


def pack_feedback(row: Feedback, has_screenshot: bool) -> dict:
    return {"id": row.id, "content": row.content, "email": row.email, "page_url": row.page_url,
            "source_hash": row.source_hash, "status": row.status, "note": row.note,
            "version": row.version, "screenshot": has_screenshot, "created_at": row.created_at,
            "updated_at": row.updated_at, "erased_at": row.erased_at}


def register_feedback(router: APIRouter, session_dep, guard, error) -> None:
    protected = [Depends(guard)]

    @router.post("/site/feedback", status_code=201)
    async def submit(request: Request, response: Response, session: Session = Depends(session_dep)):
        response.headers["Cache-Control"] = "no-store"
        key = secret()
        if os.environ.get("BLUEPULSE_FEEDBACK_ENABLED") != "1" or not key:
            raise error(503, "feedback_not_connected", "反馈接收服务尚未启用。")
        origin = request.headers.get("origin")
        if origin is not None and origin != public_origin():
            raise error(403, "forbidden", "请从本站反馈页提交。")
        try:
            fields = await read_form(request)
            return {"id": await run_in_threadpool(save_feedback, session, source_hash(request, key), *fields)}
        except FeedbackError as exc:
            if exc.status == 429:
                return JSONResponse({"error": {"code": exc.code, "message": exc.message,
                                               "request_id": getattr(request.state, "request_id", None)}},
                                    status_code=429, headers={"Cache-Control": "no-store", "Retry-After": "60"})
            raise error(exc.status, exc.code, exc.message) from exc

    def required(session: Session, identifier: int) -> Feedback:
        row = session.get(Feedback, identifier)
        if row is None:
            raise error(404, "not_found", "反馈不存在。")
        return row

    def serialize(session: Session, row: Feedback) -> dict:
        has_image = session.scalar(select(FeedbackScreenshot.feedback_id).where(
            FeedbackScreenshot.feedback_id == row.id)) is not None
        return pack_feedback(row, has_image)

    @router.get("/admin/feedback", dependencies=protected)
    def feedback_list(status: FeedbackStatus | None = None, q: str = "", page: int = 1,
                      session: Session = Depends(session_dep)):
        query = select(Feedback, FeedbackScreenshot.feedback_id).outerjoin(FeedbackScreenshot)
        if status:
            query = query.where(Feedback.status == status)
        if q.strip():
            query = query.where(or_(*(column.contains(q.strip()[:200], autoescape=True)
                                      for column in (Feedback.content, Feedback.email, Feedback.page_url))))
        page = min(max(page, 1), 100_000)
        rows = session.execute(query.order_by(Feedback.created_at.desc(), Feedback.id.desc())
                               .limit(50).offset((page - 1) * 50))
        counts = dict(session.execute(select(Feedback.status, func.count()).group_by(Feedback.status)).all())
        bans = session.scalars(select(FeedbackBan).order_by(FeedbackBan.created_at.desc()).limit(100))
        return {"page": page, "rows": [pack_feedback(row, image_id is not None) for row, image_id in rows],
                "counts": counts, "bans": [{"source_hash": row.source_hash, "reason": row.reason} for row in bans]}

    @router.get("/admin/feedback/{identifier}", dependencies=protected)
    def feedback_detail(identifier: int, session: Session = Depends(session_dep)):
        return serialize(session, required(session, identifier))

    @router.get("/admin/feedback/{identifier}/screenshot", dependencies=protected)
    def screenshot(identifier: int, session: Session = Depends(session_dep)):
        row = session.get(FeedbackScreenshot, identifier)
        if row is None:
            raise error(404, "not_found", "截图不存在。")
        return Response(row.data, media_type=row.mime, headers={"Cache-Control": "no-store",
                                                                "X-Content-Type-Options": "nosniff"})

    @router.patch("/admin/feedback/{identifier}", dependencies=protected)
    def feedback_patch(identifier: int, body: FeedbackPatch, session: Session = Depends(session_dep)):
        begin_write(session)
        row = required(session, identifier)
        if row.version != body.version or row.erased_at:
            raise error(409, "conflict", "反馈已修改或删除，请刷新后重试。")
        before = row.status
        if body.status:
            row.status = body.status
        if "note" in body.model_fields_set:
            row.note = body.note
        row.updated_at = now_utc()
        row.version += 1
        audit(session, "feedback.update", f"feedback:{identifier}",
              changes={"status_before": before, "status_after": row.status})
        result = serialize(session, row)
        session.commit()
        return result

    @router.post("/admin/feedback/{identifier}/erase", dependencies=protected)
    def erase(identifier: int, body: Reason, session: Session = Depends(session_dep)):
        if not body.reason.strip():
            raise error(400, "invalid_request", "请填写删除原因。")
        begin_write(session)
        row = required(session, identifier)
        if row.erased_at is None:
            image = session.get(FeedbackScreenshot, identifier)
            if image:
                session.delete(image)
            row.content = row.email = row.page_url = row.note = row.source_hash = None
            row.erased_at = row.updated_at = now_utc()
            row.version += 1
            audit(session, "feedback.erase", f"feedback:{identifier}", reason=body.reason.strip())
        session.commit()
        return {"erased": True}

    @router.post("/admin/feedback-bans", status_code=204, dependencies=protected)
    def ban(body: Ban, session: Session = Depends(session_dep)):
        if not body.reason.strip():
            raise error(400, "invalid_request", "请填写封禁原因。")
        begin_write(session)
        if session.get(FeedbackBan, body.source_hash) is None:
            session.add(FeedbackBan(source_hash=body.source_hash, reason=body.reason.strip(), actor=ACTOR))
            audit(session, "feedback.ban", f"feedback-source:{body.source_hash}", reason=body.reason.strip())
        session.commit()

    @router.delete("/admin/feedback-bans/{source}", status_code=204, dependencies=protected)
    def unban(source: str, session: Session = Depends(session_dep)):
        begin_write(session)
        row = session.get(FeedbackBan, source)
        if row:
            session.delete(row)
            audit(session, "feedback.unban", f"feedback-source:{source}")
        session.commit()
