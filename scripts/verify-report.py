#!/usr/bin/env python3
"""Review report citations against search cache — run after each report is written.

产出校验仅供研究流程质量控制；不构成投资建议。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
CITE_DATE_RE = re.compile(r"·\s*(\d{4}-\d{2}-\d{2})")
CORE_NUMBER_RE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*(?:%|pct|bp|bps|亿元|亿|万元|万|美元|元|倍|x|X|"
    r"桶|万桶|吨|万吨|GW|GWh|MW|MWh|PE|PB)",
    re.I,
)


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    scheme = p.scheme.lower()
    if scheme in ("http", "https"):
        scheme = "https"
    return urlunparse((scheme, p.netloc.lower(), p.path.rstrip("/"), "", p.query, ""))


def load_cache_urls(cache_root: Path) -> dict[str, dict[str, Any]]:
    """url -> {title, parsed_date, status, discarded, paths}"""
    index: dict[str, dict[str, Any]] = {}

    def add(url: str, meta: dict[str, Any]) -> None:
        key = normalize_url(url)
        if key not in index:
            index[key] = meta
        else:
            index[key].update({k: v for k, v in meta.items() if v is not None})

    for pattern in ("macro/*.json", "stocks/*.json"):
        for jf in cache_root.glob(pattern):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for q in data.get("queries") or []:
                if not q:
                    continue
                for r in q.get("results") or []:
                    link = r.get("link")
                    if not link:
                        continue
                    add(
                        link,
                        {
                            "title": r.get("title"),
                            "parsed_date": r.get("parsed_date"),
                            "discarded": False,
                            "source_json": str(jf.relative_to(cache_root.parent)),
                        },
                    )
                for r in q.get("discarded") or []:
                    link = r.get("link")
                    if not link:
                        continue
                    add(
                        link,
                        {
                            "title": r.get("title"),
                            "parsed_date": r.get("parsed_date"),
                            "discarded": True,
                            "discard_reason": r.get("discard_reason"),
                            "source_json": str(jf.relative_to(cache_root.parent)),
                        },
                    )
            for f in data.get("fetched") or []:
                link = f.get("url")
                if not link:
                    continue
                add(
                    link,
                    {
                        "title": f.get("title"),
                        "fetched_status": f.get("status"),
                        "content_path": f.get("content_path"),
                        "discarded": False,
                    },
                )
    return index


def extract_citations(md: str) -> list[dict[str, str]]:
    cites: list[dict[str, str]] = []
    for m in LINK_RE.finditer(md):
        title, url = m.group(1), m.group(2)
        # grab nearby cite date if present within 80 chars after link
        tail = md[m.end() : m.end() + 80]
        dm = CITE_DATE_RE.search(tail)
        cites.append(
            {
                "title": title.strip(),
                "url": url.strip(),
                "cite_date": dm.group(1) if dm else "",
                "pos": str(m.start()),
            }
        )
    return cites


def verify_report(report_path: Path, cache_root: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not report_path.is_file():
        return [{"level": "error", "code": "missing_report", "message": f"文件不存在: {report_path}"}]

    md = report_path.read_text(encoding="utf-8")
    index = load_cache_urls(cache_root)
    seen: set[str] = set()

    for cite in extract_citations(md):
        url = cite["url"]
        key = normalize_url(url)
        if key in seen:
            continue
        seen.add(key)

        if key not in index:
            issues.append(
                {
                    "level": "error",
                    "code": "url_not_in_cache",
                    "message": f"引用 URL 不在当日检索缓存中: [{cite['title']}]({url})",
                }
            )
            continue

        meta = index[key]
        if meta.get("discarded"):
            reason = meta.get("discard_reason", "stale")
            issues.append(
                {
                    "level": "error",
                    "code": "discarded_source",
                    "message": f"引用了已丢弃的过期来源 ({reason}): [{cite['title']}]({url})",
                }
            )

        cache_title = (meta.get("title") or "").strip()
        cite_title = cite["title"]
        if cache_title and cite_title:
            if topic_mismatch(cite_title, cache_title):
                issues.append(
                    {
                        "level": "error",
                        "code": "topic_mismatch",
                        "message": (
                            f"引用主题与缓存页面不符（可能链错文）— 报告: «{cite_title}» "
                            f"缓存: «{cache_title}» ({url})"
                        ),
                    }
                )
            elif not _title_overlap(cite_title, cache_title):
                issues.append(
                    {
                        "level": "warn",
                        "code": "title_abbreviated",
                        "message": (
                            f"引用标题与缓存标题差异较大（若为缩写可忽略）: "
                            f"«{cite_title}» vs «{cache_title}»"
                        ),
                    }
                )

        parsed = meta.get("parsed_date") or ""
        cite_date = cite.get("cite_date") or ""
        if not cite_date:
            issues.append(
                {
                    "level": "warn",
                    "code": "missing_cite_date",
                    "message": f"引用缺少 `· YYYY-MM-DD` 日期: [{cite_title}]({url})",
                }
            )
        if parsed and cite_date and parsed != cite_date:
            issues.append(
                {
                    "level": "warn",
                    "code": "cite_date_mismatch",
                    "message": (
                        f"引用日期 {cite_date} 与来源解析日期 {parsed} 不一致: "
                        f"[{cite_title}]({url})"
                    ),
                }
            )

        if not meta.get("content_path"):
            issues.append(
                {
                    "level": "warn",
                    "code": "not_fetched",
                    "message": f"引用 URL 在结果中但没有 fetched 正文索引，数字无法自动追溯: [{cite_title}]({url})",
                }
            )

        fetched_status = meta.get("fetched_status")
        if fetched_status in {"blocked", "error"}:
            issues.append(
                {
                    "level": "warn",
                    "code": "fetch_unusable",
                    "message": f"来源抓取状态为 {fetched_status}，不得作为核心数字依据: [{cite_title}]({url})",
                }
            )
        elif fetched_status == "partial":
            issues.append(
                {
                    "level": "warn",
                    "code": "fetch_partial",
                    "message": f"来源仅部分抓取，只能作为辅助证据: [{cite_title}]({url})",
                }
            )

    issues.extend(structural_checks(report_path, md))
    return issues


def structural_checks(report_path: Path, md: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    if report_path.name == "report.md":
        facts_path = report_path.with_name("facts.md")
        facts_text = ""
        if not facts_path.is_file():
            issues.append(
                {
                    "level": "error",
                    "code": "missing_facts",
                    "message": f"个股报告缺少同目录 facts.md: {facts_path}",
                }
            )
        else:
            facts_text = facts_path.read_text(encoding="utf-8")
            issues.extend(verify_facts_file(facts_path, facts_text))
            issues.extend(verify_numbers_trace_to_facts(md, facts_text))

        fundamentals = section_text(md, "## 二、基本面与财务")
        if fundamentals:
            issues.extend(
                require_table_headers(
                    fundamentals,
                    ["口径", "数据日期", "来源等级", "来源"],
                    "fundamentals_table_header",
                    "基本面与财务表缺少必要列：口径、数据日期、来源等级、来源",
                )
            )

        judgment = section_text(md, "## 六、综合判断")
        if judgment and "可证伪条件" not in judgment:
            issues.append(
                {
                    "level": "warn",
                    "code": "missing_falsification_condition",
                    "message": "综合判断缺少“可证伪条件”，后续复盘难以判断逻辑是否失效",
                }
            )

    if report_path.name == "daily-research-report.md":
        macro = section_text(md, "### 今日关键变量")
        if macro:
            issues.extend(
                require_table_headers(
                    macro,
                    ["当前现值", "最新官方滞后数据", "机构预测", "来源"],
                    "macro_variable_header",
                    "今日关键变量表应区分当前现值、最新官方滞后数据、机构预测与来源",
                )
            )

    return issues


def verify_facts_file(facts_path: Path, facts_text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    required = ["来源等级", "原文摘录", "口径", "数据日期"]
    missing = [name for name in required if name not in facts_text]
    if missing:
        issues.append(
            {
                "level": "warn",
                "code": "facts_missing_columns",
                "message": f"{facts_path} 缺少事实表字段: {', '.join(missing)}",
            }
        )

    if not re.search(r"\|\s*[ABC]\s*\|", facts_text):
        issues.append(
            {
                "level": "warn",
                "code": "facts_missing_source_tier",
                "message": f"{facts_path} 未看到 A/B/C 来源等级，核心数字可靠性无法分层",
            }
        )
    return issues


def verify_numbers_trace_to_facts(md: str, facts_text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    report_numbers = sorted({normalize_number_token(m.group(0)) for m in CORE_NUMBER_RE.finditer(md)})
    if not report_numbers:
        return issues

    facts_compact = compact_number_text(facts_text)
    missing = [n for n in report_numbers if compact_number_text(n) not in facts_compact]
    if missing:
        preview = ", ".join(missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        issues.append(
            {
                "level": "warn",
                "code": "number_not_in_facts",
                "message": f"报告中部分核心数字未在 facts.md 中找到，需确认是否已入事实表: {preview}{suffix}",
            }
        )
    return issues


def require_table_headers(section: str, headers: list[str], code: str, message: str) -> list[dict[str, str]]:
    header_line = next((line for line in section.splitlines() if line.strip().startswith("|")), "")
    missing = [h for h in headers if h not in header_line]
    if not missing:
        return []
    return [
        {
            "level": "warn",
            "code": code,
            "message": f"{message}；缺少: {', '.join(missing)}",
        }
    ]


def section_text(md: str, heading: str) -> str:
    start = md.find(heading)
    if start == -1:
        return ""
    next_heading = re.search(r"\n#{2,3}\s+", md[start + len(heading) :])
    if not next_heading:
        return md[start:]
    return md[start : start + len(heading) + next_heading.start()]


def normalize_number_token(token: str) -> str:
    return re.sub(r"\s+", "", token.strip())


def compact_number_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


TOPIC_KW = re.compile(
    r"社零|零售总额|布伦特|brent|油价|原油|lpr|净息差|nim|cpi|ppi|"
    r"碳酸锂|猪价|iata|霍尔木兹|海峡",
    re.I,
)


def topic_mismatch(cite_title: str, cache_title: str) -> bool:
    """True when cite claims a macro topic but cached page title is clearly unrelated."""
    cite_topics = set(TOPIC_KW.findall(cite_title))
    if not cite_topics:
        return False
    cache_lower = cache_title.lower()
    for t in cite_topics:
        if t.lower() in cache_lower:
            return False
        # Chinese substring check
        if t in cache_title:
            return False
    return True


def _title_overlap(a: str, b: str) -> bool:
    """Share a meaningful token (>=4 CJK or >=5 Latin chars)."""
    tokens_a = set(re.findall(r"[\u4e00-\u9fff]{4,}|[A-Za-z]{5,}", a))
    tokens_b = set(re.findall(r"[\u4e00-\u9fff]{4,}|[A-Za-z]{5,}", b))
    return bool(tokens_a & tokens_b)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify report citations against search cache")
    parser.add_argument("report", type=Path, help="Path to report.md")
    parser.add_argument(
        "cache_root",
        type=Path,
        nargs="?",
        help="Path to _search-cache/ (default: sibling of report)",
    )
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    cache = args.cache_root
    if cache is None:
        cache = args.report.parent / "_search-cache"
        if not cache.is_dir() and args.report.parent.name != "_search-cache":
            # stock report: reports/DATE/sector/.../report.md
            for parent in args.report.parents:
                candidate = parent / "_search-cache"
                if candidate.is_dir():
                    cache = candidate
                    break

    issues = verify_report(args.report, cache)
    errors = [i for i in issues if i["level"] == "error"]
    warns = [i for i in issues if i["level"] == "warn"]

    for i in issues:
        prefix = "ERROR" if i["level"] == "error" else "WARN"
        print(f"{prefix}: {i['message']}", file=sys.stderr)

    if errors or (args.strict and warns):
        print(
            f"\nverify-report: FAILED — {len(errors)} error(s), {len(warns)} warning(s)",
            file=sys.stderr,
        )
        return 1

    print(f"verify-report: OK — {len(extract_citations(args.report.read_text(encoding='utf-8')))} citations checked")
    if warns:
        print(f"  ({len(warns)} warning(s), non-strict mode)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
