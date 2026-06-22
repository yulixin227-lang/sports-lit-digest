from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .enrich_semantic_scholar import enrich_with_semantic_scholar
from .fetch_crossref import enrich_with_crossref
from .fetch_pubmed import fetch_pubmed_articles
from .render_digest import render_digest
from .score_papers import score_papers, select_top_papers
from .send_wxpusher import send_wechat_digest
from .summarize_papers import summarize_papers
from .utils import (
    ROOT,
    add_seen_paper,
    bool_env,
    int_env,
    load_env,
    load_yaml_config,
    read_seen,
    write_seen,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    load_env(ROOT)
    end_date = resolve_date(args.date)
    start_date = end_date - timedelta(days=max(args.days_back, 1) - 1)

    journals_config = load_yaml_config(ROOT / "config" / "journals.yaml")
    journal_metrics_config = load_yaml_config(ROOT / "config" / "journal_metrics.yaml")
    categories_config = load_yaml_config(ROOT / "config" / "categories.yaml")
    elite_journals_config = load_yaml_config(ROOT / "config" / "elite_journals.yaml")
    keywords_config = load_yaml_config(ROOT / "config" / "keywords.yaml")
    scoring_config = load_yaml_config(ROOT / "config" / "scoring.yaml")
    seen_path = ROOT / "data" / "seen_papers.json"
    seen = read_seen(seen_path)

    warnings: list[str] = []
    papers, stage_warnings = fetch_pubmed_articles(
        start_date=start_date,
        end_date=end_date,
        journals_config=journals_config,
        keywords_config=keywords_config,
        categories_config=categories_config,
        elite_journals_config=elite_journals_config,
        retmax=int_env("PUBMED_RETMAX", 100),
    )
    warnings.extend(stage_warnings)

    if papers and bool_env("ENABLE_CROSSREF", True):
        papers, stage_warnings = enrich_with_crossref(papers)
        warnings.extend(stage_warnings)

    if papers and bool_env("ENABLE_SEMANTIC_SCHOLAR", True):
        papers, stage_warnings = enrich_with_semantic_scholar(papers)
        warnings.extend(stage_warnings)

    scored = score_papers(
        papers,
        journals_config,
        keywords_config,
        scoring_config,
        categories_config=categories_config,
        elite_journals_config=elite_journals_config,
    )
    min_score = int_env("DIGEST_MIN_SCORE", int(scoring_config.get("threshold", 70)))
    max_papers = int_env("DIGEST_MAX_PAPERS", int(scoring_config.get("max_papers", 5)))
    skip_empty_push = bool_env("SKIP_EMPTY_PUSH", True)
    selection_seen = empty_seen() if args.force_send else seen
    selected = select_top_papers(
        scored,
        seen=selection_seen,
        min_score=min_score,
        max_papers=max_papers,
        scoring_config=scoring_config,
    )
    summaries = summarize_papers(selected, keywords_config, journal_metrics_config)

    md_path, html_path = render_digest(
        summaries,
        output_dir=ROOT / "outputs",
        template_dir=ROOT / "templates",
        digest_date=end_date.isoformat(),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        metadata={
            "dry_run": args.dry_run,
            "fetched_count": len(papers),
            "scored_count": len(scored),
            "selected_count": len(selected),
            "min_score": min_score,
            "max_papers": max_papers,
            "skip_empty_push": skip_empty_push,
            "force_send": args.force_send,
            "warnings": warnings,
        },
    )

    send_metadata = {
        "dry_run": args.dry_run,
        "fetched_count": len(papers),
        "scored_count": len(scored),
        "selected_count": len(selected),
        "min_score": min_score,
        "max_papers": max_papers,
        "skip_empty_push": skip_empty_push,
        "force_send": args.force_send,
        "warnings": warnings,
    }
    requested_wechat_mode = "full" if args.wechat_full else args.wechat_mode
    effective_wechat_mode = resolve_wechat_mode(requested_wechat_mode, len(selected))
    if should_skip_wechat_push(
        send_wechat=args.send_wechat,
        dry_run=args.dry_run,
        skip_empty_push=skip_empty_push,
        selected_count=len(selected),
    ):
        print("No selected papers; skipped WeChat push.")
    elif args.send_wechat:
        send_result = send_wechat_digest(
            provider=args.wechat_provider,
            papers=summaries,
            metadata=send_metadata,
            digest_date=end_date.isoformat(),
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            html_path=html_path,
            dry_run=args.dry_run,
            wechat_mode=effective_wechat_mode,
            markdown_path=md_path,
        )
        if args.dry_run and effective_wechat_mode == "full":
            print("Wechat full dry-run:")
            print(f"WxPusher Mode: {send_result.mode or 'none'}")
            print(f"Wechat Mode: {requested_wechat_mode} -> {effective_wechat_mode}")
            print(f"Segments: {send_result.chunk_count}")
            print(
                "Segment lengths: "
                + ", ".join(str(length) for length in (send_result.chunk_lengths or []))
            )
            print(f"Digest: {send_result.digest_location or str(md_path)}")
        elif args.dry_run:
            print("Wechat dry-run:")
            print(f"WxPusher Mode: {send_result.mode or 'none'}")
            print(f"Wechat Mode: {requested_wechat_mode} -> {effective_wechat_mode}")
            print(f"Target SPT: {send_result.target_spt or '未配置'}")
            print(f"Target UIDs: {', '.join(send_result.target_uids or []) or '未配置'}")
            print(f"Target Topic IDs: {', '.join(str(item) for item in (send_result.target_topic_ids or [])) or '未配置'}")
            print(f"Title: {send_result.title or '未生成'}")
            print(f"Summary: {send_result.summary or '未生成'}")
            print(f"Digest: {send_result.digest_location or str(html_path)}")
            print("Wechat message preview:")
            print(send_result.preview)
        elif send_result.sent:
            print(f"Wechat push sent via {send_result.provider}.")
            print(f"Wechat Mode: {requested_wechat_mode} -> {effective_wechat_mode}")
            if send_result.full_body:
                print(f"Wechat full segments: {send_result.chunk_count}")
                print(
                    "Wechat full segment lengths: "
                    + ", ".join(str(length) for length in (send_result.chunk_lengths or []))
                )
            if send_result.response is not None:
                print(f"WxPusher response: {json.dumps(_sanitize_push_response(send_result.response), ensure_ascii=False)}")
        else:
            print(f"Wechat push skipped or failed via {send_result.provider}.")
            print(f"Wechat Mode: {requested_wechat_mode} -> {effective_wechat_mode}")
            if send_result.full_body:
                print(f"Wechat full segments: {send_result.chunk_count}")
                print(
                    "Wechat full segment lengths: "
                    + ", ".join(str(length) for length in (send_result.chunk_lengths or []))
                )
            if send_result.response is not None:
                print(f"WxPusher response: {json.dumps(_sanitize_push_response(send_result.response), ensure_ascii=False)}")
        warnings.extend(send_result.warnings)

    if not args.dry_run and not args.force_send:
        for paper in selected:
            add_seen_paper(seen, paper)
        write_seen(seen_path, seen)

    print(f"Fetched: {len(papers)} | Selected: {len(selected)} | Dry run: {args.dry_run}")
    print(f"Markdown: {md_path}")
    print(f"HTML: {html_path}")
    if args.dry_run:
        print("Seen file unchanged because --dry-run was used.")
    elif args.force_send:
        print("Seen file unchanged because --force-send was used.")
    for warning in warnings:
        print(f"Warning: {warning}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a daily Chinese digest for high-quality sports science papers."
    )
    parser.add_argument(
        "--date",
        default="today",
        help="Digest date. Use 'today' or YYYY-MM-DD. Default: today.",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=1,
        help="Number of publication days to search ending at --date. Default: 1.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render outputs but do not update data/seen_papers.json.",
    )
    parser.add_argument(
        "--force-send",
        action="store_true",
        help="Ignore seen_papers.json for this run and do not update it. Intended for manual cloud push tests.",
    )
    parser.add_argument(
        "--send-wechat",
        action="store_true",
        help="Send a digest notification to WeChat after rendering. Requires provider env config.",
    )
    parser.add_argument(
        "--wechat-full",
        action="store_true",
        help="Compatibility flag for --wechat-mode full. May split long digests into multiple messages.",
    )
    parser.add_argument(
        "--wechat-mode",
        choices=["smart", "short", "full"],
        default="smart",
        help="WeChat push mode. smart: 1 selected paper sends full, 2+ sends short. Default: smart.",
    )
    parser.add_argument(
        "--wechat-provider",
        choices=["wxpusher", "serverchan"],
        default="wxpusher",
        help="WeChat push provider. Default: wxpusher. serverchan is reserved as a TODO fallback.",
    )
    return parser


def resolve_date(value: str) -> date:
    if value.lower() == "today":
        return today_in_configured_timezone()
    return datetime.strptime(value, "%Y-%m-%d").date()


def empty_seen() -> dict[str, set[str]]:
    return {"dois": set(), "pmids": set()}


def should_skip_wechat_push(
    *,
    send_wechat: bool,
    dry_run: bool,
    skip_empty_push: bool,
    selected_count: int,
) -> bool:
    return bool(send_wechat and not dry_run and skip_empty_push and selected_count == 0)


def resolve_wechat_mode(requested_mode: str, selected_count: int) -> str:
    if requested_mode == "smart":
        return "full" if selected_count == 1 else "short"
    return requested_mode


def today_in_configured_timezone() -> date:
    timezone_name = os.getenv("DIGEST_TIMEZONE", "Asia/Taipei")
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(timezone_name)).date()
    except Exception:
        return date.today()


def _sanitize_push_response(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key.lower() in {"spt", "apptoken", "simplepushtoken", "simplepushtokenlist"}:
                sanitized[key] = _mask_secret(str(item or ""))
            else:
                sanitized[key] = _sanitize_push_response(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_push_response(item) for item in value]
    return value


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


if __name__ == "__main__":
    raise SystemExit(main())
