#!/usr/bin/env python3
"""Filter SerpApi results by freshness; classify queries for max-age rules.

产出仅供研究参考，不构成投资建议。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

# Max age (days) from report date — by query class
MAX_AGE_DAYS: dict[str, int] = {
    "spot": 7,          # 现价、今日油价、盘中报价
    "news": 30,         # 一般资讯
    "macro_stat": 45,   # 社零/CPI/PMI 等月度宏观
    "policy": 60,       # 政策文件（落地后变化慢）
    "earnings": 120,    # 季报/业绩
    "annual": 400,      # 年报
    "default": 45,
}

SPOT_KW = re.compile(
    r"today|spot\s+price|price\s+now|现价|今日|盘中|latest\s+price|"
    r"oil\s+prices?\s+today|crude\s+.*today",
    re.I,
)
EARNINGS_KW = re.compile(
    r"一季报|二季报|三季报|四季报|季报|半年报|年报|earnings|quarter|"
    r"q[1-4]\s*20|净利润|营收|financial\s+results",
    re.I,
)
ANNUAL_KW = re.compile(r"年报|annual\s+report|fy20|full.?year", re.I)
MACRO_STAT_KW = re.compile(
    r"社零|零售总额|cpi|ppi|pmi|gdp|工业增加值|失业率|通胀",
    re.I,
)
POLICY_KW = re.compile(r"政策|监管|央行|lpr|决议|条例|办法", re.I)

URL_DATE_PATTERNS = [
    re.compile(r"/(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})(?:/|[_\.]|$)"),
    re.compile(r"/(20\d{2})(\d{2})(\d{2})(?:/|[_\.]|$)"),
    re.compile(r"/article/(20\d{2})(\d{2})(\d{2})/"),
    re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/"),
]

SERp_DATE_PATTERNS = [
    re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})",
        re.I,
    ),
    re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})"),
]

MONTH_MAP = {
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

RELATIVE_PATTERNS = [
    (re.compile(r"(\d+)\s*minutes?\s+ago", re.I), "minutes"),
    (re.compile(r"(\d+)\s*hours?\s+ago", re.I), "hours"),
    (re.compile(r"(\d+)\s*days?\s+ago", re.I), "days"),
    (re.compile(r"(\d+)\s*weeks?\s+ago", re.I), "weeks"),
    (re.compile(r"(\d+)\s*months?\s+ago", re.I), "months"),
]


def parse_report_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def classify_query(query: str, kind: str) -> str:
    if SPOT_KW.search(query):
        return "spot"
    if ANNUAL_KW.search(query):
        return "annual"
    if EARNINGS_KW.search(query):
        return "earnings"
    if kind == "macro" and MACRO_STAT_KW.search(query):
        return "macro_stat"
    if POLICY_KW.search(query):
        return "policy"
    if kind == "macro":
        return "macro_stat"
    return "news"


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def dates_from_url(url: str) -> list[date]:
    out: list[date] = []
    for pat in URL_DATE_PATTERNS:
        for m in pat.finditer(url):
            g = m.groups()
            if len(g) == 3:
                y, mo, da = int(g[0]), int(g[1]), int(g[2])
                dt = _safe_date(y, mo, da)
                if dt:
                    out.append(dt)
    return out


def dates_from_text(text: str) -> list[date]:
    if not text:
        return []
    out: list[date] = []
    for pat in SERp_DATE_PATTERNS:
        for m in pat.finditer(text):
            g = m.groups()
            if len(g) == 3 and g[0].isdigit():
                y, mo, da = int(g[0]), int(g[1]), int(g[2])
            else:
                mo = MONTH_MAP.get(g[0][:3].lower(), 0)
                da, y = int(g[1]), int(g[2])
            dt = _safe_date(y, mo, da)
            if dt:
                out.append(dt)
    return out


def date_from_relative(text: str, report_date: date) -> Optional[date]:
    if not text:
        return None
    for pat, unit in RELATIVE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        n = int(m.group(1))
        if unit == "minutes":
            return report_date
        if unit == "hours":
            return report_date
        if unit == "days":
            return report_date - timedelta(days=n)
        if unit == "weeks":
            return report_date - timedelta(weeks=n)
        if unit == "months":
            return report_date - timedelta(days=n * 30)
    return None


def effective_date(result: dict[str, Any], report_date: date) -> Optional[date]:
    candidates: list[date] = []

    serp_date = result.get("date")
    if isinstance(serp_date, str) and serp_date.strip():
        rel = date_from_relative(serp_date, report_date)
        if rel:
            candidates.append(rel)
        candidates.extend(dates_from_text(serp_date))

    link = result.get("link") or ""
    candidates.extend(dates_from_url(link))

    for field in ("title", "snippet"):
        candidates.extend(dates_from_text(result.get(field) or ""))

    if not candidates:
        return None

    # Prefer newest plausible date not after report_date
    valid = [d for d in candidates if d <= report_date]
    if valid:
        return max(valid)
    return min(candidates)


def url_path_year(url: str) -> Optional[int]:
    years = [d.year for d in dates_from_url(url)]
    return max(years) if years else None


def should_keep(
    result: dict[str, Any],
    query: str,
    report_date: date,
    kind: str,
) -> tuple[bool, str, Optional[str]]:
    qclass = classify_query(query, kind)
    max_age = MAX_AGE_DAYS[qclass]
    eff = effective_date(result, report_date)
    link = result.get("link") or ""

    if eff and eff > report_date:
        return False, "future_date", eff.isoformat()

    url_year = url_path_year(link)
    if url_year and url_year < report_date.year and qclass in ("spot", "news", "macro_stat"):
        return False, f"url_year_{url_year}_before_report_year", eff.isoformat() if eff else None

    if eff is None:
        if qclass == "spot":
            return False, "no_date_for_spot_query", None
        if qclass in ("news", "macro_stat"):
            return False, "no_parseable_date", None
        # earnings/annual: allow but flag — filings often lack Serp date
        return True, "date_unknown_allowed", None

    age = (report_date - eff).days
    if age > max_age:
        return False, f"stale_{age}d_max_{max_age}d", eff.isoformat()

    return True, "ok", eff.isoformat()


def filter_results(
    results: list[dict[str, Any]],
    query: str,
    report_date: date,
    kind: str,
) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []

    for r in results:
        keep, reason, parsed = should_keep(r, query, report_date, kind)
        enriched = dict(r)
        enriched["parsed_date"] = parsed
        enriched["discard_reason"] = None if keep else reason
        if keep:
            kept.append(enriched)
        else:
            discarded.append(enriched)

    return {
        "query_class": classify_query(query, kind),
        "max_age_days": MAX_AGE_DAYS[classify_query(query, kind)],
        "kept": kept,
        "discarded": discarded,
    }


def cmd_filter(args: argparse.Namespace) -> int:
    payload = json.load(sys.stdin)
    results = payload if isinstance(payload, list) else payload.get("results", [])
    report_date = parse_report_date(args.report_date)
    out = filter_results(results, args.query, report_date, args.kind)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Filter search results by date freshness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_filter = sub.add_parser("filter", help="Filter SerpApi organic results")
    p_filter.add_argument("--report-date", required=True)
    p_filter.add_argument("--kind", choices=["stock", "macro"], required=True)
    p_filter.add_argument("--query", required=True)
    p_filter.set_defaults(func=cmd_filter)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
