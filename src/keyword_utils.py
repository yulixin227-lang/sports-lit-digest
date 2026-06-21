from __future__ import annotations

from typing import Any, Iterable


DEFAULT_KEYWORD_GROUPS = ("core_keywords", "expansion_keywords", "elite_journal_keywords", "keywords")


def iter_keywords(
    keywords_config: dict[str, Any],
    groups: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    selected_groups = tuple(groups or DEFAULT_KEYWORD_GROUPS)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for group in selected_groups:
        for keyword in keywords_config.get(group, []) or []:
            if not isinstance(keyword, dict):
                keyword = {"term": str(keyword)}
            term = str(keyword.get("term") or "").strip()
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            item = dict(keyword)
            item.setdefault("aliases", [])
            item.setdefault("weight", 1.0)
            item.setdefault("group", group)
            items.append(item)

    return items
