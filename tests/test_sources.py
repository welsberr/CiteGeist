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
