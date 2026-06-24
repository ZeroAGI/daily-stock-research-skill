#!/usr/bin/env python3
"""Fetch URL and extract readable article text for search cache.

产出仅供研究参考，不构成投资建议。
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

MAX_CHARS = int(__import__("os").environ.get("MAX_CHARS", "500000"))
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BLOCK_PATTERNS = [
    r"just a moment",
    r"enable javascript and cookies",
    r"cf_chl_opt",
    r"challenge-platform",
    r"access denied",
    r"yahoo.+mainland china",
    r"没有启用javascript",
]

NOISE_LINE = re.compile(
    r"^(财经首页|新浪首页|读取中|自选股|行情中心|上证指数|深圳成指|沪深300|"
    r"热点推荐|下载公告|公告日期|公司简称|@charset|function\s*\(|var\s+\w+\s*=)",
    re.I,
)

FIN_KW = re.compile(
    r"(亿元|万美元|净利润|营业收入|营收|同比|环比|股息|分红|PE|市盈率|"
    r"billion|revenue|earnings|EPS|毛利率|产量|桶|mb/d)",
    re.I,
)


def fetch_bytes(url: str, timeout: int = 30) -> tuple[bytes, Optional[str]]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get_content_charset()


def decode_html(raw: bytes, hint: Optional[str]) -> str:
    for enc in filter(None, [hint, "utf-8", "gb18030", "gbk", "gb2312", "latin-1"]):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def meta_content(html: str, *names: str) -> Optional[str]:
    for name in names:
        for pat in (
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']',
        ):
            m = re.search(pat, html, re.I | re.S)
            if m:
                return html_lib.unescape(m.group(1).strip())
    return None


def json_ld_bodies(html: str) -> list[str]:
    bodies: list[str] = []
    for m in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue

        def walk(obj):
            if isinstance(obj, dict):
                for key in ("articleBody", "description", "text"):
                    val = obj.get(key)
                    if isinstance(val, str) and len(val) > 60:
                        bodies.append(html_lib.unescape(val))
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)
    return bodies


def script_template_fields(html: str) -> list[str]:
    out: list[str] = []
    for field in ("shareDes", "content", "articleContent", "mainContent"):
        for m in re.finditer(rf"{field}\s*=\s*`([^`]{{40,}})`", html, re.S):
            out.append(html_lib.unescape(m.group(1).strip()))
    return out


def strip_boilerplate(html: str) -> str:
    html = re.sub(r"<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<(script|style|noscript|svg|iframe)[^>]*/>", " ", html, flags=re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return html


def tag_text(fragment: str) -> str:
    fragment = strip_boilerplate(fragment)
    fragment = re.sub(r"</(p|div|h[1-6]|li|tr|td|article|section|br)>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", fragment)
    return html_lib.unescape(text)


def clean_lines(text: str, min_len: int = 8) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < min_len or NOISE_LINE.search(line):
            continue
        if len(line) > 300 and line.count("{") > 5:
            continue
        lines.append(line)
    return lines


def html_to_text(html: str) -> str:
    return "\n".join(clean_lines(tag_text(html)))


def financial_blocks(html: str) -> str:
    """Pull paragraphs with financial keywords (works well on Sina/Eastmoney bulletins)."""
    chunks: list[str] = []
    for m in re.finditer(r"<(?:td|div|p|span)[^>]*>([^<]{40,8000})</", html, re.I):
        t = html_lib.unescape(re.sub(r"\s+", " ", m.group(1)).strip())
        if FIN_KW.search(t) and not NOISE_LINE.search(t):
            chunks.append(t)
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        key = c[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return "\n\n".join(out)


def site_specific(html: str, url: str) -> list[str]:
    host = urlparse(url).netloc.lower()
    out: list[str] = []

    if "cls.cn" in host:
        for m in re.finditer(
            r'<div[^>]+class="[^"]*(?:c-de0422|f-s-20)[^"]*"[^>]*>(.*?)</div>',
            html,
            re.I | re.S,
        ):
            t = tag_text(m.group(1)).strip()
            if len(t) > 30:
                out.append(t)

    if "finance.sina.com.cn" in host or "money.finance.sina.com.cn" in host:
        fb = financial_blocks(html)
        if fb:
            out.append(fb)

    if "eastmoney.com" in host or "10jqka.com.cn" in host:
        fb = financial_blocks(html)
        if fb:
            out.append(fb)

    if "nvidianews.nvidia.com" in host:
        desc = meta_content(html, "og:description", "description")
        if desc:
            out.append(desc)
        return out  # SPA 页不继续解析整页导航

    if "prnewswire.com" in host:
        for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.I | re.S):
            t = tag_text(m.group(1)).strip()
            if len(t) > 60:
                out.append(t)

    return out


def pick_article_region(html: str) -> str:
    patterns = [
        r"<article[^>]*>(.*?)</article>",
        r'<div[^>]+id=["\'][^"\']*(?:article|content|body|main)[^"\']*["\'][^>]*>(.*?)</div>',
        r'<div[^>]+class="[^"]*(?:article-body|article-content|post-content|entry-content|detail-content)[^"]*"[^>]*>(.*?)</div>',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I | re.S)
        if m and len(m.group(1)) > 120:
            return m.group(1)
    return html


def is_blocked(html: str) -> bool:
    probe = strip_boilerplate(html)[:8000].lower()
    return any(re.search(p, probe, re.I) for p in BLOCK_PATTERNS)


def meaningful_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def merge_parts(parts: list[str]) -> str:
    seen: set[str] = set()
    merged: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        key = p[:160]
        if key in seen:
            continue
        seen.add(key)
        merged.append(p)
    return "\n\n---\n\n".join(merged).strip()


def extract(url: str, raw_html: str) -> tuple[str, str]:
    if is_blocked(raw_html):
        desc = meta_content(raw_html, "og:description", "description", "twitter:description")
        if desc and meaningful_len(desc) > 40:
            return "partial", f"[meta] {desc}"
        return "blocked", ""

    parts: list[str] = []

    parts.extend(site_specific(raw_html, url))
    parts.extend(json_ld_bodies(raw_html))
    parts.extend(script_template_fields(raw_html))

    # meta 作为补充，避免 SPA 页只有导航文本
    desc = meta_content(raw_html, "og:description", "description", "twitter:description")
    if desc and not any(desc[:80] in p for p in parts):
        parts.append(desc)

    region = pick_article_region(raw_html)
    article_text = html_to_text(region)
    if meaningful_len(article_text) > 150:
        nav_hits = len(re.findall(r"财经首页|行情中心|自选股|PLATFORMS|Autonomous Machines", article_text))
        fin_hits = len(FIN_KW.findall(article_text))
        if fin_hits >= 2 and nav_hits <= 2:
            parts.append(article_text)
        elif not parts and nav_hits <= 3:
            parts.append(article_text)

    body = merge_parts(parts)
    ml = meaningful_len(body)

    if ml > 500:
        status = "ok"
    elif ml > 100:
        status = "partial"
    elif ml > 0:
        status = "partial"
    else:
        return "error", ""

    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS] + "\n\n…[truncated]"
    return status, body


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: fetch-extract.py <url>", file=sys.stderr)
        return 2
    url = sys.argv[1]
    try:
        raw, ctype = fetch_bytes(url)
        html = decode_html(raw, ctype)
        status, body = extract(url, html)
        print(json.dumps({"status": status, "body": body, "chars": len(body)}, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as e:
        print(json.dumps({"status": "error", "body": f"HTTP {e.code}", "chars": 0}))
        return 0
    except Exception as e:
        print(json.dumps({"status": "error", "body": str(e), "chars": 0}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
