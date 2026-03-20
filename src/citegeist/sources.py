from __future__ import annotations

import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


class SourceClient:
    def __init__(
        self,
        user_agent: str = "citegeist/0.1 (local research tool)",
        cache_dir: str | Path | None = None,
        fixtures_dir: str | Path | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else None

    def get_json(self, url: str) -> dict:
        cached = self._read_cached(url, "json")
        if cached is not None:
            return json.loads(cached)

        payload = self._fetch_bytes(url)
        self._write_cache(url, "json", payload)
        return json.loads(payload.decode("utf-8"))

    def get_text(self, url: str) -> str:
        cached = self._read_cached(url, "txt")
        if cached is not None:
            return self._decode_text(cached)

        payload = self._fetch_bytes(url)
        self._write_cache(url, "txt", payload)
        return self._decode_text(payload)

    def get_xml(self, url: str) -> ET.Element:
        cached = self._read_cached(url, "xml")
        if cached is not None:
            return ET.fromstring(cached)

        payload = self._fetch_bytes(url)
        self._write_cache(url, "xml", payload)
        return ET.fromstring(payload)

    def _fetch_bytes(self, url: str) -> bytes:
        with urllib.request.urlopen(self._request(url)) as response:
            return response.read()

    def _request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
            },
        )

    def _cache_key(self, url: str, suffix: str) -> str:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return f"{digest}.{suffix}"

    def _read_cached(self, url: str, suffix: str) -> bytes | None:
        for root in (self.fixtures_dir, self.cache_dir):
            if root is None:
                continue
            path = root / self._cache_key(url, suffix)
            if path.exists():
                return path.read_bytes()
        return None

    def _write_cache(self, url: str, suffix: str, payload: bytes) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / self._cache_key(url, suffix)
        path.write_bytes(payload)

    def _decode_text(self, payload: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "iso-8859-1", "latin-1"):
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="replace")
