#!/usr/bin/env python3
"""Emit search-fetch jobs from config/industries.yaml (TSV: kind\\tkey\\tquery).

产出仅供研究参考，不构成投资建议。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = ROOT / "config" / "industries.yaml"

# AI 板块 yaml 未配 macro 时的默认宏观 query
DEFAULT_AI_MACRO = [
    "NVIDIA AI chip demand capex outlook {year}",
    "China AI semiconductor Cambricon 寒武纪 {year}",
    "Hong Kong AI IPO Zhipu MiniMax {year}",
    "global AI large model funding valuation {year}",
]

DEFAULT_STOCK_FINANCIAL = [
    "{name} {code} {latest_quarter} 净利润 营收",
    "{name} {last_fy} 年报 分红 PE PB 估值",
]


def latest_report_quarter(d: dt.date) -> str:
    """Return the latest broadly disclosed reporting period for search queries."""
    if d.month <= 4:
        return f"{d.year - 1} 年报"
    if d.month <= 8:
        return f"{d.year} 一季报"
    if d.month <= 10:
        return f"{d.year} 半年报"
    return f"{d.year} 三季报"


def subst(
    template: str,
    *,
    name: str,
    code: str,
    alias: str,
    year: int,
    month: int,
    latest_quarter: str,
    last_fy: int,
) -> str:
    return (
        template.replace("{name}", name)
        .replace("{code}", code)
        .replace("{alias}", alias)
        .replace("{year}", str(year))
        .replace("{month}", f"{month:02d}")
        .replace("{latest_quarter}", latest_quarter)
        .replace("{last_fy}", str(last_fy))
    )


def emit(kind: str, key: str, query: str) -> None:
    q = query.strip()
    if q:
        print(f"{kind}\t{key}\t{q}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--macro-only", action="store_true")
    ap.add_argument("--stocks-only", action="store_true")
    ap.add_argument("--sector", help="只输出指定 sector（如 石油、AI）")
    ap.add_argument("--code", help="只输出指定股票 code（自动跳过宏观）")
    ap.add_argument(
        "--no-default-stock-financial",
        action="store_true",
        help="不追加默认财报/估值 query",
    )
    ap.add_argument(
        "--no-default-ai-macro",
        action="store_true",
        help="AI 板块不追加默认宏观 query",
    )
    args = ap.parse_args()

    if args.code:
        args.macro_only = False
        args.stocks_only = True

    d = dt.date.fromisoformat(args.date)
    year, month = d.year, d.month
    latest_quarter = latest_report_quarter(d)
    last_fy = year - 1

    data = yaml.safe_load(args.yaml.read_text(encoding="utf-8"))
    industries = data.get("industries") or []

    for ind in industries:
        sector = ind.get("sector", "")
        if args.sector and sector != args.sector:
            continue

        macro = ind.get("macro") or {}
        if not args.stocks_only:
            queries = list(macro.get("queries") or []) if macro.get("enabled") else []
            if sector == "AI" and not queries and not args.no_default_ai_macro:
                queries = [
                    subst(
                        q,
                        name="",
                        code="",
                        alias="",
                        year=year,
                        month=month,
                        latest_quarter=latest_quarter,
                        last_fy=last_fy,
                    )
                    for q in DEFAULT_AI_MACRO
                ]
            for q in queries:
                emit(
                    "macro",
                    sector,
                    subst(
                        q,
                        name="",
                        code="",
                        alias="",
                        year=year,
                        month=month,
                        latest_quarter=latest_quarter,
                        last_fy=last_fy,
                    ),
                )

        if args.macro_only:
            continue

        news_templates = list(ind.get("news_queries") or [])
        linkage_templates = list((ind.get("macro") or {}).get("linkage_queries") or [])
        extra_fin = [] if args.no_default_stock_financial else DEFAULT_STOCK_FINANCIAL

        for sub in ind.get("sub_sectors") or []:
            for stock in sub.get("stocks") or []:
                code = str(stock.get("code", "")).strip()
                name = str(stock.get("name", "")).strip()
                aliases = [str(a).strip() for a in stock.get("aliases") or [] if str(a).strip()]
                if not code:
                    continue
                if args.code and code != args.code:
                    continue

                seen: set[str] = set()
                for tpl in news_templates + linkage_templates + extra_fin:
                    q = subst(
                        tpl,
                        name=name,
                        code=code,
                        alias="",
                        year=year,
                        month=month,
                        latest_quarter=latest_quarter,
                        last_fy=last_fy,
                    )
                    if q not in seen:
                        seen.add(q)
                        emit("stock", code, q)
                for alias in aliases:
                    alias_query = f"{name} {alias} {code} {latest_quarter} 业绩 估值"
                    q = subst(
                        alias_query,
                        name=name,
                        code=code,
                        alias=alias,
                        year=year,
                        month=month,
                        latest_quarter=latest_quarter,
                        last_fy=last_fy,
                    )
                    if q not in seen:
                        seen.add(q)
                        emit("stock", code, q)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
