import ssl
import threading
import urllib.error
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from citegeist.bibtex import BibEntry
from citegeist.cli import build_parser, main
from citegeist.discovery import search_material
from citegeist.identifiers import extract_doi, entry_identifiers
from citegeist.resolve import MetadataResolver, Resolution
from citegeist.sources import SourceClient
from citegeist.verify import BibliographyVerifier


@pytest.mark.parametrize('value', ['10.1234/example', 'doi:10.1234/example.', 'https://doi.org/10.1234%2Fexample', 'Smith (2020). Work (doi:10.1234/example).'])
def test_doi_text_goes_direct(value):
    def direct(doi):
        assert doi == '10.1234/example'
        return Resolution(BibEntry('article', 'resolved', {'doi': doi}), 'resolver', 'crossref')
    verifier = BibliographyVerifier(resolver=SimpleNamespace(resolve_doi=direct))
    assert verifier.verify_string(value).status == 'exact'


def test_balanced_doi_parentheses():
    assert extract_doi('doi:10.1234/abc(123).') == '10.1234/abc(123)'


@pytest.mark.parametrize('fields', [{'url': 'https://arxiv.org/pdf/2301.12345v2.pdf'}, {'archiveprefix': 'arXiv', 'eprint': '2301.12345v2'}, {'arxiv': '2301.12345v2'}])
def test_arxiv_bib_goes_direct(fields):
    def direct(value):
        assert value == '2301.12345v2'
        return Resolution(BibEntry('misc', 'resolved', {'arxiv': value}), 'resolver', 'arxiv')
    verifier = BibliographyVerifier(resolver=SimpleNamespace(resolve_arxiv=direct))
    assert verifier.verify_bib_entry(BibEntry('misc', 'input', fields)).status == 'exact'


def test_url_doi_field():
    assert entry_identifiers({'url': 'https://doi.org/10.1234/example'})[0] == '10.1234/example'


def test_arxiv_error_feed_is_not_exact():
    import xml.etree.ElementTree as ET
    resolver = MetadataResolver()
    resolver._safe_get_xml = lambda url: ET.fromstring('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/api/errors#incorrect_id_format</id><title>Error</title></entry></feed>')
    assert resolver.resolve_arxiv('2301.12345') is None


def test_tls_error_is_visible_without_retry(monkeypatch):
    calls = []
    def fail(request, **kwargs):
        calls.append(kwargs)
        raise urllib.error.URLError(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED'))
    monkeypatch.setattr('urllib.request.urlopen', fail)
    with pytest.raises(RuntimeError, match='CITEGEIST_CA_BUNDLE'):
        MetadataResolver(source_client=SourceClient()).resolve_doi('10.1234/example')
    assert len(calls) == 1
    assert calls[0]['timeout'] > 0


def test_explicit_ca_bundle(monkeypatch):
    contexts = []
    monkeypatch.setattr(ssl, 'create_default_context', lambda **kw: contexts.append(kw) or 'context')
    client = SourceClient(ca_bundle='/tmp/company.pem')
    assert contexts == [{'cafile': '/tmp/company.pem'}]
    assert client.ssl_context == 'context'


def test_searches_overlap_and_keep_order():
    barrier = threading.Barrier(4)
    def search(query, limit):
        barrier.wait(timeout=2)
        return []
    resolver = SimpleNamespace(**{'search_' + name: search for name in ['crossref', 'openalex', 'datacite', 'pubmed']})
    assert BibliographyVerifier(resolver=resolver).verify_string('a reference').status == 'not_found'


def test_cli_identifier_aliases():
    for flag in ['--doi', '--arxiv']:
        assert build_parser().parse_args(['verify', flag, 'value']).string == 'value'


def test_discovery_worldbank():
    client = SimpleNamespace(get_json=lambda url: {'documents': {'D1': {'display_title': 'Labor report', 'docdt': '2024-01-01', 'url': 'https://example.org/report'}, 'facets': {}}})
    entries = search_material('worldbank', 'labor', client=client)
    assert len(entries) == 1
    assert entries[0].fields['x_source'] == 'worldbank:D1'
    assert entries[0].fields['year'] == '2024'


def test_fred_uses_installer_key(monkeypatch):
    monkeypatch.delenv('FRED_API_KEY', raising=False)
    with pytest.raises(ValueError, match='FRED_API_KEY'):
        search_material('fred', 'inflation')
    monkeypatch.setenv('FRED_API_KEY', 'test-key')
    def fetch(url):
        assert parse_qs(urlsplit(url).query)['api_key'] == ['test-key']
        return {'seriess': [{'id': 'CPI', 'title': 'Consumer prices'}]}
    assert search_material('fred', 'inflation', client=SimpleNamespace(get_json=fetch))[0].fields['x_status'] == 'unverified'


def test_sources_visible_without_database(capsys):
    assert main(['sources']) == 0
    assert 'reliefweb' in capsys.readouterr().out


def test_cli_tls_failure_has_actionable_error(tmp_path, monkeypatch, capsys):
    from citegeist.sources import SourceTLSFailure
    def fail(*args, **kwargs):
        raise SourceTLSFailure('TLS failure: set CITEGEIST_CA_BUNDLE')
    monkeypatch.setattr(BibliographyVerifier, 'verify_string', fail)
    assert main(['--db', str(tmp_path / 'library.db'), 'verify', '--doi', '10.1234/test']) == 1
    output = capsys.readouterr()
    assert not output.out
    assert 'CITEGEIST_CA_BUNDLE' in output.err
