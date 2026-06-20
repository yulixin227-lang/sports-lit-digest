from __future__ import annotations

import html
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
    return md_path, html_path


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

    return {
        "start_date": start_date,
        "end_date": end_date,
        "fetched_count": metadata.get("fetched_count", 0),
        "selected_count": len(papers),
        "focus_topics": " / ".join(focus_topics) if focus_topics else "暂无明确重点方向",
        "top_pick": top_pick,
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
        f"**文章类型**：{paper['article_type_label']}",
        "",
        f"**推荐指数**：{paper['stars']}（{paper['recommendation_index']}）",
        "",
        f"**质量评分**：{paper['score']}/100",
        "",
        f"**关键词**：{paper['keywords_display']}",
        "",
        f"**链接**：{paper['link']}",
        "",
        f"**证据强度提醒**：{paper['evidence_strength']}",
        "",
    ]
    for section in paper.get("body_sections") or []:
        lines.extend([f"**{section['label']}**", section["value"], ""])
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
        "h1{font-size:30px;line-height:1.35;margin-bottom:20px}h2{font-size:22px;line-height:1.4;margin:0 0 12px}h3{font-size:19px;margin-top:32px}",
        ".overview{border:1px solid #d0d7de;border-radius:8px;padding:18px 20px;background:#f6f8fa;margin-bottom:28px}",
        ".paper-card{border:1px solid #d0d7de;border-radius:8px;padding:22px 24px;margin:24px 0}",
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
        f"<p class='meta'><strong>文章类型：</strong>{html.escape(str(paper['article_type_label']))}</p>",
        f"<p class='score'>推荐指数：{html.escape(str(paper['stars']))}（{html.escape(str(paper['recommendation_index']))}） | 质量评分：{html.escape(str(paper['score']))}/100</p>",
        f"<p class='meta'><strong>关键词：</strong>{html.escape(str(paper['keywords_display']))}</p>",
        f"<p class='meta'><strong>链接：</strong><a href='{html.escape(str(paper['link']))}'>{html.escape(str(paper['link']))}</a></p>",
        f"<p class='evidence'><strong>证据强度提醒：</strong>{html.escape(str(paper['evidence_strength']))}</p>",
    ]
    for section in paper.get("body_sections") or []:
        body.append(_html_field(section["label"], section["value"]))
    body.append("</article>")
    return body


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


def _top_pick_text(top_pick: dict[str, Any]) -> str:
    if top_pick.get("index"):
        return f"第 {top_pick['index']} 篇，{top_pick['reason']}"
    return str(top_pick.get("reason") or "今日暂无推荐。")
