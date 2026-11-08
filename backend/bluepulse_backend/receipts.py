"""AIHOT paid-request ordering and recovery, adapted to SQLite transactions."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import time
from typing import Callable

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .editorial_models import PaidAttempt, PaidReceipt
from .models import now_utc
from .work_queue import serialized, utc


class BudgetWait(Exception):
    pass


class ReceiptUnknown(Exception):
    pass


@dataclass(frozen=True)
class Budget:
    minute: int
    hour: int
    day: int
    total: int | None = None


def _key(subject, purpose, identity):
    canonical = json.dumps([subject, purpose, identity], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _response(data: dict) -> httpx.Response:
    return httpx.Response(data["status"], headers=data["headers"], content=data["body"].encode())


class PaidGateway:
    def __init__(self, engine, *, service: str, budget: Budget, run_key: str | None = None,
                 redact: Callable = lambda value: value, clock: Callable = now_utc):
        if budget.total is not None and not run_key:
            raise ValueError("total_budget_requires_run_key")
        self.engine, self.service, self.budget = engine, service, budget
        self.run_key, self.redact, self.clock = run_key, redact, clock

    def request(self, subject: str, purpose: str, identity: dict,
                send: Callable[[], httpx.Response]) -> httpx.Response:
        key, started = _key(subject, purpose, identity), self.clock()
        with serialized(self.engine) as session:
            receipt = session.get(PaidReceipt, key)
            if receipt is not None and receipt.status == "received":
                saved = session.get(PaidAttempt, (key, receipt.latest_attempt)).response
                status = saved["status"]
                transient = status == 429 or 500 <= status <= 599
                if not transient:
                    return _response(saved)
                if utc(started) - utc(receipt.updated_at) < timedelta(seconds=60):
                    raise BudgetWait("provider_backoff")
            unresolved = session.scalar(select(PaidReceipt.key).where(
                PaidReceipt.subject == subject, PaidReceipt.purpose == purpose,
                PaidReceipt.status.in_(("pending", "unknown")),
            ).limit(1))
            if unresolved:
                raise ReceiptUnknown(unresolved)
            self._check_budget(session, started)
            if receipt is None:
                receipt = PaidReceipt(key=key, subject=subject, purpose=purpose, request=self.redact(identity),
                                      status="pending", updated_at=started, latest_attempt=0)
                session.add(receipt)
                session.flush()
            number = receipt.latest_attempt + 1
            receipt.status, receipt.updated_at, receipt.latest_attempt = "pending", started, number
            session.add(PaidAttempt(receipt_key=key, number=number, service=self.service,
                                    run_key=self.run_key, sent_at=started, status="pending"))
        monotonic = time.monotonic()
        try:
            response = send()
        except httpx.TransportError as exc:
            self._save(key, number, "unknown", error=type(exc).__name__)
            raise ReceiptUnknown(key) from exc
        raw = self._serialize_response(response, time.monotonic() - monotonic)
        # Retain provider responses even when business parsing or application fails.
        self._save(key, number, "received", response=raw)
        return _response(raw)

    def _check_budget(self, session: Session, now: datetime):
        attempts = select(func.count()).select_from(PaidAttempt).where(PaidAttempt.service == self.service)
        for window, cap in ((60, self.budget.minute), (3600, self.budget.hour), (86400, self.budget.day)):
            if cap <= 0 or session.scalar(attempts.where(
                PaidAttempt.sent_at > now - timedelta(seconds=window)
            )) >= cap:
                raise BudgetWait(f"request_budget_{window}")
        if self.budget.total is not None and session.scalar(
            select(func.count()).select_from(PaidAttempt).where(PaidAttempt.run_key == self.run_key)
        ) >= self.budget.total:
            raise BudgetWait("request_budget_total")

    def _serialize_response(self, response: httpx.Response, duration: float) -> dict:
        try:
            payload = response.json()
        except ValueError:
            body = self.redact(response.text[:2_000_000])
        else:
            choices = payload.get("choices") if isinstance(payload, dict) else None
            if isinstance(choices, list):
                for choice in choices:
                    message = choice.get("message") if isinstance(choice, dict) else None
                    if isinstance(message, dict):
                        reasoning = message.pop("reasoning_content", None)
                        if isinstance(reasoning, str):
                            message["_reasoning_chars"] = len(reasoning)
            body = json.dumps(self.redact(payload), ensure_ascii=False)
        request_id = response.headers.get("x-request-id")
        headers = {"x-request-id": self.redact(request_id)} if request_id else {}
        return {"status": response.status_code, "headers": headers, "body": body,
                "duration_ms": round(duration * 1000)}

    def _save(self, key, number, status, *, response=None, error=None):
        with serialized(self.engine) as session:
            receipt = session.get(PaidReceipt, key)
            attempt = session.get(PaidAttempt, (key, number))
            now = self.clock()
            attempt.status, attempt.finished_at, attempt.response, attempt.error = status, now, response, error
            if receipt.latest_attempt == number and (receipt.status in {"pending", "unknown"} or
                    receipt.status == "retryable" and status == "received"):
                receipt.status, receipt.updated_at = status, now


def release_unknown(session: Session, receipt_key: str, *, billed: bool, note: str) -> bool:
    receipt = session.get(PaidReceipt, receipt_key)
    if receipt is None or receipt.status != "unknown" or not note.strip():
        return False
    _release(session, receipt, now_utc(), note.strip(), billed)
    return True


def _release(session, receipt, now, note, billed):
    receipt.status, receipt.updated_at = "retryable", now
    attempt = session.get(PaidAttempt, (receipt.key, receipt.latest_attempt))
    attempt.release_note, attempt.billed = note, billed


def recover_receipts(engine, now: datetime):
    with serialized(engine) as session:
        for receipt in session.scalars(select(PaidReceipt).where(
            PaidReceipt.status.in_(("pending", "unknown"))
        )):
            age = utc(now) - utc(receipt.updated_at)
            if receipt.status == "pending" and age >= timedelta(minutes=10):
                receipt.status, receipt.updated_at = "unknown", now
                attempt = session.get(PaidAttempt, (receipt.key, receipt.latest_attempt))
                attempt.status, attempt.error = "unknown", "worker_interrupted"
            elif receipt.status == "unknown" and not receipt.auto_released and age >= timedelta(minutes=30):
                _release(session, receipt, now, "结果未知超过 30 分钟，未核对计费", None)
                receipt.auto_released = True
