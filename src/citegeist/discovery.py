"""Explicit discovery of reports and economic series; results remain unverified."""
import os
from urllib.parse import urlencode

from .bibtex import BibEntry
from .sources import SourceClient


def search_material(source: str, query: str, limit: int = 10, client=None) -> list[BibEntry]:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    client = client or SourceClient()
    if source == "worldbank":
        params = {"format": "json", "qterm": query, "rows": limit,
                  "fl": "display_title,docdt,docty,authr,repnb,pdfurl"}
        payload = client.get_json("https://search.worldbank.org/api/v3/wds?" + urlencode(params))
        records = payload.get("documents", {})
        entries = []
        for key, record in records.items():
            if not isinstance(record, dict):
                continue
            title = record.get("display_title") or record.get("title") or record.get("repnb")
            if not title:
                continue
            fields = {"title": title, "institution": "{World Bank}",
                      "url": record.get("url", ""), "year": str(record.get("docdt", ""))[:4],
                      "number": record.get("repnb", ""), "x_source": f"worldbank:{key}",
                      "x_status": "unverified"}
            entries.append(BibEntry("techreport", f"worldbank-{key}", {k: str(v) for k,v in fields.items() if v}))
        return entries[:limit]
    if source == "fred":
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            raise ValueError("FRED requires your own FRED_API_KEY")
        params = {"api_key": api_key, "file_type": "json", "search_text": query, "limit": limit}
        payload = client.get_json("https://api.stlouisfed.org/fred/series/search?" + urlencode(params))
        return [BibEntry("misc", "fred-" + record["id"], {
            "title": record["title"], "url": "https://fred.stlouisfed.org/series/" + record["id"],
            "publisher": "{Federal Reserve Bank of St. Louis}", "type": "Economic data series",
            "x_source": "fred:" + record["id"], "x_status": "unverified",
            "note": "Series metadata; cite the data vintage and original producer when using observations.",
        }) for record in payload.get("seriess", [])][:limit]
    raise ValueError(f"Unsupported discovery source: {source}")
