from __future__ import annotations

import os
import urllib.parse
from typing import Any

from .utils import http_get_json, normalize_doi


CROSSREF_WORKS_URL = "https://api.crossref.org/works"


def enrich_with_crossref(papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    mailto = os.getenv("CROSSREF_MAILTO") or os.getenv("NCBI_EMAIL")

    for paper in papers:
        try:
            message = _fetch_crossref_message(paper, mailto)
        except Exception as exc:
            warnings.append(f"Crossref 补全失败：{paper.get('title', '')[:80]} | {exc}")
            continue

        if not message:
            continue
        _merge_crossref_message(paper, message)

    return papers, warnings


def _fetch_crossref_message(paper: dict[str, Any], mailto: str | None) -> dict[str, Any] | None:
    doi = normalize_doi(paper.get("doi"))
    params = {"mailto": mailto} if mailto else None

    if doi:
        url = f"{CROSSREF_WORKS_URL}/{urllib.parse.quote(doi, safe='')}"
        data = http_get_json(url, params=params)
        return data.get("message")

    title = str(paper.get("title") or "").strip()
    if not title:
        return None
    query_params: dict[str, Any] = {"query.title": title, "rows": 1}
    if mailto:
        query_params["mailto"] = mailto
    data = http_get_json(CROSSREF_WORKS_URL, params=query_params)
    items = data.get("message", {}).get("items", [])
    return items[0] if items else None


def _merge_crossref_message(paper: dict[str, Any], message: dict[str, Any]) -> None:
    doi = normalize_doi(message.get("DOI"))
    if doi and not paper.get("doi"):
        paper["doi"] = doi
        paper["url"] = f"https://doi.org/{doi}"

    container_titles = message.get("container-title") or []
    if container_titles and not paper.get("journal"):
        paper["journal"] = container_titles[0]

    published = _date_from_crossref(message)
    if published and not paper.get("publication_date"):
        paper["publication_date"] = published
    if published and not paper.get("year"):
        try:
            paper["year"] = int(published[:4])
        except ValueError:
            pass

    if not paper.get("authors"):
        paper["authors"] = _authors_from_crossref(message)

    crossref_type = message.get("type")
    if crossref_type:
        paper.setdefault("article_types", [])
        if crossref_type not in paper["article_types"]:
            paper["article_types"].append(crossref_type)

    paper["crossref"] = {
        "is_referenced_by_count": message.get("is-referenced-by-count"),
        "publisher": message.get("publisher"),
        "url": message.get("URL"),
    }


def _date_from_crossref(message: dict[str, Any]) -> str:
    for key in ("published-online", "published-print", "published", "issued", "created"):
        date_parts = message.get(key, {}).get("date-parts")
        if date_parts and date_parts[0]:
            parts = date_parts[0]
            if len(parts) >= 3:
                return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
            if len(parts) >= 2:
                return f"{parts[0]:04d}-{parts[1]:02d}"
            return f"{parts[0]:04d}"
    return ""


def _authors_from_crossref(message: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for item in message.get("author", []):
        given = item.get("given") or ""
        family = item.get("family") or ""
        name = " ".join(part for part in [given, family] if part).strip()
        if name:
            authors.append(name)
    return authors
