from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def render_digest(
    papers: list[dict[str, Any]],
    output_dir: Path,
    template_dir: Path,
    digest_date: str,
    start_date: str,
    end_date: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = metadata or {}
    overview = _build_overview(papers, metadata, start_date, end_date)
    context = {
        "date": digest_date,
        "start_date": start_date,
        "end_date": end_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "papers": papers,
        "paper_count": len(papers),
        "metadata": metadata,
        "overview": overview,
        "term_dictionary": _merge_dictionary_terms(papers),
    }

    md_text = _render_template(template_dir, "daily_digest.md.j2", context, fallback=_fallback_markdown)
    html_text = _render_template(template_dir, "daily_digest.html.j2", context, fallback=_fallback_html)

    md_path = output_dir / f"{digest_date}-digest.md"
    html_path = output_dir / f"{digest_date}-digest.html"
    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    _write_index(output_dir, latest_date=digest_date, latest_overview=overview)
    return md_path, html_path


def _write_index(output_dir: Path, latest_date: str, latest_overview: dict[str, Any]) -> Path:
    entries = _collect_digest_entries(output_dir, latest_date, latest_overview)
    latest = entries[0] if entries else {
        "date": latest_date,
        "file": f"{latest_date}-digest.html",
        "selected_count": latest_overview.get("selected_count", 0),
        "focus_topics": latest_overview.get("focus_topics", "暂无明确重点方向"),
    }
    index_path = output_dir / "index.html"
    index_path.write_text(_index_html(entries, latest), encoding="utf-8")
    return index_path


def _collect_digest_entries(
    output_dir: Path,
    latest_date: str,
    latest_overview: dict[str, Any],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for html_file in output_dir.glob("*-digest.html"):
        match = re.match(r"(\d{4}-\d{2}-\d{2})-digest\.html$", html_file.name)
        if not match:
            continue
        item_date = match.group(1)
        if item_date == latest_date:
            selected_count = latest_overview.get("selected_count", 0)
            focus_topics = latest_overview.get("focus_topics", "暂无明确重点方向")
        else:
            selected_count, focus_topics = _read_digest_summary(html_file.with_suffix(".md"))
        entries.append(
            {
                "date": item_date,
                "file": html_file.name,
                "selected_count": selected_count,
                "focus_topics": focus_topics,
            }
        )
    return sorted(entries, key=lambda item: item["date"], reverse=True)


def _read_digest_summary(md_path: Path) -> tuple[int | str, str]:
    if not md_path.exists():
        return "未知", "暂无记录"
    text = md_path.read_text(encoding="utf-8", errors="replace")
    selected_match = re.search(r"最终推荐：\s*(\d+)\s*篇", text)
    focus_match = re.search(r"本期重点方向：\s*(.+)", text)
    selected_count: int | str = int(selected_match.group(1)) if selected_match else "未知"
    focus_topics = focus_match.group(1).strip() if focus_match else "暂无记录"
    return selected_count, focus_topics


def _index_html(entries: list[dict[str, Any]], latest: dict[str, Any]) -> str:
    history_items = "\n".join(
        "<li>"
        f"<a href='{html.escape(item['file'])}'>{html.escape(item['date'])}</a>"
        f"<span>最终推荐 {html.escape(str(item['selected_count']))} 篇</span>"
        f"<span>{html.escape(str(item['focus_topics']))}</span>"
        "</li>"
        for item in entries
    )
    latest_file = html.escape(str(latest["file"]))
    latest_date = html.escape(str(latest["date"]))
    generated_at = html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>每日运动科学文献简报</title>
  <style>
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC',sans-serif;line-height:1.75;max-width:920px;margin:40px auto;padding:0 20px;color:#202124;background:#fff}}
    h1{{font-size:30px;line-height:1.35;margin-bottom:10px}}
    .latest{{border:1px solid #d0d7de;border-radius:8px;padding:18px 20px;background:#f6f8fa;margin:24px 0}}
    .latest a{{font-size:20px;font-weight:700}}
    ul{{list-style:none;padding:0;margin:0}}
    li{{border-top:1px solid #d0d7de;padding:14px 0;display:grid;grid-template-columns:150px 140px 1fr;gap:14px;align-items:start}}
    a{{color:#0969da;text-decoration:none}}a:hover{{text-decoration:underline}}
    .meta{{color:#57606a;font-size:14px}}
    @media(max-width:720px){{li{{display:block}}li span{{display:block;margin-top:4px}}}}
  </style>
  <script>
    window.setTimeout(function(){{
      var params = new URLSearchParams(window.location.search);
      if (!params.has('stay')) {{
        window.location.href = '{latest_file}';
      }}
    }}, 4500);
  </script>
</head>
<body>
  <h1>每日运动科学文献简报</h1>
  <p class="meta">页面会在数秒后自动跳转到最新简报；如需停留在历史列表，可在地址后加 <code>?stay=1</code>。</p>
  <section class="latest">
    <p class="meta">最新简报</p>
    <a href="{latest_file}">{latest_date} 文献简报</a>
    <p>最终推荐 {html.escape(str(latest['selected_count']))} 篇｜{html.escape(str(latest['focus_topics']))}</p>
  </section>
  <h2>历史简报</h2>
  <ul>
    {history_items}
  </ul>
  <p class="meta">更新时间：{generated_at}</p>
</body>
</html>
"""


def _build_overview(
    papers: list[dict[str, Any]],
    metadata: dict[str, Any],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    focus_topics = []
    for paper in papers:
        focus_topics.extend(paper.get("focus_topics") or [])
    focus_topics = list(dict.fromkeys(focus_topics))[:5]

    if papers:
        top_index, top_paper = max(
            enumerate(papers, 1),
            key=lambda item: float(item[1].get("score") or 0),
        )
        top_pick = {
            "index": top_index,
            "title": top_paper.get("chinese_title"),
            "reason": top_paper.get("top_pick_reason") or top_paper.get("one_sentence_conclusion"),
        }
    else:
        top_pick = {
            "index": None,
            "title": "今日暂无推荐",
            "reason": "当前阈值下没有新文章入选。",
        }

    presentation_pick = _select_presentation_pick(papers)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "fetched_count": metadata.get("fetched_count", 0),
        "selected_count": len(papers),
        "focus_topics": " / ".join(focus_topics) if focus_topics else "暂无明确重点方向",
        "top_pick": top_pick,
        "presentation_pick": presentation_pick,
    }


def _select_presentation_pick(papers: list[dict[str, Any]]) -> dict[str, Any]:
    if not papers:
        return {
            "index": None,
            "title": "",
            "reason": "今日没有特别适合组会精讲的文章。",
        }

    best_index, best_paper = max(
        enumerate(papers, 1),
        key=lambda item: float(item[1].get("presentation_value_score") or 0),
    )
    score = float(best_paper.get("presentation_value_score") or 0)
    materials = best_paper.get("presentation_materials") or {}
    suitability = str(materials.get("suitability") or "")
    if score < 55 or suitability == "不建议":
        return {
            "index": None,
            "title": "",
            "reason": "今日没有特别适合组会精讲的文章。",
        }
    return {
        "index": best_index,
        "title": best_paper.get("chinese_title") or best_paper.get("title") or "",
        "reason": materials.get("core_talking_point")
        or best_paper.get("presentation_value_reason")
        or best_paper.get("why_worth_reading")
        or "这篇文章的研究问题和结果信息相对更适合做组会讲解。",
        "score": round(score, 1),
    }


def _merge_dictionary_terms(papers: list[dict[str, Any]]) -> list[dict[str, str]]:
    merged: dict[str, str] = {}
    for paper in papers:
        for item in paper.get("dictionary_terms") or []:
            merged.setdefault(str(item["term"]), str(item["definition"]))
    return [{"term": term, "definition": definition} for term, definition in merged.items()]


def _render_template(
    template_dir: Path,
    template_name: str,
    context: dict[str, Any],
    fallback,
) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(template_name)
        return template.render(**context)
    except ModuleNotFoundError:
        return fallback(context)


def _fallback_markdown(context: dict[str, Any]) -> str:
    overview = context["overview"]
    lines = [
        f"# 每日运动科学文献简报 | {context['date']}",
        "",
        "## 今日概览",
        "",
        f"- 检索范围：{overview['start_date']} 至 {overview['end_date']}",
        f"- 初筛文章：{overview['fetched_count']} 篇",
        f"- 最终推荐：{overview['selected_count']} 篇",
        f"- 本期重点方向：{overview['focus_topics']}",
        f"- 今日最值得读：{_top_pick_text(overview['top_pick'])}",
        f"- 今日最适合组会讲：{_presentation_pick_text(overview['presentation_pick'])}",
        "",
    ]

    metadata = context.get("metadata") or {}
    if metadata.get("dry_run"):
        lines.extend(["> dry-run：本次不会更新 `data/seen_papers.json`。", ""])
    if metadata.get("warnings"):
        lines.extend(["> 运行提示：部分外部数据源补全失败，不影响已生成内容；详见命令行 warning。", ""])

    if not context["papers"]:
        lines.extend(
            [
                "今天没有达到评分阈值的新增文章。",
                "",
                "这不代表相关领域没有新文献，只表示在当前期刊白名单、关键词和评分阈值下没有入选。",
                "",
            ]
        )

    for index, paper in enumerate(context["papers"], 1):
        lines.extend(_paper_markdown(index, paper))

    lines.extend(_dictionary_markdown(context["term_dictionary"]))
    lines.append(f"生成时间：{context['generated_at']}")
    return "\n".join(lines).rstrip() + "\n"


def _paper_markdown(index: int, paper: dict[str, Any]) -> list[str]:
    lines = [
        f"## {index}. {paper['chinese_title']}",
        "",
        f"**英文原题**：{paper['title']}",
        "",
        f"**期刊 / 年份 / DOI / PMID**：{paper['journal']} / {paper['year']} / {paper['doi']} / {paper['pmid']}",
        "",
        "**期刊信息**：",
        f"- 期刊：{_journal_metric(paper, 'display_name')}",
        f"- 影响因子：{_journal_metric(paper, 'impact_factor_display')}",
        f"- JCR分区：{_journal_metric(paper, 'jcr_display')}",
        f"- 中科院分区：{_journal_metric(paper, 'cas_display')}",
        f"- 指标年份：{_journal_metric(paper, 'metrics_year_display')}",
        f"- 数据来源：{_journal_metric(paper, 'metrics_source')}",
        "",
        f"**文章类型**：{paper['article_type_label']}",
        "",
        f"**本篇方向**：{_paper_value(paper, 'direction_display', '未明确分类')}",
        "",
        f"**研究类型标签**：{_paper_value(paper, 'study_type_display', '未明确研究类型')}",
        "",
        f"**数据来源**：{_paper_value(paper, 'data_source_display', '摘要中未提供')}",
        "",
        f"**是否顶刊雷达**：{_paper_value(paper, 'elite_radar_display', '否')}",
        "",
        f"**和我有什么关系**：{_paper_value(paper, 'relation_to_me', '这篇文章与当前扩展方向的关系不够明确。')}",
        "",
        f"**推荐指数**：{paper['stars']}（{paper['recommendation_index']}）",
        "",
        f"**质量评分**：{paper['score']}/100",
        "",
        f"**阅读优先级**：{_paper_value(paper, 'reading_priority', '推荐阅读')}",
        "",
        f"**结果具体性**：{_paper_value(paper, 'result_specificity_display', '未评估')}",
        "",
        f"**关键词**：{paper['keywords_display']}",
        "",
        f"**链接**：{paper['link']}",
        "",
        f"**精简版摘要**：{_paper_value(paper, 'brief_summary', '摘要未明确说明，需阅读全文确认。')}",
        "",
        f"**证据强度提醒**：{paper['evidence_strength']}",
        "",
    ]
    for section in paper.get("body_sections") or []:
        lines.extend([f"**{section['label']}**", section["value"], ""])
    lines.extend(_presentation_markdown(paper))
    lines.extend(_ppt_markdown(paper))
    lines.extend(_missing_markdown(paper))
    lines.append("---")
    lines.append("")
    return lines


def _dictionary_markdown(term_dictionary: list[dict[str, str]]) -> list[str]:
    lines = ["## 今日术语小词典", ""]
    if not term_dictionary:
        lines.extend(["今天入选文章没有触发需要额外解释的英文缩写或术语。", ""])
        return lines
    for item in term_dictionary:
        lines.append(f"- **{item['term']}**：{item['definition']}")
    lines.append("")
    return lines


def _fallback_html(context: dict[str, Any]) -> str:
    overview = context["overview"]
    body = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>每日运动科学文献简报 | {html.escape(context['date'])}</title>",
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC',sans-serif;line-height:1.75;max-width:920px;margin:40px auto;padding:0 20px;color:#202124;background:#fff}",
        "h1{font-size:30px;line-height:1.35;margin-bottom:20px}h2{font-size:22px;line-height:1.4;margin:0 0 12px}h3{font-size:19px;margin:28px 0 10px}h4{font-size:16px;margin:18px 0 6px}",
        ".overview{border:1px solid #d0d7de;border-radius:8px;padding:18px 20px;background:#f6f8fa;margin-bottom:28px}",
        ".paper-card{border:1px solid #d0d7de;border-radius:8px;padding:22px 24px;margin:24px 0}",
        ".journal-metrics{border:1px solid #d8dee4;border-radius:8px;padding:12px 14px;margin:14px 0;background:#fbfbfd}.journal-metrics ul{margin:6px 0 0 18px;padding:0}",
        ".presentation-block,.ppt-block,.missing-block{border-top:1px solid #d8dee4;margin-top:24px;padding-top:14px}",
        ".meta{color:#57606a;margin:6px 0}.score{font-weight:700}.field{margin:18px 0}.label{font-weight:700}",
        ".evidence{border-left:4px solid #0969da;background:#f6f8fa;padding:10px 14px;margin:18px 0;color:#24292f}",
        "a{color:#0969da}.dict{border-top:1px solid #d0d7de;margin-top:34px;padding-top:18px}",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>每日运动科学文献简报 | {html.escape(context['date'])}</h1>",
        "<section class='overview'><h2>今日概览</h2><ul>",
        f"<li>检索范围：{html.escape(overview['start_date'])} 至 {html.escape(overview['end_date'])}</li>",
        f"<li>初筛文章：{html.escape(str(overview['fetched_count']))} 篇</li>",
        f"<li>最终推荐：{html.escape(str(overview['selected_count']))} 篇</li>",
        f"<li>本期重点方向：{html.escape(overview['focus_topics'])}</li>",
        f"<li>今日最值得读：{html.escape(_top_pick_text(overview['top_pick']))}</li>",
        f"<li>今日最适合组会讲：{html.escape(_presentation_pick_text(overview['presentation_pick']))}</li>",
        "</ul></section>",
    ]

    metadata = context.get("metadata") or {}
    if metadata.get("dry_run"):
        body.append("<p class='evidence'>dry-run：本次不会更新 <code>data/seen_papers.json</code>。</p>")
    if metadata.get("warnings"):
        body.append("<p class='evidence'>运行提示：部分外部数据源补全失败，不影响已生成内容；详见命令行 warning。</p>")
    if not context["papers"]:
        body.append("<p>今天没有达到评分阈值的新增文章。</p>")
        body.append("<p>这不代表相关领域没有新文献，只表示在当前期刊白名单、关键词和评分阈值下没有入选。</p>")

    for index, paper in enumerate(context["papers"], 1):
        body.extend(_paper_html(index, paper))

    body.extend(_dictionary_html(context["term_dictionary"]))
    body.append(f"<p class='meta'>生成时间：{html.escape(context['generated_at'])}</p>")
    body.extend(["</body>", "</html>"])
    return "\n".join(body)


def _paper_html(index: int, paper: dict[str, Any]) -> list[str]:
    body = [
        "<article class='paper-card'>",
        f"<h2>{index}. {html.escape(str(paper['chinese_title']))}</h2>",
        f"<p class='meta'><strong>英文原题：</strong>{html.escape(str(paper['title']))}</p>",
        f"<p class='meta'><strong>期刊 / 年份 / DOI / PMID：</strong>{html.escape(str(paper['journal']))} / {html.escape(str(paper['year']))} / {html.escape(str(paper['doi']))} / {html.escape(str(paper['pmid']))}</p>",
        "<section class='journal-metrics'><strong>期刊信息</strong><ul>",
        f"<li>期刊：{html.escape(_journal_metric(paper, 'display_name'))}</li>",
        f"<li>影响因子：{html.escape(_journal_metric(paper, 'impact_factor_display'))}</li>",
        f"<li>JCR分区：{html.escape(_journal_metric(paper, 'jcr_display'))}</li>",
        f"<li>中科院分区：{html.escape(_journal_metric(paper, 'cas_display'))}</li>",
        f"<li>指标年份：{html.escape(_journal_metric(paper, 'metrics_year_display'))}</li>",
        f"<li>数据来源：{html.escape(_journal_metric(paper, 'metrics_source'))}</li>",
        "</ul></section>",
        f"<p class='meta'><strong>文章类型：</strong>{html.escape(str(paper['article_type_label']))}</p>",
        f"<p class='meta'><strong>本篇方向：</strong>{html.escape(_paper_value(paper, 'direction_display', '未明确分类'))}</p>",
        f"<p class='meta'><strong>研究类型标签：</strong>{html.escape(_paper_value(paper, 'study_type_display', '未明确研究类型'))}</p>",
        f"<p class='meta'><strong>数据来源：</strong>{html.escape(_paper_value(paper, 'data_source_display', '摘要中未提供'))}</p>",
        f"<p class='meta'><strong>是否顶刊雷达：</strong>{html.escape(_paper_value(paper, 'elite_radar_display', '否'))}</p>",
        f"<p class='field'><span class='label'>和我有什么关系：</span>{html.escape(_paper_value(paper, 'relation_to_me', '这篇文章与当前扩展方向的关系不够明确。'))}</p>",
        f"<p class='score'>推荐指数：{html.escape(str(paper['stars']))}（{html.escape(str(paper['recommendation_index']))}） | 质量评分：{html.escape(str(paper['score']))}/100</p>",
        f"<p class='meta'><strong>阅读优先级：</strong>{html.escape(_paper_value(paper, 'reading_priority', '推荐阅读'))}</p>",
        f"<p class='meta'><strong>结果具体性：</strong>{html.escape(_paper_value(paper, 'result_specificity_display', '未评估'))}</p>",
        f"<p class='meta'><strong>关键词：</strong>{html.escape(str(paper['keywords_display']))}</p>",
        f"<p class='meta'><strong>链接：</strong><a href='{html.escape(str(paper['link']))}'>{html.escape(str(paper['link']))}</a></p>",
        f"<p class='field'><span class='label'>精简版摘要：</span>{html.escape(_paper_value(paper, 'brief_summary', '摘要未明确说明，需阅读全文确认。'))}</p>",
        f"<p class='evidence'><strong>证据强度提醒：</strong>{html.escape(str(paper['evidence_strength']))}</p>",
    ]
    for section in paper.get("body_sections") or []:
        body.append(_html_field(section["label"], section["value"]))
    body.extend(_presentation_html(paper))
    body.extend(_ppt_html(paper))
    body.extend(_missing_html(paper))
    body.append("</article>")
    return body


def _presentation_markdown(paper: dict[str, Any]) -> list[str]:
    materials = paper.get("presentation_materials") or {}
    if not materials:
        return []
    lines = [
        "### 组会汇报素材",
        "",
        f"- 是否适合做组会汇报：{_dict_value(materials, 'suitability', '可选')}",
        f"- 理由：{_dict_value(materials, 'reason', '摘要信息不足，需阅读全文后判断。')}",
        f"- 推荐汇报优先级：{_dict_value(materials, 'priority', '中')}",
        f"- 组会汇报价值评分：{_dict_value(materials, 'score', '未评分')}/100",
        "",
        "**组会讲解主线**",
        "",
    ]
    lines.extend(_markdown_list(materials.get("storyline")))
    lines.extend(["", "**关键实验和数据**", ""])
    for item in materials.get("key_data") or []:
        lines.append(f"- {item.get('label', '信息')}：{item.get('value') or '摘要未明确说明，需阅读全文确认。'}")
    lines.extend(["", "**重要结论**", ""])
    lines.extend(_markdown_list(materials.get("important_conclusions")))
    lines.extend(["", "**对小同行的启发**", ""])
    lines.extend(_markdown_list(materials.get("peer_inspiration")))
    lines.append("")
    return lines


def _ppt_markdown(paper: dict[str, Any]) -> list[str]:
    ppt = paper.get("ppt_preparation") or {}
    if not ppt:
        return []
    lines = [
        "### PPT 生成准备信息",
        "",
        f"- 建议 PPT 页数：简短汇报 {ppt.get('short_pages', '3-5 页')}；组会精讲 {ppt.get('deep_pages', '8-12 页')}",
        f"- 全文提醒：{ppt.get('full_text_notice', '当前未读取全文 PDF，Figure 内容需人工核对原文。')}",
        "",
        "**建议 PPT 结构**",
        "",
    ]
    for page in ppt.get("structure") or []:
        lines.append(f"- {page.get('title', 'PPT 页面')}")
        for bullet in page.get("bullets") or []:
            lines.append(f"  - {bullet}")
    lines.extend(["", "**Figure 使用原则**", ""])
    lines.extend(_markdown_list(ppt.get("figure_principles")))
    lines.append("")
    return lines


def _missing_markdown(paper: dict[str, Any]) -> list[str]:
    missing = paper.get("missing_info") or []
    lines = ["### 需要人工核对", ""]
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- 当前摘要和元数据已覆盖主要核对项，但正式组会前仍建议阅读全文。")
    lines.append("")
    return lines


def _presentation_html(paper: dict[str, Any]) -> list[str]:
    materials = paper.get("presentation_materials") or {}
    if not materials:
        return []
    body = [
        "<section class='presentation-block'>",
        "<h3>组会汇报素材</h3>",
        "<ul>",
        f"<li>是否适合做组会汇报：{html.escape(_dict_value(materials, 'suitability', '可选'))}</li>",
        f"<li>理由：{html.escape(_dict_value(materials, 'reason', '摘要信息不足，需阅读全文后判断。'))}</li>",
        f"<li>推荐汇报优先级：{html.escape(_dict_value(materials, 'priority', '中'))}</li>",
        f"<li>组会汇报价值评分：{html.escape(_dict_value(materials, 'score', '未评分'))}/100</li>",
        "</ul>",
        "<h4>组会讲解主线</h4>",
        _html_list(materials.get("storyline")),
        "<h4>关键实验和数据</h4>",
        "<ul>",
    ]
    for item in materials.get("key_data") or []:
        label = html.escape(str(item.get("label") or "信息"))
        value = html.escape(str(item.get("value") or "摘要未明确说明，需阅读全文确认。"))
        body.append(f"<li>{label}：{value}</li>")
    body.extend(
        [
            "</ul>",
            "<h4>重要结论</h4>",
            _html_list(materials.get("important_conclusions")),
            "<h4>对小同行的启发</h4>",
            _html_list(materials.get("peer_inspiration")),
            "</section>",
        ]
    )
    return body


def _ppt_html(paper: dict[str, Any]) -> list[str]:
    ppt = paper.get("ppt_preparation") or {}
    if not ppt:
        return []
    body = [
        "<section class='ppt-block'>",
        "<h3>PPT 生成准备信息</h3>",
        "<ul>",
        f"<li>建议 PPT 页数：简短汇报 {html.escape(str(ppt.get('short_pages', '3-5 页')))}；组会精讲 {html.escape(str(ppt.get('deep_pages', '8-12 页')))}</li>",
        f"<li>全文提醒：{html.escape(str(ppt.get('full_text_notice', '当前未读取全文 PDF，Figure 内容需人工核对原文。')))}</li>",
        "</ul>",
        "<h4>建议 PPT 结构</h4>",
    ]
    for page in ppt.get("structure") or []:
        body.append(f"<p class='label'>{html.escape(str(page.get('title') or 'PPT 页面'))}</p>")
        body.append(_html_list(page.get("bullets")))
    body.extend(
        [
            "<h4>Figure 使用原则</h4>",
            _html_list(ppt.get("figure_principles")),
            "</section>",
        ]
    )
    return body


def _missing_html(paper: dict[str, Any]) -> list[str]:
    missing = paper.get("missing_info") or []
    items = missing or ["当前摘要和元数据已覆盖主要核对项，但正式组会前仍建议阅读全文。"]
    return [
        "<section class='missing-block'>",
        "<h3>需要人工核对</h3>",
        _html_list(items),
        "</section>",
    ]


def _markdown_list(values: Any) -> list[str]:
    items = values or ["摘要未明确说明，需阅读全文确认。"]
    return [f"- {item}" for item in items]


def _html_list(values: Any) -> str:
    items = values or ["摘要未明确说明，需阅读全文确认。"]
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _dictionary_html(term_dictionary: list[dict[str, str]]) -> list[str]:
    body = ["<section class='dict'><h2>今日术语小词典</h2>"]
    if not term_dictionary:
        body.append("<p>今天入选文章没有触发需要额外解释的英文缩写或术语。</p></section>")
        return body
    body.append("<ul>")
    for item in term_dictionary:
        body.append(f"<li><strong>{html.escape(item['term'])}</strong>：{html.escape(item['definition'])}</li>")
    body.append("</ul></section>")
    return body


def _html_field(label: str, value: str) -> str:
    return f"<p class='field'><span class='label'>{html.escape(str(label))}：</span>{html.escape(str(value))}</p>"


def _journal_metric(paper: dict[str, Any], field: str) -> str:
    metrics = paper.get("journal_metrics") or {}
    value = metrics.get(field)
    if value is None or str(value).strip() == "":
        return "未配置"
    return str(value)


def _paper_value(paper: dict[str, Any], field: str, default: str) -> str:
    value = paper.get(field)
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def _dict_value(data: dict[str, Any], field: str, default: str) -> str:
    value = data.get(field)
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def _top_pick_text(top_pick: dict[str, Any]) -> str:
    if top_pick.get("index"):
        return f"第 {top_pick['index']} 篇，{top_pick['reason']}"
    return str(top_pick.get("reason") or "今日暂无推荐。")


def _presentation_pick_text(presentation_pick: dict[str, Any]) -> str:
    if presentation_pick.get("index"):
        return f"第 {presentation_pick['index']} 篇，{presentation_pick['reason']}"
    return str(presentation_pick.get("reason") or "今日没有特别适合组会精讲的文章。")
