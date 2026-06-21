from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WXPUSHER_SEND_URL = "https://wxpusher.zjiecode.com/api/send/message"
WXPUSHER_SIMPLE_SEND_URL = "https://wxpusher.zjiecode.com/api/send/message/simple-push"
DEFAULT_FULL_MESSAGE_LIMIT = 18000


@dataclass
class SendResult:
    provider: str
    sent: bool
    skipped: bool
    preview: str
    warnings: list[str]
    title: str = ""
    summary: str = ""
    digest_location: str = ""
    target_uids: list[str] | None = None
    target_topic_ids: list[int] | None = None
    mode: str = ""
    target_spt: str = ""
    response: dict[str, Any] | None = None
    full_body: bool = False
    chunk_count: int = 1
    chunk_lengths: list[int] | None = None


def send_wechat_digest(
    *,
    provider: str,
    papers: list[dict[str, Any]],
    metadata: dict[str, Any],
    digest_date: str,
    start_date: str,
    end_date: str,
    html_path: Path,
    dry_run: bool,
    wechat_mode: str = "short",
    full_body: bool = False,
    markdown_path: Path | None = None,
) -> SendResult:
    if provider == "wxpusher":
        return send_wxpusher_digest(
            papers=papers,
            metadata=metadata,
            digest_date=digest_date,
            start_date=start_date,
            end_date=end_date,
            html_path=html_path,
            dry_run=dry_run,
            wechat_mode=wechat_mode,
            full_body=full_body,
            markdown_path=markdown_path,
        )
    if provider == "serverchan":
        preview = build_wechat_message(
            papers=papers,
            metadata=metadata,
            digest_date=digest_date,
            start_date=start_date,
            end_date=end_date,
            html_path=html_path,
        )["content"]
        return SendResult(
            provider="serverchan",
            sent=False,
            skipped=True,
            preview=preview,
            warnings=["Server酱通道已预留，但本版本尚未实现真实发送；请使用 --wechat-provider wxpusher。"],
            title="每日运动科学文献简报",
            target_uids=[],
            target_topic_ids=[],
            mode="serverchan",
        )
    return SendResult(
        provider=provider,
        sent=False,
        skipped=True,
        preview="",
        warnings=[f"未知微信推送通道：{provider}"],
    )


def send_wxpusher_digest(
    *,
    papers: list[dict[str, Any]],
    metadata: dict[str, Any],
    digest_date: str,
    start_date: str,
    end_date: str,
    html_path: Path,
    dry_run: bool,
    wechat_mode: str = "short",
    full_body: bool = False,
    markdown_path: Path | None = None,
) -> SendResult:
    if full_body or wechat_mode == "full":
        return send_wxpusher_full_digest(
            digest_date=digest_date,
            markdown_path=markdown_path or html_path.with_suffix(".md"),
            html_path=html_path,
            dry_run=dry_run,
        )

    message = build_wechat_message(
        papers=papers,
        metadata=metadata,
        digest_date=digest_date,
        start_date=start_date,
        end_date=end_date,
        html_path=html_path,
    )
    config = load_wxpusher_config()
    mode = _select_wxpusher_mode(config)
    result_fields = {
        "title": message["title"],
        "summary": message["summary"],
        "digest_location": message["digest_location"],
        "target_uids": config["uids"],
        "target_topic_ids": config["topic_ids"],
        "target_spt": _mask_secret(config["spt"]),
        "mode": mode or "none",
    }

    if dry_run:
        warnings = []
        if mode == "spt":
            warnings.append("WXPUSHER_SPT_ENABLED=true 且已配置 SPT；dry-run 不会真实发送。")
        elif mode == "standard":
            warnings.append("已配置 WxPusher 标准发送；dry-run 不会真实发送。")
        else:
            warnings.append("未配置可用的 WxPusher SPT 或标准发送；dry-run 仅展示预览。")
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=True,
            preview=message["content"],
            warnings=warnings,
            **result_fields,
        )

    if mode == "spt":
        return _send_wxpusher_spt(message, config, result_fields)

    if mode != "standard":
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=True,
            preview=message["content"],
            warnings=["未配置可用的 WxPusher SPT 或标准发送，已跳过微信推送。"],
            **result_fields,
        )

    return _send_wxpusher_standard(message, config, result_fields)


def send_wxpusher_full_digest(
    *,
    digest_date: str,
    markdown_path: Path,
    html_path: Path | None = None,
    dry_run: bool,
) -> SendResult:
    messages = build_full_digest_messages(
        digest_date=digest_date,
        markdown_path=markdown_path,
        html_path=html_path,
        max_chars=_int_env("WXPUSHER_FULL_CHUNK_CHARS", DEFAULT_FULL_MESSAGE_LIMIT),
    )
    config = load_wxpusher_config()
    mode = _select_wxpusher_mode(config)
    first_message = messages[0] if messages else {
        "title": f"每日运动科学文献简报 | {digest_date}",
        "summary": "完整简报正文",
        "content": "",
        "public_url": "",
        "digest_location": str(markdown_path),
    }
    result_fields = {
        "title": first_message["title"],
        "summary": first_message["summary"],
        "digest_location": str(markdown_path),
        "target_uids": config["uids"],
        "target_topic_ids": config["topic_ids"],
        "target_spt": _mask_secret(config["spt"]),
        "mode": mode or "none",
        "full_body": True,
        "chunk_count": len(messages),
        "chunk_lengths": [len(message["content"]) for message in messages],
    }

    preview = "\n\n---\n\n".join(message["content"] for message in messages)
    if dry_run:
        warnings = [f"wechat-full dry-run：将发送 {len(messages)} 段，长度约为 {result_fields['chunk_lengths']} 字。"]
        if mode == "spt":
            warnings.append("WXPUSHER_SPT_ENABLED=true 且已配置 SPT；dry-run 不会真实发送。")
        elif mode == "standard":
            warnings.append("已配置 WxPusher 标准发送；dry-run 不会真实发送。")
        else:
            warnings.append("未配置可用的 WxPusher SPT 或标准发送；dry-run 仅展示分段信息。")
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=True,
            preview=preview,
            warnings=warnings,
            **result_fields,
        )

    if mode not in {"spt", "standard"}:
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=True,
            preview=preview,
            warnings=["未配置可用的 WxPusher SPT 或标准发送，已跳过完整正文微信推送。"],
            **result_fields,
        )

    responses: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, message in enumerate(messages, 1):
        if mode == "spt":
            result = _send_wxpusher_spt(message, config, result_fields)
        else:
            result = _send_wxpusher_standard(message, config, result_fields)
        if result.response is not None:
            responses.append({"segment": index, "response": result.response})
        warnings.extend(result.warnings)
        if not result.sent:
            return SendResult(
                provider="wxpusher",
                sent=False,
                skipped=False,
                preview=preview,
                warnings=warnings or [f"第 {index}/{len(messages)} 段完整正文推送失败。"],
                response={
                    "sentSegments": index - 1,
                    "totalSegments": len(messages),
                    "segments": responses,
                },
                **result_fields,
            )

    return SendResult(
        provider="wxpusher",
        sent=True,
        skipped=False,
        preview=preview,
        warnings=warnings,
        response={
            "sentSegments": len(messages),
            "totalSegments": len(messages),
            "segments": responses,
        },
        **result_fields,
    )


def _send_wxpusher_spt(
    message: dict[str, str],
    config: dict[str, Any],
    result_fields: dict[str, Any],
) -> SendResult:
    payload: dict[str, Any] = {
        "content": message["content"][:40000],
        "summary": message["summary"][:100],
        "contentType": 3,
        "spt": config["spt"],
    }
    if message["public_url"]:
        payload["url"] = message["public_url"][:1000]

    try:
        response = _post_json(WXPUSHER_SIMPLE_SEND_URL, payload)
    except Exception as exc:
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=False,
            preview=message["content"],
            warnings=[f"WxPusher SPT 推送失败：{exc}"],
            **result_fields,
        )

    if response.get("code") != 1000 or response.get("success") is False:
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=False,
            preview=message["content"],
            warnings=[f"WxPusher SPT 推送返回异常：{response}"],
            response=response,
            **result_fields,
        )

    return SendResult(
        provider="wxpusher",
        sent=True,
        skipped=False,
        preview=message["content"],
        warnings=[],
        response=response,
        **result_fields,
    )


def _send_wxpusher_standard(
    message: dict[str, str],
    config: dict[str, Any],
    result_fields: dict[str, Any],
) -> SendResult:
    payload: dict[str, Any] = {
        "appToken": config["app_token"],
        "content": message["content"][:40000],
        "summary": message["summary"][:100],
        "contentType": 3,
        "verifyPayType": 0,
    }
    if config["uids"]:
        payload["uids"] = config["uids"]
    if config["topic_ids"]:
        payload["topicIds"] = config["topic_ids"]
    if message["public_url"]:
        payload["url"] = message["public_url"][:1000]

    try:
        response = _post_json(WXPUSHER_SEND_URL, payload)
    except Exception as exc:
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=False,
            preview=message["content"],
            warnings=[f"WxPusher 推送失败：{exc}"],
            **result_fields,
        )

    if response.get("code") != 1000 or response.get("success") is False:
        return SendResult(
            provider="wxpusher",
            sent=False,
            skipped=False,
            preview=message["content"],
            warnings=[f"WxPusher 推送返回异常：{response}"],
            response=response,
            **result_fields,
        )

    send_warnings = _send_record_warnings(response)
    return SendResult(
        provider="wxpusher",
        sent=True,
        skipped=False,
        preview=message["content"],
        warnings=send_warnings,
        response=response,
        **result_fields,
    )


def load_wxpusher_config() -> dict[str, Any]:
    app_token = os.getenv("WXPUSHER_APP_TOKEN", "").strip()
    if app_token in {"请我自己手动填写", "your_app_token", "YOUR_APP_TOKEN"}:
        app_token = ""
    spt_url = os.getenv("WXPUSHER_SPT_URL", "").strip()
    spt = extract_spt_from_url(spt_url)
    return {
        "spt_enabled": _bool_env("WXPUSHER_SPT_ENABLED", False),
        "spt_url": spt_url,
        "spt": spt,
        "enabled": _bool_env("WXPUSHER_ENABLED", False),
        "app_token": app_token,
        "uids": _split_csv(os.getenv("WXPUSHER_UIDS", "")),
        "topic_ids": _split_int_csv(os.getenv("WXPUSHER_TOPIC_IDS", "")),
    }


def extract_spt_from_url(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    token_match = re.search(r"\bSPT_[A-Za-z0-9_-]+\b", text)
    if token_match:
        return token_match.group(0)
    parsed = urllib.parse.urlparse(text)
    if parsed.path:
        decoded_path = urllib.parse.unquote(parsed.path)
        path_match = re.search(r"\bSPT_[A-Za-z0-9_-]+\b", decoded_path)
        if path_match:
            return path_match.group(0)
    return ""


def _select_wxpusher_mode(config: dict[str, Any]) -> str:
    if config["enabled"] and config["app_token"] and (config["uids"] or config["topic_ids"]):
        return "standard"
    if config["spt_enabled"] and config["spt"]:
        return "spt"
    return ""


def build_wechat_message(
    *,
    papers: list[dict[str, Any]],
    metadata: dict[str, Any],
    digest_date: str,
    start_date: str,
    end_date: str,
    html_path: Path,
) -> dict[str, str]:
    public_url = build_public_digest_url(html_path)
    digest_location = public_url or str(html_path)
    overview = _build_overview(papers, metadata, start_date, end_date)
    warnings = metadata.get("warnings") or []

    title = f"每日运动科学文献简报 | {digest_date}"
    lines = [
        title,
        "",
        "————————————",
        "【今日概览】",
        f"* 检索范围：{start_date} 至 {end_date}",
        f"* 初筛文章：{overview['fetched_count']} 篇",
        f"* 最终推荐：{overview['selected_count']} 篇",
        f"* 本期重点方向：{overview['focus_topics']}",
        "",
        "【今日最值得读】",
        overview["top_pick"],
        "",
    ]

    if papers:
        for index, paper in enumerate(papers, 1):
            metrics = _paper_journal_metrics(paper)
            lines.extend(
                [
                    "————————————",
                    f"【文章 {index}】",
                    str(paper.get("chinese_title") or "标题待补全"),
                    f"英文原题：{_truncate_text(paper.get('english_title') or paper.get('title') or '摘要中未提供', 96)}",
                    f"期刊：{metrics['display_name']}",
                    f"JCR：{metrics['jcr_quartile']}",
                    f"中科院：{metrics['cas_zone']}",
                    f"IF：{metrics['impact_factor']}",
                    f"文章类型：{paper.get('article_type_label', '类型待补全')}",
                    f"推荐指数：{paper.get('stars') or paper.get('recommendation_index', '待评估')}",
                    f"质量评分：{paper.get('score', '待评估')}/100",
                    "",
                    "【一句话结论】",
                    str(paper.get("one_sentence_conclusion") or "摘要中未提供。"),
                    "",
                    "【证据强度提醒】",
                    _brief_text(paper.get("evidence_strength") or "摘要中未提供。", 90),
                    "",
                    "【为什么值得看】",
                    _brief_text(_paper_section(paper, "为什么值得看") or paper.get("top_pick_reason") or "摘要中未提供。", 110),
                    "",
                ]
            )
    else:
        lines.append("今天没有达到评分阈值的新增文章。")
        lines.append("")

    history_location = build_public_index_url(html_path) or str(html_path.parent / "index.html")
    lines.extend(
        [
            "————————————",
            "【阅读全文】",
            _format_wechat_link(digest_location),
            "",
            "【历史简报】",
            _format_wechat_link(history_location),
        ]
    )
    if not public_url:
        lines.append("提示：手机微信可能无法打开本地路径。建议后续配置 PUBLIC_DIGEST_BASE_URL，并用 GitHub Pages 或 Cloudflare Pages 托管 outputs。")

    if warnings:
        lines.extend(
            [
                "",
                "【运行提示】",
                f"本次运行有 {len(warnings)} 条补全 warning，不影响简报生成；详情见命令行输出。",
            ]
        )

    content = "\n".join(lines).strip()
    return {
        "title": title,
        "summary": f"最终推荐 {overview['selected_count']} 篇｜{overview['focus_topics']}",
        "content": content,
        "public_url": public_url,
        "digest_location": digest_location,
    }


def build_full_digest_messages(
    *,
    digest_date: str,
    markdown_path: Path,
    html_path: Path | None = None,
    max_chars: int = DEFAULT_FULL_MESSAGE_LIMIT,
) -> list[dict[str, str]]:
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown digest not found: {markdown_path}")

    markdown = markdown_path.read_text(encoding="utf-8").strip()
    if not markdown:
        markdown = f"# 每日运动科学文献简报 | {digest_date}\n\n本期没有可推送的正文内容。"
    body = markdown_to_wechat_text(markdown)
    body = append_digest_location(body, html_path or markdown_path.with_suffix(".html"))

    chunks = split_markdown_by_paragraph(body, max_chars=max_chars)
    total = len(chunks)
    messages = []
    for index, chunk in enumerate(chunks, 1):
        title = f"每日运动科学文献简报 | {digest_date}"
        if total > 1:
            title = f"{title}（{index}/{total}）"
        content = chunk.strip()
        if not content.startswith("每日运动科学文献简报"):
            content = f"{title}\n\n{content}"
        elif total > 1:
            content = f"{title}\n\n{content}"
        content = f"{content}\n\n{'本期结束' if index == total else '继续下一条'}"
        messages.append(
            {
                "title": title,
                "summary": title[:100],
                "content": content,
                "public_url": build_public_digest_url(html_path or markdown_path.with_suffix(".html")),
                "digest_location": str(markdown_path),
            }
        )
    return messages


def split_markdown_by_paragraph(markdown: str, max_chars: int = DEFAULT_FULL_MESSAGE_LIMIT) -> list[str]:
    max_chars = max(1000, max_chars)
    body_limit = max_chars - 120
    blocks = re.split(r"\n{2,}", markdown.strip())
    chunks: list[str] = []
    current = ""

    for raw_block in blocks:
        block = raw_block.strip()
        if not block:
            continue
        candidates = _split_oversized_block(block, body_limit) if len(block) > body_limit else [block]
        for candidate in candidates:
            if not current:
                current = candidate
            elif len(current) + len(candidate) + 2 <= body_limit:
                current = f"{current}\n\n{candidate}"
            else:
                chunks.append(current)
                current = candidate

    if current:
        chunks.append(current)
    return chunks or [markdown.strip()]


def markdown_to_wechat_text(markdown: str) -> str:
    text = markdown.replace("\r\n", "\n")
    text = re.sub(r"^#\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+今日概览\s*$", "————————————\n【今日概览】", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+今日术语小词典\s*$", "————————————\n【术语小词典】", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+(\d+)\.\s+(.+)$", r"————————————\n【文章 \1】\n\2", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*(.+?)\*\*：", r"\1：", text, flags=re.MULTILINE)
    text = re.sub(r"^\*\*(.+?)\*\*\s*$", r"【\1】", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^- ", "* ", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def append_digest_location(text: str, html_path: Path) -> str:
    public_url = build_public_digest_url(html_path)
    digest_location = public_url or str(html_path)
    history_location = build_public_index_url(html_path) or str(html_path.parent / "index.html")
    lines = [
        text.strip(),
        "",
        "————————————",
        "【完整 HTML 简报】",
        _format_wechat_link(digest_location),
        "",
        "【历史简报】",
        _format_wechat_link(history_location),
    ]
    if not public_url:
        lines.append("提示：手机微信可能无法打开本地路径。建议配置 PUBLIC_DIGEST_BASE_URL。")
    return "\n".join(lines).strip()


def build_public_digest_url(html_path: Path) -> str:
    base_url = os.getenv("PUBLIC_DIGEST_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return ""
    return f"{base_url}/{html_path.name}"


def build_public_index_url(html_path: Path) -> str:
    base_url = os.getenv("PUBLIC_DIGEST_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return ""
    return f"{base_url}/"


def _build_overview(
    papers: list[dict[str, Any]],
    metadata: dict[str, Any],
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    focus_topics = []
    for paper in papers:
        focus_topics.extend(paper.get("focus_topics") or [])
    focus_topics_text = " / ".join(list(dict.fromkeys(focus_topics))[:5]) or "暂无明确重点方向"

    if papers:
        top_index, top_paper = max(
            enumerate(papers, 1),
            key=lambda item: float(item[1].get("score") or 0),
        )
        top_pick = f"第 {top_index} 篇，原因：{top_paper.get('top_pick_reason') or top_paper.get('one_sentence_conclusion')}"
    else:
        top_pick = "今日暂无推荐，当前阈值下没有新文章入选。"

    return {
        "start_date": start_date,
        "end_date": end_date,
        "fetched_count": metadata.get("fetched_count", 0),
        "selected_count": len(papers),
        "focus_topics": focus_topics_text,
        "top_pick": top_pick,
    }


def _collect_dictionary_terms(papers: list[dict[str, Any]]) -> list[dict[str, str]]:
    terms: list[dict[str, str]] = []
    seen: set[str] = set()
    for paper in papers:
        for item in paper.get("dictionary_terms") or []:
            term = str(item.get("term") or "").strip()
            definition = str(item.get("definition") or "").strip()
            key = term.lower()
            if term and definition and key not in seen:
                seen.add(key)
                terms.append({"term": term, "definition": definition})
    return terms


def _paper_journal_metrics(paper: dict[str, Any]) -> dict[str, str]:
    metrics = paper.get("journal_metrics") or {}
    return {
        "display_name": _metric_text(metrics.get("display_name") or paper.get("journal")),
        "jcr_quartile": _metric_text(metrics.get("jcr_quartile")),
        "cas_zone": _metric_text(metrics.get("cas_zone")),
        "impact_factor": _metric_text(metrics.get("impact_factor_display") or metrics.get("impact_factor")),
    }


def _metric_text(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "未配置"
    return str(value).strip()


def _paper_section(paper: dict[str, Any], label: str) -> str:
    for section in paper.get("body_sections") or []:
        if section.get("label") == label:
            return str(section.get("value") or "").strip()
    return ""


def _brief_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    sentence_match = re.match(r"^(.{20,}?[。！？.!?])", text)
    if sentence_match and len(sentence_match.group(1)) <= limit:
        return sentence_match.group(1)
    return _truncate_text(text, limit)


def _truncate_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _format_wechat_link(url: str) -> str:
    return f"[{url}]({url})"


def _post_json(url: str, payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    try:
        import requests

        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _send_record_warnings(response: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for item in response.get("data") or []:
        if item.get("code") != 1000:
            target = item.get("uid") or item.get("topicId") or "unknown target"
            warnings.append(f"WxPusher 目标 {target} 返回异常：{item}")
    return warnings


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_int_csv(value: str) -> list[int]:
    ids: list[int] = []
    for item in _split_csv(value):
        try:
            ids.append(int(item))
        except ValueError:
            continue
    return ids


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _split_oversized_block(block: str, limit: int) -> list[str]:
    lines = block.splitlines()
    if len(lines) > 1 and all(len(line) <= limit for line in lines):
        return _pack_units(lines, limit, separator="\n")

    sentences = re.split(r"(?<=[。！？.!?])\s+", block)
    if len(sentences) > 1 and all(len(sentence) <= limit for sentence in sentences):
        return _pack_units(sentences, limit, separator=" ")

    return [block[index : index + limit] for index in range(0, len(block), limit)]


def _pack_units(units: list[str], limit: int, separator: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + len(unit) + len(separator) <= limit:
            current = f"{current}{separator}{unit}"
        else:
            chunks.append(current)
            current = unit
    if current:
        chunks.append(current)
    return chunks


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"
