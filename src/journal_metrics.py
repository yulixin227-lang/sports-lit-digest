from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .utils import ROOT, load_yaml_config


UNCONFIGURED = "未配置"


def load_journal_metrics_config(path: Path | None = None) -> dict[str, Any]:
    metrics_path = path or ROOT / "config" / "journal_metrics.yaml"
    if not metrics_path.exists():
        return {"journals": {}}
    return load_yaml_config(metrics_path)


def normalize_journal_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_journal_metrics(
    journal_name: Any,
    metrics_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = metrics_config if metrics_config is not None else load_journal_metrics_config()
    journals = config.get("journals") or {}
    normalized_query = normalize_journal_name(journal_name)
    match = _find_journal_metrics(normalized_query, journals)
    if match is None:
        return _format_metrics(
            {
                "display_name": str(journal_name or UNCONFIGURED).strip() or UNCONFIGURED,
                "impact_factor": None,
                "impact_factor_year": None,
                "jcr_quartile": None,
                "jcr_category": None,
                "jcr_year": None,
                "cas_zone": None,
                "cas_category": None,
                "cas_year": None,
                "metrics_source": None,
                "notes": "未在 config/journal_metrics.yaml 中配置",
            },
            configured=False,
        )
    return _format_metrics(match, configured=True)


def _find_journal_metrics(
    normalized_query: str,
    journals: dict[str, Any],
) -> dict[str, Any] | None:
    if not normalized_query:
        return None

    index: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in journals.items():
        if not isinstance(raw_value, dict):
            continue
        value = dict(raw_value)
        value.setdefault("display_name", raw_key)
        keys = [raw_key, value.get("display_name"), *(value.get("aliases") or [])]
        for key in keys:
            normalized_key = normalize_journal_name(key)
            if normalized_key:
                index[normalized_key] = value

    return index.get(normalized_query)


def _format_metrics(raw: dict[str, Any], *, configured: bool) -> dict[str, Any]:
    impact_factor = raw.get("impact_factor")
    impact_factor_year = _blank_to_none(raw.get("impact_factor_year"))
    jcr_quartile = _display_value(raw.get("jcr_quartile"))
    jcr_category = _display_value(raw.get("jcr_category"))
    jcr_year = _blank_to_none(raw.get("jcr_year"))
    cas_zone = _display_value(raw.get("cas_zone"))
    cas_category = _display_value(raw.get("cas_category"))
    cas_year = _blank_to_none(raw.get("cas_year"))
    metrics_source = _display_value(raw.get("metrics_source"))

    return {
        "configured": configured,
        "display_name": _display_value(raw.get("display_name")),
        "impact_factor": impact_factor,
        "impact_factor_display": _impact_factor_display(impact_factor),
        "impact_factor_year": impact_factor_year,
        "jcr_quartile": jcr_quartile,
        "jcr_category": jcr_category,
        "jcr_display": _join_metric_pair(jcr_quartile, jcr_category),
        "jcr_year": jcr_year,
        "cas_zone": cas_zone,
        "cas_category": cas_category,
        "cas_display": _join_metric_pair(cas_zone, cas_category),
        "cas_year": cas_year,
        "metrics_year_display": _metrics_year_display(impact_factor_year, jcr_year, cas_year),
        "metrics_source": metrics_source,
        "notes": str(raw.get("notes") or "").strip(),
    }


def _impact_factor_display(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return UNCONFIGURED
    return str(value).strip()


def _display_value(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return UNCONFIGURED
    return str(value).strip()


def _blank_to_none(value: Any) -> Any:
    if value is None or str(value).strip() == "":
        return None
    return value


def _join_metric_pair(primary: str, category: str) -> str:
    if primary == UNCONFIGURED and category == UNCONFIGURED:
        return UNCONFIGURED
    if category == UNCONFIGURED:
        return primary
    if primary == UNCONFIGURED:
        return f"{UNCONFIGURED} / {category}"
    return f"{primary} / {category}"


def _metrics_year_display(
    impact_factor_year: Any,
    jcr_year: Any,
    cas_year: Any,
) -> str:
    parts: list[str] = []
    if impact_factor_year:
        parts.append(f"{impact_factor_year} Impact Factor")
    if jcr_year:
        parts.append(f"{jcr_year} JCR")
    if cas_year:
        parts.append(f"{cas_year} 中科院分区")
    return "；".join(parts) if parts else UNCONFIGURED
