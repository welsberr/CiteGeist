import http.client
from pathlib import Path
import urllib.error

from citegeist.sources import SourceClient


def test_source_client_reads_fixture_before_network(tmp_path: Path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()

    client = SourceClient(cache_dir=tmp_path / "cache", fixtures_dir=fixtures_dir)
    url = "https://api.crossref.org/works/10.1000/example"
    fixture_path = fixtures_dir / client._cache_key(url, "json")  # noqa: SLF001
    fixture_path.write_text('{"message": {"DOI": "10.1000/example"}}', encoding="utf-8")

    payload = client.get_json(url)

    assert payload["message"]["DOI"] == "10.1000/example"


def test_source_client_writes_cache_after_fetch(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    client = SourceClient(cache_dir=cache_dir)
    url = "https://example.org/test"

    client._fetch_bytes = lambda _url: b'{"ok": true}'  # type: ignore[method-assign]

    payload = client.get_json(url)

    assert payload["ok"] is True
    assert any(cache_dir.iterdir())


def test_source_client_falls_back_to_latin1_for_text(tmp_path: Path):
    client = SourceClient(cache_dir=tmp_path / "cache")
    url = "https://example.org/latin1"

    client._fetch_bytes = lambda _url: "café".encode("iso-8859-1")  # type: ignore[method-assign]

    payload = client.get_text(url)

    assert payload == "café"


def test_source_client_try_get_json_returns_none_on_http_error(tmp_path: Path):
    client = SourceClient(cache_dir=tmp_path / "cache")

    def raise_404(_url: str):
        raise urllib.error.HTTPError(_url, 404, "Not Found", hdrs=None, fp=None)

    client._fetch_bytes = raise_404  # type: ignore[method-assign]

    assert client.try_get_json("https://example.org/missing") is None


def test_source_client_retries_remote_disconnects(tmp_path: Path):
    client = SourceClient(cache_dir=tmp_path / "cache", max_retries=2, retry_backoff_seconds=0.0)
    attempts = {"count": 0}

    def flaky_fetch(_url: str) -> bytes:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise http.client.RemoteDisconnected("closed")
        return b'{"ok": true}'

    client._fetch_bytes = SourceClient._fetch_bytes.__get__(client, SourceClient)  # type: ignore[method-assign]
    client._request = lambda url: url  # type: ignore[method-assign]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return flaky_fetch("https://example.org/test")

    import urllib.request

    original_urlopen = urllib.request.urlopen
    urllib.request.urlopen = lambda _request: FakeResponse()  # type: ignore[assignment]
    try:
        payload = client.get_json("https://example.org/test")
    finally:
        urllib.request.urlopen = original_urlopen  # type: ignore[assignment]

    assert payload["ok"] is True
    assert attempts["count"] == 3
