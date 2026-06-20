from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from .utils import http_post_json, http_post_text, normalize_doi


ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch_pubmed_articles(
    start_date: date,
    end_date: date,
    journals_config: dict[str, Any],
    keywords_config: dict[str, Any],
    retmax: int = 100,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch recent PubMed articles matching configured journals and keywords."""
    warnings: list[str] = []
    query = build_pubmed_query(journals_config, keywords_config)
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": retmax,
        "sort": "pub+date",
        "datetype": "pdat",
        "mindate": start_date.strftime("%Y/%m/%d"),
        "maxdate": end_date.strftime("%Y/%m/%d"),
        "tool": "sports-lit-digest",
        "email": os.getenv("NCBI_EMAIL") or os.getenv("CROSSREF_MAILTO"),
        "api_key": os.getenv("NCBI_API_KEY"),
    }

    try:
        search_data = http_post_json(ESEARCH_URL, data=_drop_empty(params))
    except Exception as exc:
        return [], [f"PubMed 检索失败：{exc}"]

    ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return [], warnings

    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "tool": "sports-lit-digest",
        "email": os.getenv("NCBI_EMAIL") or os.getenv("CROSSREF_MAILTO"),
        "api_key": os.getenv("NCBI_API_KEY"),
    }
    try:
        xml_text = http_post_text(EFETCH_URL, data=_drop_empty(fetch_params))
        papers = parse_pubmed_xml(xml_text)
    except Exception as exc:
        return [], [f"PubMed 详情解析失败：{exc}"]

    return papers, warnings


def build_pubmed_query(
    journals_config: dict[str, Any],
    keywords_config: dict[str, Any],
) -> str:
    journal_terms = []
    for journal in journals_config.get("journals", []):
        for name in [journal.get("name"), *journal.get("aliases", [])]:
            if name:
                journal_terms.append(f'"{_escape_query(str(name))}"[Journal]')

    keyword_terms = []
    for keyword in keywords_config.get("keywords", []):
        for term in [keyword.get("term"), *keyword.get("aliases", [])]:
            if term:
                keyword_terms.append(f'"{_escape_query(str(term))}"[Title/Abstract]')

    if not journal_terms:
        raise ValueError("config/journals.yaml 至少需要一个期刊")
    if not keyword_terms:
        raise ValueError("config/keywords.yaml 至少需要一个关键词")

    journal_part = " OR ".join(sorted(set(journal_terms)))
    keyword_part = " OR ".join(sorted(set(keyword_terms)))
    return f"({journal_part}) AND ({keyword_part})"


def parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    papers: list[dict[str, Any]] = []

    for article_node in root.findall(".//PubmedArticle"):
        citation = article_node.find("./MedlineCitation")
        article = citation.find("./Article") if citation is not None else None
        if article is None:
            continue

        pmid = _text(citation.find("./PMID")) if citation is not None else ""
        title = _text(article.find("./ArticleTitle"))
        abstract = _abstract_text(article)
        journal_title = _text(article.find("./Journal/Title"))
        iso_journal = _text(article.find("./Journal/ISOAbbreviation"))
        publication_date, year = _publication_date(article)
        doi = _article_doi(article_node)
        article_types = [
            _text(node)
            for node in article.findall("./PublicationTypeList/PublicationType")
            if _text(node)
        ]
        authors = _authors(article)

        paper = {
            "source": "pubmed",
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal_title or iso_journal,
            "journal_abbreviation": iso_journal,
            "publication_date": publication_date,
            "year": year,
            "doi": doi,
            "authors": authors,
            "article_types": article_types,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "url": f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""),
        }
        papers.append(paper)

    return _dedupe_papers(papers)


def _drop_empty(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in (None, "")}


def _escape_query(value: str) -> str:
    return value.replace('"', "")


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def _abstract_text(article: ET.Element) -> str:
    parts: list[str] = []
    for node in article.findall("./Abstract/AbstractText"):
        text = _text(node)
        if not text:
            continue
        label = node.attrib.get("Label") or node.attrib.get("NlmCategory")
        parts.append(f"{label}: {text}" if label else text)
    return "\n".join(parts)


def _article_doi(article_node: ET.Element) -> str:
    doi_nodes = article_node.findall(".//ELocationID[@EIdType='doi']")
    doi_nodes.extend(article_node.findall(".//ArticleId[@IdType='doi']"))
    for node in doi_nodes:
        doi = normalize_doi(_text(node))
        if doi:
            return doi
    return ""


def _authors(article: ET.Element) -> list[str]:
    names: list[str] = []
    for author in article.findall("./AuthorList/Author"):
        collective = _text(author.find("./CollectiveName"))
        if collective:
            names.append(collective)
            continue
        fore_name = _text(author.find("./ForeName"))
        last_name = _text(author.find("./LastName"))
        initials = _text(author.find("./Initials"))
        full_name = " ".join(part for part in [fore_name or initials, last_name] if part)
        if full_name:
            names.append(full_name)
    return names


def _publication_date(article: ET.Element) -> tuple[str, int | None]:
    article_date = article.find("./ArticleDate")
    if article_date is not None:
        parsed = _parse_date_parts(
            _text(article_date.find("./Year")),
            _text(article_date.find("./Month")),
            _text(article_date.find("./Day")),
        )
        if parsed[0]:
            return parsed

    pub_date = article.find("./Journal/JournalIssue/PubDate")
    if pub_date is not None:
        parsed = _parse_date_parts(
            _text(pub_date.find("./Year")),
            _text(pub_date.find("./Month")),
            _text(pub_date.find("./Day")),
        )
        if parsed[0]:
            return parsed
        medline_date = _text(pub_date.find("./MedlineDate"))
        if medline_date:
            match = re.search(r"\b(19|20)\d{2}\b", medline_date)
            year = int(match.group(0)) if match else None
            return medline_date, year

    return "", None


def _parse_date_parts(year_text: str, month_text: str, day_text: str) -> tuple[str, int | None]:
    if not year_text:
        return "", None
    year = int(year_text) if year_text.isdigit() else None
    month = _month_to_number(month_text)
    day = int(day_text) if day_text.isdigit() else None
    if year and month and day:
        return f"{year:04d}-{month:02d}-{day:02d}", year
    if year and month:
        return f"{year:04d}-{month:02d}", year
    if year:
        return f"{year:04d}", year
    return year_text, None


def _month_to_number(value: str) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        number = int(value)
        return number if 1 <= number <= 12 else None
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return months.get(value[:3].lower())


def _dedupe_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for paper in papers:
        key = normalize_doi(paper.get("doi")) or str(paper.get("pmid") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(paper)
    return deduped
