from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from .bibtex import BibEntry
from .sources import SourceClient

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "mods": "http://www.loc.gov/mods/v3",
}


@dataclass(slots=True)
class HarvestResult:
    base_url: str
    identifier: str
    entry: BibEntry


@dataclass(slots=True)
class OaiSet:
    set_spec: str
    set_name: str
    set_description: str = ""


@dataclass(slots=True)
class OaiMetadataFormat:
    metadata_prefix: str
    schema: str
    metadata_namespace: str


class OaiPmhHarvester:
    def __init__(self, source_client: SourceClient | None = None) -> None:
        self.source_client = source_client or SourceClient()

    def identify(self, base_url: str) -> dict[str, str]:
        root = self.source_client.try_get_xml(f"{base_url}?{urlencode({'verb': 'Identify'})}")
        if root is None:
            return {}
        identify = root.find(".//oai:Identify", NS)
        if identify is None:
            return {}
        payload: dict[str, str] = {}
        for field_name in (
            "repositoryName",
            "baseURL",
            "protocolVersion",
            "adminEmail",
            "earliestDatestamp",
            "deletedRecord",
            "granularity",
        ):
            payload[field_name] = _node_text(identify.find(f"oai:{field_name}", NS))
        return payload

    def list_sets(self, base_url: str) -> list[OaiSet]:
        root = self.source_client.try_get_xml(f"{base_url}?{urlencode({'verb': 'ListSets'})}")
        if root is None:
            return []
        sets = root.findall(".//oai:set", NS)
        results: list[OaiSet] = []
        for node in sets:
            results.append(
                OaiSet(
                    set_spec=_node_text(node.find("oai:setSpec", NS)),
                    set_name=_node_text(node.find("oai:setName", NS)),
                    set_description=_flatten_set_description(node.find("oai:setDescription", NS)),
                )
            )
        return results

    def list_metadata_formats(self, base_url: str, identifier: str | None = None) -> list[OaiMetadataFormat]:
        params = {"verb": "ListMetadataFormats"}
        if identifier:
            params["identifier"] = identifier
        root = self.source_client.try_get_xml(f"{base_url}?{urlencode(params)}")
        if root is None:
            return []
        formats = root.findall(".//oai:metadataFormat", NS)
        results: list[OaiMetadataFormat] = []
        for node in formats:
            results.append(
                OaiMetadataFormat(
                    metadata_prefix=_node_text(node.find("oai:metadataPrefix", NS)),
                    schema=_node_text(node.find("oai:schema", NS)),
                    metadata_namespace=_node_text(node.find("oai:metadataNamespace", NS)),
                )
            )
        return results

    def list_records(
        self,
        base_url: str,
        metadata_prefix: str = "oai_dc",
        set_spec: str | None = None,
        date_from: str | None = None,
        date_until: str | None = None,
        limit: int | None = None,
    ) -> list[HarvestResult]:
        results: list[HarvestResult] = []
        params = {"verb": "ListRecords", "metadataPrefix": metadata_prefix}
        if set_spec:
            params["set"] = set_spec
        if date_from:
            params["from"] = date_from
        if date_until:
            params["until"] = date_until

        ordinal = 1
        next_url = f"{base_url}?{urlencode(params)}"
        while next_url:
            root = self.source_client.try_get_xml(next_url)
            if root is None:
                break
            records = root.findall(".//oai:record", NS)
            for record in records:
                parsed = self._record_to_result(base_url, record, ordinal)
                ordinal += 1
                if parsed is not None:
                    results.append(parsed)
                if limit is not None and len(results) >= limit:
                    return results
            next_url = self._resumption_url(base_url, root)
        return results

    def get_record(
        self,
        base_url: str,
        identifier: str,
        metadata_prefix: str = "oai_dc",
    ) -> HarvestResult | None:
        params = {
            "verb": "GetRecord",
            "metadataPrefix": metadata_prefix,
            "identifier": identifier,
        }
        root = self.source_client.try_get_xml(f"{base_url}?{urlencode(params)}")
        if root is None:
            return None
        record = root.find(".//oai:record", NS)
        if record is None:
            return None
        return self._record_to_result(base_url, record, 1)

    def _record_to_result(self, base_url: str, record: ET.Element, ordinal: int) -> HarvestResult | None:
        identifier = _node_text(record.find("./oai:header/oai:identifier", NS))
        metadata_node = record.find("./oai:metadata/*", NS)
        if metadata_node is None or not identifier:
            return None

        entry = _metadata_node_to_entry(base_url, identifier, metadata_node, ordinal)
        return HarvestResult(base_url=base_url, identifier=identifier, entry=entry)

    def _resumption_url(self, base_url: str, root: ET.Element) -> str | None:
        token = _node_text(root.find(".//oai:resumptionToken", NS))
        if not token:
            return None
        return f"{base_url}?{urlencode({'verb': 'ListRecords', 'resumptionToken': token})}"


def _oai_dc_to_entry(base_url: str, identifier: str, metadata: ET.Element, ordinal: int) -> BibEntry:
    titles = _all_text(metadata.findall("dc:title", NS))
    creators = _all_text(metadata.findall("dc:creator", NS))
    dates = _all_text(metadata.findall("dc:date", NS))
    descriptions = _all_text(metadata.findall("dc:description", NS))
    identifiers = _all_text(metadata.findall("dc:identifier", NS))
    publishers = _all_text(metadata.findall("dc:publisher", NS))
    types = [value.lower() for value in _all_text(metadata.findall("dc:type", NS))]

    title = titles[0] if titles else "Untitled record"
    year = _first_year(dates)
    entry_type = _guess_oai_entry_type(types)

    fields: dict[str, str] = {
        "title": title,
        "oai": identifier,
        "url": _best_identifier_url(identifiers) or f"{base_url}?verb=GetRecord&identifier={identifier}&metadataPrefix=oai_dc",
        "note": "harvested_from = {oai_pmh}",
    }
    if creators:
        fields["author"] = " and ".join(creators)
    if year:
        fields["year"] = year
    if descriptions:
        fields["abstract"] = descriptions[0]
    if publishers:
        fields["publisher"] = publishers[0]

    citation_key = _oai_citation_key(creators, year, title, ordinal)
    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _mods_to_entry(base_url: str, identifier: str, metadata: ET.Element, ordinal: int) -> BibEntry:
    title = _node_text(metadata.find(".//mods:titleInfo/mods:title", NS)) or "Untitled record"
    sub_title = _node_text(metadata.find(".//mods:titleInfo/mods:subTitle", NS))
    if sub_title:
        title = f"{title}: {sub_title}"

    creators: list[str] = []
    for name in metadata.findall(".//mods:name", NS):
        role_terms = [term.text or "" for term in name.findall(".//mods:roleTerm", NS)]
        if role_terms and not any(term.lower() == "author" for term in role_terms):
            continue
        parts = [_node_text(part) for part in name.findall("./mods:namePart", NS)]
        parts = [part for part in parts if part]
        if parts:
            creators.append(", ".join(parts) if len(parts) == 2 else " ".join(parts))

    year = ""
    for date_node in metadata.findall(".//mods:originInfo/mods:dateIssued", NS):
        text = _node_text(date_node)
        if len(text) >= 4 and text[:4].isdigit():
            year = text[:4]
            break

    publisher = _node_text(metadata.find(".//mods:originInfo/mods:publisher", NS))
    abstract = _node_text(metadata.find(".//mods:abstract", NS))
    genre = _node_text(metadata.find(".//mods:genre", NS)).lower()
    related_title = _node_text(metadata.find(".//mods:relatedItem/mods:titleInfo/mods:title", NS))
    url = _node_text(metadata.find(".//mods:location/mods:url", NS))

    entry_type = "phdthesis" if "thesis" in genre or "dissertation" in genre else "misc"
    if not entry_type == "phdthesis":
        if related_title:
            entry_type = "article"

    fields: dict[str, str] = {
        "title": title,
        "oai": identifier,
        "url": url or f"{base_url}?verb=GetRecord&identifier={identifier}&metadataPrefix=mods",
        "note": "harvested_from = {oai_pmh_mods}",
    }
    if creators:
        fields["author"] = " and ".join(creators)
    if year:
        fields["year"] = year
    if publisher:
        fields["publisher"] = publisher
    if abstract:
        fields["abstract"] = abstract
    if related_title:
        fields["journal"] = related_title

    citation_key = _oai_citation_key(creators, year, title, ordinal)
    return BibEntry(entry_type=entry_type, citation_key=citation_key, fields=fields)


def _metadata_node_to_entry(base_url: str, identifier: str, metadata: ET.Element, ordinal: int) -> BibEntry:
    if metadata.tag.endswith("dc"):
        return _oai_dc_to_entry(base_url, identifier, metadata, ordinal)
    if metadata.tag.endswith("mods"):
        return _mods_to_entry(base_url, identifier, metadata, ordinal)
    return BibEntry(
        entry_type="misc",
        citation_key=_oai_citation_key([], "", identifier, ordinal),
        fields={
            "title": identifier,
            "oai": identifier,
            "url": f"{base_url}?verb=GetRecord&identifier={identifier}",
            "note": f"unsupported_oai_metadata = {{{metadata.tag}}}",
        },
    )


def _node_text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return " ".join(node.text.split())


def _all_text(nodes: list[ET.Element]) -> list[str]:
    values = []
    for node in nodes:
        value = _node_text(node)
        if value:
            values.append(value)
    return values


def _first_year(dates: list[str]) -> str:
    for date in dates:
        if len(date) >= 4 and date[:4].isdigit():
            return date[:4]
    return ""


def _guess_oai_entry_type(types: list[str]) -> str:
    joined = " ".join(types)
    if "thesis" in joined or "dissertation" in joined:
        return "phdthesis"
    if "article" in joined:
        return "article"
    if "book" in joined:
        return "book"
    return "misc"


def _best_identifier_url(identifiers: list[str]) -> str:
    for identifier in identifiers:
        if identifier.startswith("http://") or identifier.startswith("https://"):
            return identifier
    return ""


def _oai_citation_key(creators: list[str], year: str, title: str, ordinal: int) -> str:
    author = creators[0] if creators else "oai"
    family = author.split(",")[0] if "," in author else author.split()[-1]
    family = "".join(ch for ch in family.lower() if ch.isalnum()) or "oai"
    first_word = "".join(ch for ch in title.split()[0].lower() if ch.isalnum()) if title.split() else "untitled"
    return f"{family}{year or 'nd'}{first_word}{ordinal}"


def _flatten_set_description(node: ET.Element | None) -> str:
    if node is None:
        return ""
    parts = []
    for child in node.iter():
        if child.text and child.text.strip():
            parts.append(" ".join(child.text.split()))
    return " ".join(parts)
