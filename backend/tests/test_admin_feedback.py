from __future__ import annotations

import asyncio
from io import BytesIO

import httpx
import pytest
from sqlalchemy.orm import Session

from bluepulse_backend.db import Base, make_engine
from bluepulse_backend.models import Material, MaterialTopic, Source


def admin_client(tmp_path, monkeypatch):
    from bluepulse_backend.api import create_app

    monkeypatch.setenv("BLUEPULSE_SITE_ORIGIN", "https://pulse.example.test")
    monkeypatch.setenv("BLUEPULSE_ADMIN_PASSWORD", "a test password for Pulse")
    monkeypatch.setenv("BLUEPULSE_ADMIN_SESSION_SECRET", "test-session-secret-" * 3)
    monkeypatch.setenv("BLUEPULSE_FEEDBACK_ENABLED", "1")
    monkeypatch.delenv("BLUEPULSE_TRUST_PROXY", raising=False)
    url = f"sqlite:///{(tmp_path / 'admin.db').as_posix()}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(url)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://pulse.example.test/api/v1/")


async def login(client):
    return await client.post("admin/login", headers={"Origin": "https://pulse.example.test"},
                             json={"password": "a test password for Pulse"})


def test_admin_session_is_revocable_and_mutations_require_csrf(tmp_path, monkeypatch):
    async def scenario():
        async with admin_client(tmp_path, monkeypatch) as client:
            assert (await client.get("admin/sources")).status_code == 401
            response = await login(client)
            assert response.status_code == 200
            cookie = response.headers["Set-Cookie"].lower()
            assert all(word in cookie for word in ("httponly", "secure", "samesite=lax"))
            csrf = response.json()["csrf"]
            assert (await client.get("admin/sources")).status_code == 200
            assert (await client.post("admin/logout", headers={"Origin": "https://pulse.example.test"})).status_code == 403
            headers = {"Origin": "https://pulse.example.test", "X-CSRF-Token": csrf}
            assert (await client.post("admin/logout", headers=headers)).status_code == 204
            assert (await client.get("admin/sources")).status_code == 401
            assert (await login(client)).status_code == 200
            monkeypatch.setenv("BLUEPULSE_ADMIN_PASSWORD", "a different admin password")
            assert (await client.get("admin/session")).status_code == 401
            monkeypatch.setenv("BLUEPULSE_ADMIN_PASSWORD", "a test password for Pulse")
            assert (await client.get("admin/session")).status_code == 401

    asyncio.run(scenario())


def test_feedback_rejects_fake_image_and_keeps_real_image_private(tmp_path, monkeypatch):
    async def scenario():
        from PIL import Image

        async with admin_client(tmp_path, monkeypatch) as client:
            fake_png = b"\x89PNG\r\n\x1a\nnot an image"
            invalid = await client.post("site/feedback", data={"content": "图像校验"},
                                        files={"screenshot": ("fake.png", fake_png, "image/png")})
            assert invalid.status_code == 400
            output = BytesIO()
            Image.new("RGB", (2, 2), "green").save(output, "PNG")
            image = output.getvalue()
            response = await client.post("site/feedback", data={"content": "真实反馈", "pageUrl": "/hot"},
                                         files={"screenshot": ("capture.jpg", image, "image/jpeg")})
            assert response.status_code == 201
            receipt_id = response.json()["id"]
            assert isinstance(receipt_id, int) and receipt_id > 0
            resource = f"admin/feedback/{receipt_id}"
            assert (await client.get(f"{resource}/screenshot")).status_code == 401
            headers = {"Origin": "https://pulse.example.test", "X-CSRF-Token": (await login(client)).json()["csrf"]}
            screenshot = await client.get(f"{resource}/screenshot")
            assert screenshot.headers["Content-Type"] == "image/png"
            assert screenshot.content == image
            record = (await client.get(resource)).json()
            patch = {"status": "resolved", "version": record["version"]}
            assert (await client.patch(resource, json=patch, headers=headers)).status_code == 200
            assert (await client.patch(resource, json=patch, headers=headers)).status_code == 409
            assert (await client.post(f"{resource}/erase", json={"reason": "用户要求"}, headers=headers)).status_code == 200
            assert (await client.get(f"{resource}/screenshot")).status_code == 404
            assert (await client.get(resource)).json()["content"] is None

    asyncio.run(scenario())


def test_feedback_limit_survives_connections_and_forged_ip(tmp_path, monkeypatch):
    async def scenario():
        async with admin_client(tmp_path, monkeypatch) as client:
            for index in range(5):
                response = await client.post("site/feedback", files={"content": (None, "限流测试")},
                                             headers={"X-Real-IP": f"192.0.2.{index}"})
                assert response.status_code == 201
            exceeded = await client.post("site/feedback", files={"content": (None, "又一条反馈")},
                                         headers={"X-Real-IP": "203.0.113.8"})
            assert exceeded.status_code == 429
            assert exceeded.headers["Retry-After"] == "60"

    asyncio.run(scenario())


@pytest.mark.parametrize("topics", [["practice"], ["other"],
                                   ["product", "practice", "paper", "law", "embodied",
                                    "public-opinion", "low-altitude", "other"]])
def test_source_and_editorial_mutations_project_with_audit(tmp_path, monkeypatch, topics):
    async def scenario():
        async with admin_client(tmp_path, monkeypatch) as client:
            engine = make_engine(f"sqlite:///{(tmp_path / 'admin.db').as_posix()}")
            with Session(engine, expire_on_commit=False) as session:
                source = Source(slug="fixture", name="测试来源", allowed_hosts=["news.example.test"])
                session.add(source)
                session.flush()
                item = Material(source_id=source.id, source_title="Original",
                                source_url="https://news.example.test/item",
                                canonical_url="https://news.example.test/item",
                                source_body="source evidence " * 40, body_status="full_text",
                                zh_title="原题", zh_summary="原摘要", relevant=True, language="en",
                                content_hash="1" * 64, state="publication_hidden", editorial_revision=1)
                session.add(item)
                session.commit()
            headers = {"Origin": "https://pulse.example.test", "X-CSRF-Token": (await login(client)).json()["csrf"]}
            source_path = f"admin/sources/{source.id}"
            original = (await client.get(source_path)).json()
            edit = await client.patch(f"admin/sources/{source.id}",
                                      json={"excerpt_allowed": True, "reason": "许可已核实",
                                            "version": original["version"]}, headers=headers)
            assert edit.status_code == 200
            assert (await client.patch(source_path, json={"enabled": False, "reason": "误用旧状态",
                                                          "version": original["version"]}, headers=headers)).status_code == 409
            override = await client.post(f"admin/content/{item.id}/override",
                                          json={"zh_title": "人工标题", "topics": topics,
                                                "reason": "纠正标题分类"}, headers=headers)
            assert override.status_code == 200
            with Session(engine) as session:
                material = session.get(Material, item.id)
                assert material.public and material.zh_title == "人工标题"
                assert material.topics == topics
                assert all(session.get(MaterialTopic, (item.id, topic)) is not None for topic in topics)
            removed = await client.post(f"admin/content/{item.id}/visibility",
                                        json={"withdrawn": True, "reason": "已撤回"}, headers=headers)
            assert removed.status_code == 200
            assert not removed.json()["public"]
            actions = [row["action"] for row in (await client.get("admin/audit")).json()["rows"]]
            assert actions == ["content.visibility", "content.override", "source.update", "auth.login"]
            engine.dispose()

    asyncio.run(scenario())
