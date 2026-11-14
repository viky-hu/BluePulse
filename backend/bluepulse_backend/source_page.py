"""Robots and diagnostic helpers for independently queued source pages."""
from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .ccgp_source import USER_AGENT
from .live_sources import SourceFetchError


class SourcePageReader:
    def __init__(self, http, listing, sleeper, *, allow_missing_robots=False,
                 excessive_delay="robots_disallowed_or_delayed", denied_listing="robots_disallowed_or_delayed"):
        self.http, self.listing, self.sleeper = http, listing, sleeper
        self.allow_missing_robots = allow_missing_robots
        self.excessive_delay = excessive_delay
        self.denied_listing = denied_listing
        self.robots_missing = False
        self.policy: RobotFileParser | None = None
        self.delay = 1.0

    def refresh(self) -> None:
        self.policy = None
        self.robots_missing = False

    def prepare(self) -> RobotFileParser:
        if self.policy is None:
            host = urlsplit(self.listing).hostname
            try:
                robots = self.http.get(f"https://{host}/robots.txt", accept="text/plain")
            except SourceFetchError as exc:
                if not self.allow_missing_robots or exc.code != "http_404":
                    raise
                self.robots_missing = True
                robots = b""
            policy = RobotFileParser()
            policy.parse(robots.decode("utf-8-sig", "replace").splitlines())
            delay = policy.crawl_delay(USER_AGENT) or 0
            if delay > 10:
                raise SourceFetchError(self.excessive_delay)
            self.delay = max(1.0, float(delay))
            self.policy = policy
        return self.policy

    def get(self, url: str, accept: str) -> bytes:
        self._before_request(url)
        return self.http.get(url, accept=accept)

    def post_json(self, url: str, payload: dict) -> bytes:
        self._before_request(url)
        return self.http.post_json(url, payload)

    def _before_request(self, url: str) -> None:
        if not self.prepare().can_fetch(USER_AGENT, url):
            raise SourceFetchError(self.denied_listing if url == self.listing else "robots_disallowed")
        if getattr(self.http.client, "pulse_host_pace", None):
            self.http.delay_seconds = max(self.http.delay_seconds, self.delay)
        else:
            self.sleeper(self.delay)


class IncompleteArticle(SourceFetchError):
    def __init__(self, body_chars: int):
        super().__init__("incomplete_article")
        self.body_chars = body_chars


def bounded_details(candidates, fetch_detail, diagnostics, item_diagnostics=None):
    results = []
    for candidate in candidates:
        try:
            results.append(fetch_detail(candidate))
        except SourceFetchError as exc:
            if exc.code in {"http_403", "http_429", "robots_disallowed"}:
                raise
            diagnostics["detail_failed"] += 1
            if item_diagnostics is not None:
                status = {"url": candidate.url, "status": exc.code}
                if isinstance(exc, IncompleteArticle):
                    status["body_chars"] = exc.body_chars
                item_diagnostics.append(status)
    if not results and diagnostics["detail_failed"]:
        raise SourceFetchError("all_details_failed")
    return results
