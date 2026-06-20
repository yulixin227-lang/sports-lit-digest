from __future__ import annotations

import os
import urllib.parse
from typing import Any

from .utils import http_get_json, normalize_doi


SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper"
FIELDS = ",".join(
    [
        "title",
        "abstract",
        "venue",
        "year",
        "citationCount",
        "influentialCitationCount",
        "authors",
        "url",
        "externalIds",
        "publicationDate",
        "publicationTypes",
        "journal",
    ]
)


def enrich_with_semantic_scholar(
    papers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"x-api-key": api_key} if api_key else None

    for paper in papers:
        identifier = _paper_identifier(paper)
        if not identifier:
            continue
        try:
            url = f"{SEMANTIC_SCHOLAR_URL}/{urllib.parse.quote(identifier, safe=':')}"
            data = http_get_json(url, params={"fields": FIELDS}, headers=headers)
        except Exception as exc:
            warnings.append(f"Semantic Scholar 补全失败：{identifier} | {exc}")
            continue
        _merge_semantic_scholar(paper, data)

    return papers, warnings


def _paper_identifier(paper: dict[str, Any]) -> str:
    doi = normalize_doi(paper.get("doi"))
    if doi:
        return f"DOI:{doi}"
    pmid = str(paper.get("pmid") or "").strip()
    if pmid:
        return f"PMID:{pmid}"
    return ""


def _merge_semantic_scholar(paper: dict[str, Any], data: dict[str, Any]) -> None:
    if data.get("abstract") and not paper.get("abstract"):
        paper["abstract"] = data["abstract"]
    if data.get("venue") and not paper.get("journal"):
        paper["journal"] = data["venue"]
    if data.get("publicationDate") and not paper.get("publication_date"):
        paper["publication_date"] = data["publicationDate"]
    if data.get("year") and not paper.get("year"):
        paper["year"] = data["year"]

    external_ids = data.get("externalIds") or {}
    doi = normalize_doi(external_ids.get("DOI"))
    if doi and not paper.get("doi"):
        paper["doi"] = doi
        paper["url"] = f"https://doi.org/{doi}"

    publication_types = data.get("publicationTypes") or []
    if publication_types:
        paper.setdefault("article_types", [])
        for publication_type in publication_types:
            if publication_type not in paper["article_types"]:
                paper["article_types"].append(publication_type)

    paper["semantic_scholar"] = {
        "url": data.get("url"),
        "venue": data.get("venue"),
        "citationCount": data.get("citationCount"),
        "influentialCitationCount": data.get("influentialCitationCount"),
        "authors": [author.get("name") for author in data.get("authors", []) if author.get("name")],
        "journal": data.get("journal"),
    }
