"""Collect image references only inside a verified article body."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit


def approved_image_url(url: object, allowed_hosts: list[str]) -> bool:
    if not isinstance(url, str) or not url or len(url) > 2048 or "\\" in url:
        return False
    if any(ord(char) <= 32 or ord(char) == 127 for char in url):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname in allowed_hosts and
                parts.port in (None, 443) and parts.username is None and
                parts.password is None and not parts.fragment)
    except ValueError:
        return False


def _dimension(value):
    return int(value) if value and re.fullmatch(r"[1-9][0-9]{0,4}", value) else None


class ArticleImages:
    def __init__(self, url, host):
        self.url = url
        self.host = host
        self.items = {}

    def add(self, attrs):
        if len(self.items) >= 9:
            return
        for attribute in ("src", "data-src"):
            raw = attrs.get(attribute)
            if not raw:
                continue
            try:
                url = urljoin(self.url, raw)
            except ValueError:
                continue
            if approved_image_url(url, [self.host]):
                self.items.setdefault(url, {
                    "kind": "image", "url": url, "alt": (attrs.get("alt") or "").strip()[:250] or None,
                    "width": _dimension(attrs.get("width")), "height": _dimension(attrs.get("height")),
                })
                return

    def permitted(self, policy, user_agent):
        return [item for url, item in self.items.items() if policy.can_fetch(user_agent, url)] or None
