from citegeist import OaiPmhHarvester, parse_bibtex
from citegeist.cli import main


OAI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:example.edu:123</identifier>
      </header>
      <metadata>
        <oai_dc:dc>
          <dc:title>Thesis Metadata Harvesting</dc:title>
          <dc:creator>Doe, Jane</dc:creator>
          <dc:date>2023-05-01</dc:date>
          <dc:description>A dissertation about repository harvesting.</dc:description>
          <dc:identifier>https://example.edu/items/123</dc:identifier>
          <dc:publisher>Example University</dc:publisher>
          <dc:type>Text</dc:type>
          <dc:type>Dissertation</dc:type>
        </oai_dc:dc>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>
"""

OAI_XML_PAGE_1 = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:example.edu:123</identifier>
      </header>
      <metadata>
        <oai_dc:dc>
          <dc:title>First Harvested Thesis</dc:title>
          <dc:creator>Doe, Jane</dc:creator>
          <dc:date>2023-05-01</dc:date>
          <dc:type>Dissertation</dc:type>
        </oai_dc:dc>
      </metadata>
    </record>
    <resumptionToken>TOKEN123</resumptionToken>
  </ListRecords>
</OAI-PMH>
"""

OAI_XML_PAGE_2 = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:example.edu:456</identifier>
      </header>
      <metadata>
        <oai_dc:dc>
          <dc:title>Second Harvested Thesis</dc:title>
          <dc:creator>Smith, John</dc:creator>
          <dc:date>2022-05-01</dc:date>
          <dc:type>Dissertation</dc:type>
        </oai_dc:dc>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>
"""

OAI_IDENTIFY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <Identify>
    <repositoryName>Example Repository</repositoryName>
    <baseURL>https://example.edu/oai</baseURL>
    <protocolVersion>2.0</protocolVersion>
    <adminEmail>repo@example.edu</adminEmail>
    <earliestDatestamp>2001-01-01</earliestDatestamp>
    <deletedRecord>persistent</deletedRecord>
    <granularity>YYYY-MM-DD</granularity>
  </Identify>
</OAI-PMH>
"""

OAI_LISTSETS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListSets>
    <set>
      <setSpec>theses</setSpec>
      <setName>Theses and Dissertations</setName>
      <setDescription>
        <description>This set contains graduate theses.</description>
      </setDescription>
    </set>
  </ListSets>
</OAI-PMH>
"""

OAI_METADATA_FORMATS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <ListMetadataFormats>
    <metadataFormat>
      <metadataPrefix>oai_dc</metadataPrefix>
      <schema>http://www.openarchives.org/OAI/2.0/oai_dc.xsd</schema>
      <metadataNamespace>http://www.openarchives.org/OAI/2.0/oai_dc/</metadataNamespace>
    </metadataFormat>
    <metadataFormat>
      <metadataPrefix>mods</metadataPrefix>
      <schema>http://www.loc.gov/standards/mods/v3/mods-3-7.xsd</schema>
      <metadataNamespace>http://www.loc.gov/mods/v3</metadataNamespace>
    </metadataFormat>
  </ListMetadataFormats>
</OAI-PMH>
"""

OAI_MODS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:mods="http://www.loc.gov/mods/v3">
  <ListRecords>
    <record>
      <header>
        <identifier>oai:example.edu:mods123</identifier>
      </header>
      <metadata>
        <mods:mods>
          <mods:titleInfo>
            <mods:title>MODS Thesis Title</mods:title>
          </mods:titleInfo>
          <mods:name>
            <mods:namePart>Doe</mods:namePart>
            <mods:namePart>Jane</mods:namePart>
            <mods:role>
              <mods:roleTerm>author</mods:roleTerm>
            </mods:role>
          </mods:name>
          <mods:originInfo>
            <mods:publisher>Example University</mods:publisher>
            <mods:dateIssued>2022</mods:dateIssued>
          </mods:originInfo>
          <mods:genre>dissertation</mods:genre>
          <mods:abstract>MODS abstract text.</mods:abstract>
          <mods:location>
            <mods:url>https://example.edu/mods123</mods:url>
          </mods:location>
        </mods:mods>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>
"""


def test_oai_harvester_maps_dublin_core_to_bibentry():
    harvester = OaiPmhHarvester()
    harvester.source_client.get_xml = lambda _url: __import__("xml.etree.ElementTree").etree.ElementTree.fromstring(OAI_XML)  # type: ignore[method-assign]

    results = harvester.list_records("https://example.edu/oai")

    assert len(results) == 1
    entry = results[0].entry
    assert entry.entry_type == "phdthesis"
    assert entry.fields["title"] == "Thesis Metadata Harvesting"
    assert entry.fields["author"] == "Doe, Jane"
    assert entry.fields["oai"] == "oai:example.edu:123"


def test_oai_harvester_follows_resumption_tokens():
    harvester = OaiPmhHarvester()
    from xml.etree import ElementTree as ET

    payloads = iter([ET.fromstring(OAI_XML_PAGE_1), ET.fromstring(OAI_XML_PAGE_2)])
    harvester.source_client.get_xml = lambda _url: next(payloads)  # type: ignore[method-assign]

    results = harvester.list_records("https://example.edu/oai")

    assert [result.identifier for result in results] == [
        "oai:example.edu:123",
        "oai:example.edu:456",
    ]
    assert [result.entry.citation_key for result in results] == [
        "doe2023first1",
        "smith2022second2",
    ]


def test_oai_harvester_passes_date_filters():
    harvester = OaiPmhHarvester()
    seen_urls: list[str] = []
    from xml.etree import ElementTree as ET

    def fake_get_xml(url: str):
        seen_urls.append(url)
        return ET.fromstring(OAI_XML)

    harvester.source_client.get_xml = fake_get_xml  # type: ignore[method-assign]

    harvester.list_records(
        "https://example.edu/oai",
        date_from="2023-01-01",
        date_until="2023-12-31",
        limit=1,
    )

    assert "from=2023-01-01" in seen_urls[0]
    assert "until=2023-12-31" in seen_urls[0]


def test_oai_harvester_maps_mods_records():
    harvester = OaiPmhHarvester()
    from xml.etree import ElementTree as ET

    harvester.source_client.get_xml = lambda _url: ET.fromstring(OAI_MODS_XML)  # type: ignore[method-assign]

    results = harvester.list_records("https://example.edu/oai", metadata_prefix="mods")

    assert len(results) == 1
    entry = results[0].entry
    assert entry.entry_type == "phdthesis"
    assert entry.fields["title"] == "MODS Thesis Title"
    assert entry.fields["author"] == "Doe, Jane"
    assert entry.fields["publisher"] == "Example University"
    assert entry.fields["abstract"] == "MODS abstract text."


def test_oai_harvester_can_identify_repository_and_list_sets():
    harvester = OaiPmhHarvester()
    from xml.etree import ElementTree as ET

    payloads = iter(
        [ET.fromstring(OAI_IDENTIFY_XML), ET.fromstring(OAI_LISTSETS_XML), ET.fromstring(OAI_METADATA_FORMATS_XML)]
    )
    harvester.source_client.get_xml = lambda _url: next(payloads)  # type: ignore[method-assign]

    identify = harvester.identify("https://example.edu/oai")
    sets = harvester.list_sets("https://example.edu/oai")
    formats = harvester.list_metadata_formats("https://example.edu/oai")

    assert identify["repositoryName"] == "Example Repository"
    assert identify["granularity"] == "YYYY-MM-DD"
    assert sets[0].set_spec == "theses"
    assert sets[0].set_name == "Theses and Dissertations"
    assert "graduate theses" in sets[0].set_description
    assert [item.metadata_prefix for item in formats] == ["oai_dc", "mods"]


def test_harvest_oai_cli_ingests_records(tmp_path):
    from unittest.mock import patch

    database = tmp_path / "library.sqlite3"
    harvester = OaiPmhHarvester()
    from xml.etree import ElementTree as ET

    harvester.source_client.get_xml = lambda _url: ET.fromstring(OAI_XML)  # type: ignore[method-assign]
    harvested = harvester.list_records("https://example.edu/oai")

    with patch("citegeist.cli.OaiPmhHarvester.list_records") as mocked_list:
        mocked_list.return_value = harvested

        exit_code = main(
            [
                "--db",
                str(database),
                "harvest-oai",
                "https://example.edu/oai",
                "--metadata-prefix",
                "oai_dc",
                "--from",
                "2023-01-01",
                "--until",
                "2023-12-31",
                "--limit",
                "5",
            ]
        )

    assert exit_code == 0

    from citegeist.storage import BibliographyStore

    store = BibliographyStore(database)
    try:
        entry = store.list_entries(limit=10)[0]
        assert entry["citation_key"] == "doe2023thesis1"
        bibtex = store.get_entry_bibtex("doe2023thesis1")
        parsed = parse_bibtex(bibtex or "")
        assert parsed[0].fields["oai"] == "oai:example.edu:123"
    finally:
        store.close()
