"""Explicit, bounded source collection with an optional capped model pass."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .ccgp_source import CcgpAdapter, HOST as CCGP_HOST, USER_AGENT
from .db import make_engine
from .live_sources import BoundedHTTP, GovUkAdapter, NistRssAdapter, SourceFetchError
from .live_model import LiveAnalyzer, load_local_credentials, model_listed
from .model_processing import process_model_batch
from .models import Source
from .operations import source_funnel
from .pipeline import SourceAdapter, ingest
from .source_expansion import BoundedHtmlSourceAdapter
from .top5_probe import HtmlEvidenceProbe
from .htx_source import HtxNewsAdapter
from .police_science_source import PoliceScienceAdapter
from .statescoop_source import StateScoopAdapter
from .europol_source import EuropolNewsAdapter
from .spf_source import SpfPoliceLifeAdapter


@dataclass(frozen=True)
class SourceSpec:
    slug: str
    name: str
    host: str
    country_code: str | None
    region: str
    language: str
    topics: tuple[str, ...]
    kind: str
    source_type: str = "official"


SOURCES = {
    "govuk": SourceSpec("govuk", "GOV.UK Home Office", "www.gov.uk", "GB", "foreign", "en",
                        ("policing", "policy-standards"), "govuk_api"),
    "ccgp-policing-tech": SourceSpec("ccgp-policing-tech", "中国政府采购网警务科技公告",
                                     CCGP_HOST, "CN", "domestic", "zh",
                                     ("policing", "procurement-projects"), "ccgp_html"),
    "nist-public-safety": SourceSpec("nist-public-safety", "NIST Public Safety", "www.nist.gov",
                                     "US", "foreign", "en", ("public-safety-tech", "research"), "nist_rss"),
    "nist-forensic-science": SourceSpec("nist-forensic-science", "NIST Forensic Science", "www.nist.gov",
                                       "US", "foreign", "en", ("public-safety-tech", "research"), "nist_forensic_rss"),
    "nist-information-technology": SourceSpec("nist-information-technology", "NIST Information Technology",
                                               "www.nist.gov", "US", "foreign", "en",
                                               ("public-safety-tech", "cybersecurity", "artificial-intelligence"),
                                               "nist_it_rss"),
    "nist-standards": SourceSpec("nist-standards", "NIST Standards", "www.nist.gov", "US", "foreign",
                                 "en", ("policy-standards", "research"), "nist_standards_rss"),
    "htx-news": SourceSpec("htx-news", "HTX News", "www.htx.gov.sg", "SG", "foreign", "en",
                           ("policing", "public-safety-tech", "artificial-intelligence"), "htx_news"),
    "police-science": SourceSpec("police-science", "Police Science & Technology", "science.police.uk",
                                 "GB", "foreign", "en",
                                 ("policing", "public-safety-tech", "research"), "police_science"),
    "npcc": SourceSpec("npcc", "NPCC News", "news.npcc.police.uk", "GB", "foreign", "en",
                       ("policing", "public-safety-tech"), "npcc_html"),
    "jiangsu-police": SourceSpec("jiangsu-police", "江苏省公安厅警务动态", "gat.jiangsu.gov.cn",
                                 "CN", "domestic", "zh", ("policing", "public-safety-tech"),
                                 "jiangsu_html"),
    "police-digital-service": SourceSpec("police-digital-service", "Police Digital Service",
                                         "pds.police.uk", "GB", "foreign", "en",
                                         ("policing", "public-safety-tech", "cybersecurity"), "pds_html"),
    "biometric-update-law-enforcement": SourceSpec(
        "biometric-update-law-enforcement", "Biometric Update Law Enforcement",
        "www.biometricupdate.com", None, "foreign", "en",
        ("policing", "public-safety-tech"), "biometric_html", "media"),
    "statescoop-law-enforcement-tech": SourceSpec(
        "statescoop-law-enforcement-tech", "StateScoop Law Enforcement Technology",
        "statescoop.com", "US", "foreign", "en",
        ("policing", "public-safety-tech", "artificial-intelligence"), "statescoop_rss", "media"),
    "europol-news": SourceSpec("europol-news", "Europol Newsroom", "www.europol.europa.eu",
                                None, "foreign", "en",
                                ("policing", "public-safety-tech", "cybersecurity"), "europol_rss"),
    "spf-police-life": SourceSpec("spf-police-life", "Singapore Police Force Police Life",
                                  "www.police.gov.sg", "SG", "foreign", "en",
                                  ("policing", "public-safety-tech", "cybersecurity"), "spf_police_life"),
}


class _EntryRobotsAdapter:
    """Use the same robots gate for preview, ingest, and source audit."""

    def __init__(self, wrapped: SourceAdapter, client: httpx.Client, host: str):
        self.wrapped, self.client, self.host = wrapped, client, host
        self.robots_status: int | None = None
        self._guarded = False

    def __getattr__(self, name: str):
        return getattr(self.wrapped, name)

    @property
    def diagnostics(self) -> dict:
        return {**getattr(self.wrapped, "diagnostics", {}), "robots_status": self.robots_status}

    def candidates(self):
        if not self._guarded:
            try:
                raw = BoundedHTTP(self.client, allowed_hosts={self.host}).get(
                    f"https://{self.host}/robots.txt", accept="text/plain")
                self.robots_status = 200
            except SourceFetchError as exc:
                if exc.code != "http_404":
                    raise
                raw, self.robots_status = b"", 404
            policy = RobotFileParser()
            policy.parse(raw.decode("utf-8-sig", "replace").splitlines())
            delay = policy.crawl_delay(USER_AGENT) or 0
            entry = getattr(self.wrapped, "SEARCH", None) or self.wrapped.feed
            if delay > 10 or not policy.can_fetch(USER_AGENT, entry):
                raise SourceFetchError("robots_disallowed_or_delayed")
            self.wrapped.http.delay_seconds = max(self.wrapped.http.delay_seconds, delay)

            def guard(request: httpx.Request) -> None:
                if (request.url.host == self.host and request.url.path != "/robots.txt"
                        and not policy.can_fetch(USER_AGENT, str(request.url))):
                    raise SourceFetchError("robots_disallowed")

            self.client.event_hooks["request"].append(guard)
            self._guarded = True
        return self.wrapped.candidates()


def build_adapter(spec: SourceSpec, client: httpx.Client, *, max_items: int) -> SourceAdapter:
    http = BoundedHTTP(client, allowed_hosts={spec.host}, delay_seconds=0.3)
    if spec.kind == "govuk_api":
        return _EntryRobotsAdapter(GovUkAdapter(http, max_items=max_items), client, spec.host)
    if spec.kind == "ccgp_html":
        return CcgpAdapter(http, max_items=max_items)
    if spec.kind == "nist_rss":
        return _EntryRobotsAdapter(NistRssAdapter(http, max_items=max_items), client, spec.host)
    if spec.kind == "nist_forensic_rss":
        return _EntryRobotsAdapter(NistRssAdapter(
            http, max_items=max_items, feed="https://www.nist.gov/news-events/forensic%20science/rss.xml"),
            client, spec.host)
    if spec.kind == "nist_it_rss":
        return _EntryRobotsAdapter(NistRssAdapter(
            http, max_items=max_items, feed="https://www.nist.gov/news-events/information%20technology/rss.xml",
            focused=True),
            client, spec.host)
    if spec.kind == "nist_standards_rss":
        return _EntryRobotsAdapter(NistRssAdapter(
            http, max_items=max_items, feed="https://www.nist.gov/news-events/standards/rss.xml",
            focused=True),
            client, spec.host)
    if spec.kind == "htx_news":
        return HtxNewsAdapter(BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=1_000_000,
                                          delay_seconds=0.3), max_items=max_items)
    if spec.kind == "police_science":
        return PoliceScienceAdapter(BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=1_000_000,
                                                delay_seconds=0.3), max_items=max_items)
    if spec.kind == "statescoop_rss":
        return StateScoopAdapter(BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=500_000,
                                             delay_seconds=0.3), max_items=max_items)
    if spec.kind == "europol_rss":
        return EuropolNewsAdapter(BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=1_000_000,
                                               delay_seconds=0.3), max_items=max_items)
    if spec.kind == "spf_police_life":
        return SpfPoliceLifeAdapter(BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=500_000,
                                                delay_seconds=0.3), max_items=max_items)
    if spec.kind in {"npcc_html", "jiangsu_html"}:
        return HtmlEvidenceProbe(
            BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=1_000_000, delay_seconds=0.3),
            kind="npcc" if spec.kind == "npcc_html" else "jiangsu", max_items=max_items,
        )
    if spec.kind in {"pds_html", "biometric_html"}:
        kind = {"pds_html": "pds", "biometric_html": "biometric"}[spec.kind]
        return BoundedHtmlSourceAdapter(
            BoundedHTTP(client, allowed_hosts={spec.host}, max_bytes=1_000_000, delay_seconds=0.3),
            kind=kind, max_items=max_items,
        )
    raise ValueError("unknown_source_kind")


def ensure_source(session: Session, spec: SourceSpec) -> Source:
    source = session.scalar(select(Source).where(Source.slug == spec.slug))
    if source is not None:
        if source.allowed_hosts != [spec.host]:
            raise ValueError("source_host_policy_mismatch")
        return source
    source = Source(slug=spec.slug, name=spec.name, region=spec.region,
                    country_code=spec.country_code, language=spec.language,
                    source_type=spec.source_type, topics=list(spec.topics),
                    allowed_hosts=[spec.host], enabled=True,
                    excerpt_allowed=False, full_text_allowed=False,
                    min_body_status="full_text")
    session.add(source)
    session.commit()
    return source


def collect(session: Session, spec: SourceSpec, adapter: SourceAdapter) -> dict:
    source = ensure_source(session, spec)
    run = ingest(session, source, adapter)
    return source_funnel(session, run.id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded source preview, ingest, or explicit paid analysis")
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--mode", choices=("preview", "ingest", "ingest-analyze"), default="preview")
    parser.add_argument("--max-items", type=int, default=2)
    parser.add_argument("--max-model-calls", type=int, default=2)
    parser.add_argument("--env", type=Path, default=Path(__file__).resolve().parents[3] / ".env")
    parser.add_argument("--database-url", help="required for ingest; target database must already be migrated")
    parser.add_argument("--execute", action="store_true", help="required to enable public network requests")
    parser.add_argument("--allow-paid-model", action="store_true", help="required for ingest-analyze")
    args = parser.parse_args()
    if not args.execute:
        parser.error("pass --execute to enable bounded network requests")
    if not 1 <= args.max_items <= 5:
        parser.error("max-items must be between 1 and 5")
    if args.mode != "preview" and not args.database_url:
        parser.error("ingest requires an explicit --database-url")
    if args.mode == "ingest-analyze" and (not args.allow_paid_model or
                                          not 1 <= args.max_model_calls <= 5):
        parser.error("ingest-analyze requires --allow-paid-model and 1-5 max-model-calls")
    spec = SOURCES[args.source]
    with httpx.Client(timeout=httpx.Timeout(35, connect=10), follow_redirects=False,
                      headers={"User-Agent": USER_AGENT}) as client:
        analyzer = None
        if args.mode == "ingest-analyze":
            base_url, api_key, model = load_local_credentials(args.env)
            if not model_listed(client, base_url, api_key, model):
                parser.error("configured model is not listed by the provider")
            analyzer = LiveAnalyzer(client, base_url, api_key, model)
        adapter = build_adapter(spec, client, max_items=args.max_items)
        if args.mode == "preview":
            candidates = adapter.candidates()
            result = {"source": spec.slug, "candidate_count": len(candidates),
                      "fetch_metrics": getattr(adapter, "diagnostics", {}),
                      "item_diagnostics": getattr(adapter, "item_diagnostics", []),
                      "body_status": {
                          "full_text": sum(bool(item.body) for item in candidates),
                          "abstract_only": sum(not item.body and bool(item.summary) for item in candidates),
                          "metadata_only": sum(not item.body and not item.summary for item in candidates),
                      }}
        else:
            engine = make_engine(args.database_url)
            try:
                with Session(engine) as session:
                    result = collect(session, spec, adapter)
                    if analyzer is not None:
                        result["processing"] = process_model_batch(
                            session, analyzer, max_calls=args.max_model_calls,
                            source_id=result["source_id"])
                        result = {**source_funnel(session, result["run_id"]),
                                  "processing": result["processing"]}
            finally:
                engine.dispose()
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
