"""Retain public listing and detail evidence without invoking production source parsers."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from .ccgp_source import USER_AGENT
from .models import now_utc
from .source_collection import SOURCES

MAX_RESPONSE_BYTES = 5_000_000
SPF_ARCHIVE = "https://www.police.gov.sg/api/GetLifeArticles"
CCGP_CATEGORIES = ("gkzb", "zbgg", "cjgg", "gzgg", "fblbgg", "jzxcs", "jzxtpgg", "xjgg", "qtgg")
GOVUK_API = ("https://www.gov.uk/api/search.json?filter_organisations=home-office&order=-public_timestamp"
             "&count=100&fields=title,description,link,public_timestamp,content_store_document_type")


def official_entries(day):
    """Seed from first-party catalogs. Use an explicit plan to add archive pages and reviewed originals."""
    day = day.isoformat()
    entries = {
        "govuk": [f"{GOVUK_API}&filter_public_timestamp=from:{day}"],
        "ccgp-policing-tech": [f"https://www.ccgp.gov.cn/cggg/{level}/{category}/"
                             for level in ("zygg", "dfgg") for category in CCGP_CATEGORIES],
        "htx-news": ["https://www.htx.gov.sg/HTXInterface/ArticleListing/GetNewsAndEventsListing"
                     "?type=News&keyword=&topic=all&dateFrom=&dateTo=&page=1"],
        "police-science": ["https://science.police.uk/news-and-events/news/", "https://science.police.uk/sitemap.xml"],
        "npcc": ["https://news.npcc.police.uk/releases"],
        "jiangsu-police": [f"https://gat.jiangsu.gov.cn/col/col{cat}/index.html" for cat in (6372, 89895)],
        "police-digital-service": ["https://pds.police.uk/welcome/blog/",
                                   f"https://pds.police.uk/wp-json/wp/v2/posts?after={day}T00:00:00&per_page=50"],
        "biometric-update-law-enforcement": ["https://www.biometricupdate.com/biometric-news/law-enforcement",
                                            "https://www.biometricupdate.com/biometric-news/law-enforcement/feed"],
        "statescoop-law-enforcement-tech": [
            f"https://statescoop.com/wp-json/wp/v2/posts?tags={tag}&per_page=20&_fields=link,date,date_gmt,title,excerpt"
            for tag in (14, 25503)],
        "europol-news": ["https://www.europol.europa.eu/media-press/newsroom",
                         "https://www.europol.europa.eu/media-press/newsroom?page=2",
                         "https://www.europol.europa.eu/cms/api/rss/news"],
        "spf-police-life": ["https://www.police.gov.sg/Media-Hub/Police-Life", SPF_ARCHIVE],
    }
    for topic, segment, ids in (
        ("public-safety", "Public%20safety", (249461, 249331, 249316)),
        ("forensic-science", "forensic%20science", (248616,)),
        ("information-technology", "information%20technology", (249421,)),
        ("standards", "standards", (249341, 249391, 249371)),
    ):
        entries[f"nist-{topic}"] = [f"https://www.nist.gov/news-events/{segment}/rss.xml",
                                   *(f"https://www.nist.gov/news-events/news-updates/topic/{id}" for id in ids)]
    return [{"source": slug, "url": url, **({"method": "POST"} if url == SPF_ARCHIVE else {})}
            for slug, urls in entries.items() for url in urls]


def _official_host(slug, url):
    spec = SOURCES[slug]
    parsed = urlsplit(url)
    host = parsed.hostname
    source_host = spec.host.removeprefix("www.")
    if (parsed.scheme != "https" or not host or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment
            or host != source_host and not host.endswith("." + source_host)):
        raise ValueError("The evidence URL must use the listed source's official HTTPS host")
    return host


def _robots(client, host, sleep):
    url = f"https://{host}/robots.txt"
    parser = RobotFileParser()
    for hop in range(7):
        with client.stream("GET", url, follow_redirects=False) as response:
            status = response.status_code
            if status == 404:
                parser.parse([])
                return parser
            if response.is_redirect:
                target = response.headers.get("Location")
                if not target or urljoin(url, target) != url or host != "science.police.uk":
                    raise ValueError(f"robots_redirect_{status}")
                if hop >= 5:
                    # RFC 9309 allows a robots file beyond five redirects to be treated as unavailable.
                    parser.parse([])
                    return parser
                sleep(1.0)
                continue
            response.raise_for_status()
            parser.parse(_read(response, 512_000).decode("utf-8-sig", "replace").splitlines())
            return parser
    raise ValueError("robots_redirect_limit")


def _read(response, limit):
    data = bytearray()
    for chunk in response.iter_bytes():
        if len(data) + len(chunk) > limit:
            raise ValueError("body_limit")
        data.extend(chunk)
    return bytes(data)


def capture(client, plan, output, *, sleep=time.sleep):
    output.mkdir(parents=True, exist_ok=True)
    urls = [(row["source"], row["url"], row.get("method", "GET")) for row in plan]
    validated = []
    for slug, url, method in urls:
        if method != "GET" and (method != "POST" or url != SPF_ARCHIVE or slug != "spf-police-life"):
            raise ValueError("POST is supported only for the official public Police Life archive")
        validated.append((slug, url, method, _official_host(slug, url)))
    rows, policies, blocked = [], {}, set()
    journal = output / "pages.jsonl"
    with journal.open("x", encoding="utf-8") as stream:
        for source, url, method, host in validated:
            row = {"source": source, "url": url, "method": method, "captured_at": now_utc().isoformat()}
            try:
                if host not in policies:
                    try:
                        policies[host] = _robots(client, host, sleep)
                    except (httpx.HTTPError, ValueError) as error:
                        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else str(error)
                        policies[host] = f"robots_unavailable: {status}"
                policy = policies[host]
                if isinstance(policy, str):
                    row["error"] = policy
                elif host in blocked:
                    row["error"] = "host_throttled"
                elif not policy.can_fetch(USER_AGENT, url):
                    row["error"] = "robots_disallowed"
                else:
                    sleep(max(1.0, policy.crawl_delay(USER_AGENT) or 0))
                    options = {"json": {}} if method == "POST" else {}
                    with client.stream(method, url, follow_redirects=False, **options) as response:
                        row.update(status=response.status_code, content_type=response.headers.get("Content-Type"),
                                   retry_after=response.headers.get("Retry-After"),
                                   location=response.headers.get("Location"))
                        if response.status_code in (403, 429) or row["retry_after"]:
                            blocked.add(host)
                        if response.status_code == 200:
                            raw = _read(response, MAX_RESPONSE_BYTES)
                            digest = hashlib.sha256(raw).hexdigest()
                            name = f"{digest}.raw"
                            raw_path = output / name
                            if not raw_path.exists():
                                raw_path.write_bytes(raw)
                            row.update(file=name, sha256=digest, length=len(raw))
            except (httpx.HTTPError, ValueError) as error:
                row["error"] = str(error)
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
    return rows


def main(argv=None):
    from datetime import date, timedelta

    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--plan", type=Path, help="JSON list of official public requests")
    inputs.add_argument("--from-date", type=date.fromisoformat, help="Seed all configured sources")
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args(argv)
    plan = (json.loads(args.plan.read_text(encoding="utf-8")) if args.plan
            else official_entries(args.from_date - timedelta(days=1)))
    with httpx.Client(headers={"User-Agent": USER_AGENT},
                      timeout=httpx.Timeout(20, connect=8), follow_redirects=False) as client:
        rows = capture(client, plan, args.output)
    (args.output / "pages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print(json.dumps({"requests": len(rows), "captured": sum("sha256" in row for row in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
