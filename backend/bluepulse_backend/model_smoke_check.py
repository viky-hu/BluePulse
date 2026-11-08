"""Opt-in, three-call AutoDL compatibility check using an isolated fictional fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, make_engine
from .live_model import DEFAULT_MODEL_ENV, LiveAnalyzer, ProviderRejected, load_local_credentials, model_listed
from .models import AnalysisAttempt, Material, Source
from .pipeline import process_pending
from .selection_scoring import process_selection


FIXTURE_BODY = (
    "This is a fictional public-text fixture for API compatibility testing, not a real news report. "
    "In this simulated scenario, a police technology unit plans a limited trial of a drone mapping system "
    "for search and rescue training. The proposed system would use thermal images and offline mapping "
    "to help officers mark search areas during a training exercise. No operational deployment or measured "
    "improvement is claimed. The trial plan requires human review of image detections, access controls, "
    "and deletion of training images after evaluation. The document describes planned testing only, "
    "and provides no evidence of effectiveness or procurement completion."
)


def _safe(value, secret: str):
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]") if secret else value
    if isinstance(value, list):
        return [_safe(item, secret) for item in value]
    if isinstance(value, dict):
        # Usage counters remain available; private reasoning text does not enter artifacts.
        return {_safe(key, secret): _safe(item, secret) for key, item in value.items()
                if key not in {"reasoning_content", "reasoning"}}
    return value


def run(output_dir: Path, *, execute: bool = False, allow_paid_model: bool = False,
        max_model_calls_total: int = 0, env: Path = DEFAULT_MODEL_ENV,
        transport: httpx.BaseTransport | None = None) -> dict:
    if not execute and not allow_paid_model and max_model_calls_total == 0:
        return {"status": "disabled", "paid_calls_started": 0,
                "message": "Use --execute --allow-paid-model --max-model-calls-total 3 to opt in."}
    if not execute or not allow_paid_model or max_model_calls_total != 3:
        raise ValueError("explicit_three_call_limit_required")
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output_directory_must_be_empty")
    base, secret, model = load_local_credentials(env)
    parts = urlsplit(base)
    if parts.path.rstrip("/") != "/api/v1" or parts.query or parts.fragment:
        raise ValueError("unexpected_autodl_endpoint")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    report_path.touch(exist_ok=False)
    database_url = f"sqlite:///{(output_dir / 'smoke.db').as_posix()}"
    report = {"status": "prepared", "fixture": "fictional-police-drone-plan-v1", "model": model,
              "endpoint": base, "database_url": database_url, "report": str(report_path),
              "business_database_written": False, "max_paid_calls": 3, "paid_calls_started": 0,
              "calls": []}
    stage = "preflight"
    call_started = 0.0

    def save():
        temporary = report_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(_safe(report, secret), file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        # Windows scanners may briefly lock a just-replaced JSON file. Retry only
        # the durable file replacement, never a provider request or business step.
        for index in range(4):
            try:
                temporary.replace(report_path)
                break
            except PermissionError:
                if index == 3:
                    raise
                time.sleep(0.05)

    def before_request(request: httpx.Request):
        nonlocal call_started
        if request.method == "GET" and stage == "preflight" and request.url.path == "/api/v1/models":
            return
        if request.method != "POST" or request.url.path != "/api/v1/chat/completions":
            raise ValueError("unexpected_smoke_request")
        if report["paid_calls_started"] >= max_model_calls_total:
            raise ValueError("smoke_call_limit_reached")
        call_started = time.monotonic()
        report["paid_calls_started"] += 1
        report["calls"].append({"stage": stage, "status": "started", "response_received": False,
                                "request_sha256": hashlib.sha256(request.content).hexdigest(),
                                "request_payload": json.loads(request.content)})
        save()  # Must finish before httpx sends the paid request.

    def after_response(response: httpx.Response):
        if response.request.method == "GET":
            report["preflight_http_status"] = response.status_code
            return
        response.read()
        call = report["calls"][-1]
        call.update(status="received", response_received=True, http_status=response.status_code,
                    duration_ms=round((time.monotonic() - call_started) * 1000))
        try:
            envelope = response.json()
        except ValueError:
            envelope = None
            call["response_invalid_json"] = True
        call["response"] = _safe(envelope, secret)
        choices = envelope.get("choices") if isinstance(envelope, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        message = choice.get("message")
        reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
        call["reasoning_chars"] = len(reasoning) if isinstance(reasoning, str) else 0
        usage = envelope.get("usage") if isinstance(envelope, dict) else None
        reasoning_tokens = None
        if isinstance(usage, dict):
            for key in ("completion_tokens_details", "output_tokens_details"):
                details = usage.get(key)
                if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), (int, float)):
                    reasoning_tokens = max(reasoning_tokens or 0, details["reasoning_tokens"])
        call["reasoning_tokens"] = reasoning_tokens
        save()  # Received response is durable before LiveAnalyzer parses it.
        if response.status_code == 200 and (call["reasoning_chars"] or (reasoning_tokens or 0) > 0):
            raise ProviderRejected("provider_thinking_not_disabled", stop_batch=True, provider_meta={
                "http_status": response.status_code, "request_id": _safe(envelope.get("id"), secret),
                "finish_reason": _safe(choice.get("finish_reason"), secret), "usage": _safe(usage, secret),
                "duration_ms": call["duration_ms"], "reasoning_chars": call["reasoning_chars"]})

    def update_calls(session):
        attempts = session.scalars(select(AnalysisAttempt).order_by(AnalysisAttempt.created_at)).all()
        for call, attempt in zip(report["calls"], attempts):
            call["status"] = "parsed" if attempt.status == "applied" else attempt.status
            call["attempt_id"] = attempt.id
            call["input_version"] = attempt.input_version
            if attempt.error_code:
                call["error_code"] = attempt.error_code

    engine = None
    save()
    try:
        with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False, transport=transport,
                          event_hooks={"request": [before_request], "response": [after_response]}) as client:
            analyzer = LiveAnalyzer(client, base, secret, model)
            if not analyzer.autodl_profile:
                raise ValueError("unsupported_smoke_model")
            report["model_listed"] = model_listed(client, base, secret, model)
            save()
            if not report["model_listed"]:
                raise ValueError("configured_model_not_listed")
            engine = make_engine(database_url)
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                source = Source(slug="smoke-fixture", name="Fictional API compatibility fixture",
                                allowed_hosts=["example.test"], excerpt_allowed=False, full_text_allowed=False)
                row = Material(source=source, canonical_url="https://example.test/model-smoke",
                               source_url="https://example.test/model-smoke", language="en", body_status="full_text",
                               source_title="Fictional plan for police drone search-and-rescue training",
                               source_body=FIXTURE_BODY, content_hash=hashlib.sha256(FIXTURE_BODY.encode()).hexdigest())
                session.add(row)
                session.commit()
                stage = "classification"
                outcome = process_pending(session, analyzer, material_id=row.id, max_items=1)
                update_calls(session)
                save()
                if outcome["unknown"] or outcome["failed"]:
                    report["status"] = "unknown" if outcome["unknown"] else "failed"
                elif not (row.relevant and row.topics and row.zh_title and row.zh_summary
                          and re.search(r"[\u4e00-\u9fff]", row.zh_title)
                          and re.search(r"[\u4e00-\u9fff]", row.zh_summary)):
                    report.update(status="failed", error_code="fixture_classification_not_valid")
                else:
                    report["classification"] = {"title_zh": row.zh_title, "summary_zh": row.zh_summary,
                                                "topics": row.topics}
                    # One round at a time ensures any failed round stops further paid work.
                    for round_number in (1, 2):
                        stage = f"score-{round_number}"
                        scoring = process_selection(session, row, analyzer, max_calls=1)
                        update_calls(session)
                        report["scoring"] = scoring
                        save()
                        if scoring["status"] not in {"partial", "uncalibrated", "complete"}:
                            report["status"] = "unknown" if scoring["status"] == "unknown" else "failed"
                            break
                    else:
                        ids = [call.get("response", {}).get("id") for call in report["calls"]]
                        if len(ids) == 3 and all(ids) and len(set(ids)) == 3:
                            report["status"] = "passed"
                        else:
                            report.update(status="failed", error_code="independent_request_ids_missing")
                report["public_materials"] = int(row.public)
    except Exception as exc:
        report.update(status="failed", error_code=getattr(exc, "code", type(exc).__name__))
    finally:
        if engine is not None:
            engine.dispose()
        save()
    return _safe(report, secret)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid-model", action="store_true")
    parser.add_argument("--max-model-calls-total", type=int, default=0)
    parser.add_argument("--env", type=Path, default=DEFAULT_MODEL_ENV)
    parser.add_argument("--output-dir", type=Path, default=Path("data/model-api-check/fixed-smoke"))
    args = parser.parse_args()
    try:
        report = run(args.output_dir, execute=args.execute, allow_paid_model=args.allow_paid_model,
                     max_model_calls_total=args.max_model_calls_total, env=args.env)
    except (ValueError, OSError) as exc:
        # Do not echo exception messages from arbitrary files or credentials.
        parser.exit(2, f"model_smoke_configuration_error: {type(exc).__name__}\n")
    summary = {key: report[key] for key in ("status", "paid_calls_started", "report", "error_code", "message") if key in report}
    print(json.dumps(summary, ensure_ascii=False))
    raise SystemExit(0 if report["status"] in {"passed", "disabled"} else 1)


if __name__ == "__main__":
    main()
