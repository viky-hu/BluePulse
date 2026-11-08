"""Permission-bound article image proxy adapted from AIHOT media/imgproxy.ts.

AIHOT is MIT-licensed. Copyright (c) 2026 数字生命卡兹克.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
import time
from io import BytesIO
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from .publication import visible
from .source_images import approved_image_url as approved_image_url


LIFETIME_SECONDS = 900
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
RASTER_TYPES = {"PNG", "JPEG", "WEBP", "GIF"}


def public_media(article) -> list[dict]:
    if not article.source.media_allowed or not article.source.full_text_allowed or not visible(article):
        return []
    raw = getattr(article, "source_media", None) or []
    return [
        item for item in raw[:9]
        if isinstance(item, dict) and item.get("kind") == "image" and
        approved_image_url(item.get("url"), article.source.allowed_hosts)
    ]


def _signature(secret: str, article, index: int, expires: int, url: str) -> str:
    payload = f"{article.id}\n{article.revision}\n{index}\n{expires}\n{url}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def media_path(article, index: int, image: dict) -> str | None:
    secret = os.environ.get("BLUEPULSE_MEDIA_SECRET")
    if not secret:
        return None
    expires = (int(time.time()) // 60) * 60 + LIFETIME_SECONDS
    params = urlencode({"exp": expires, "sig": _signature(secret, article, index, expires, image["url"])})
    return f"/api/bluepulse/site/media/{article.id}/{index}?{params}"


def verified_media(article, index: int, expires: int, signature: str) -> str | None:
    secret = os.environ.get("BLUEPULSE_MEDIA_SECRET")
    now = int(time.time())
    if not secret or not now < expires <= now + LIFETIME_SECONDS or len(signature) != 64:
        return None
    images = public_media(article)
    if not 0 <= index < len(images):
        return None
    url = images[index]["url"]
    return url if hmac.compare_digest(_signature(secret, article, index, expires, url), signature) else None


def _pinned_origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        raise ValueError("invalid_image_origin")
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    for entry in addresses:
        address = ipaddress.ip_address(entry[4][0])
        if address.is_global and not address.is_multicast and not address.is_reserved:
            netloc = f"[{address}]" if address.version == 6 else str(address)
            return urlunsplit(("https", netloc, parts.path, parts.query, "")), host
    raise ValueError("image_origin_not_public")


def fetch_raster(url: str) -> bytes:
    """Fetch only an already verified origin, pinning its DNS answer through TLS."""
    from PIL import Image

    pinned, host = _pinned_origin(url)
    data = BytesIO()
    with httpx.Client(timeout=4, follow_redirects=False, trust_env=False) as client:
        request = client.build_request(
            "GET", pinned, headers={"Host": host, "Accept": "image/*", "Accept-Encoding": "identity"},
            extensions={"sni_hostname": host},
        )
        deadline = time.monotonic() + 4
        with client.send(request, stream=True) as response:
            response.raise_for_status()
            for chunk in response.iter_raw(chunk_size=64 * 1024):
                if data.tell() + len(chunk) > MAX_BYTES or time.monotonic() >= deadline:
                    raise ValueError("image_download_limit")
                data.write(chunk)
    data.seek(0)
    try:
        with Image.open(data, formats=sorted(RASTER_TYPES)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("image_pixel_limit")
            image.thumbnail((1600, 1600))
            result = BytesIO()
            image.convert("RGBA").save(result, format="WEBP", quality=86)
            return result.getvalue()
    except Image.DecompressionBombError:
        raise ValueError("image_pixel_limit") from None


def public_cover(article) -> dict | None:
    for index, image in enumerate(public_media(article)):
        path = media_path(article, index, image)
        if path:
            return {
                "url": path, "width": _dimension(image.get("width")),
                "height": _dimension(image.get("height")),
            }
    return None


def _dimension(value):
    return value if type(value) is int and value > 0 else None


def public_source_icon(source) -> str | None:
    # Source avatars fall back to initials until an approved icon is stored.
    return None
