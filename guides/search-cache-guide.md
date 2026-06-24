# 检索与网页抓取缓存规范

> **免责声明**：检索缓存与基于缓存撰写的报告仅供研究参考，**不构成投资建议**。

## 路径

当日缓存位于 `reports/<YYYY-MM-DD>/_search-cache/`：

```
reports/<YYYY-MM-DD>/_search-cache/
  macro/
    {topic}.json                 # SerpApi 摘要结果
    fetched/                     # 宏观链接正文（可选）
      {url-hash}.md
  stocks/
    {code}.json                  # SerpApi 摘要 + fetched 索引
    {code}/fetched/
      {url-hash}.md              # 抓取正文（Markdown 纯文本摘要）
```

## SerpApi 层：`{code}.json`

```json
{
  "queries": [
    {
      "id": "a1b2c3d4e5f6a7b8",
      "q": "海天味业 603288 2026 一季报 净利润",
      "searched_at": "2026-06-24T12:00:00Z",
      "filter_meta": { "query_class": "earnings", "max_age_days": 120 },
      "results": [
        {
          "title": "…",
          "link": "https://…",
          "snippet": "…",
          "date": null,
          "parsed_date": "2026-04-29",
          "discard_reason": null
        }
      ],
      "discarded": [
        {
          "title": "…",
          "link": "https://…",
          "snippet": "…",
          "parsed_date": "2025-11-25",
          "discard_reason": "url_year_2025_before_report_year"
        }
      ]
    }
  ],
  "fetched": [ … ]
}
```

- 同日补检索：**merge** 新 `queries[]` 条目，不覆盖旧 query；每次检索写入唯一 `id`，并发过滤/fetch 必须按该 `id` 回写，禁止依赖 `queries[-1]`。
- `content_path` 相对 `_search-cache/`。
- **`discarded`**：被 `date-filter.py` 判定过期的 SerpApi 结果；**不 fetch、禁止写入报告**。

## 时效过滤（`date-filter.py`）

`search-fetch.sh` 在 SerpApi 返回后、fetch 前自动调用。按 query 类型与报告日期 `YYYY-MM-DD` 判定：

| query 类型 | 判定依据 | 最大龄期（天） |
|------------|----------|----------------|
| `spot` | today/现价/今日油价等 | **7** |
| `news` | 默认个股资讯 | **30** |
| `macro_stat` | 社零/CPI/PMI/GDP 等 | **45** |
| `policy` | 政策/监管/LPR | **60** |
| `earnings` | 季报/业绩 | **120** |
| `annual` | 年报 | **400** |

额外硬规则：
- URL 路径年份 **< 报告年份** 的 spot/news/macro_stat → **丢弃**（防 2025 旧稿混入 2026 报告）
- spot 类 query 无法解析日期 → **丢弃**
- news/macro_stat 无法解析日期 → **丢弃**
- 解析日期 **> 报告日** → 丢弃

每条 kept 结果写入 `parsed_date`（ISO `YYYY-MM-DD`）；报告引用日期须与此一致。

手动复现过滤：

```bash
jq -c '.queries[-1].results' macro/消费.json \
  | python3 date-filter.py filter --report-date 2026-06-24 --kind macro \
      --query "社会消费品零售总额 2026 5月"
```

## 网页抓取层：`fetched/{hash}.md`

```markdown
# {title}
- **URL**: {url}
- **Fetched**: {ISO8601}
- **Status**: ok | partial | blocked | error

{正文：优先 trafilatura/站点规则/JSON-LD/meta 提取，截断至 ~15000 字符}

## SerpApi Snippet（检索摘要）
{当 Status 非 ok 时自动附加 snippet}
```

**Status 含义**：
- `ok` — 正文提取成功（财务段落/公告/文章）
- `partial` — 仅 meta 或短摘要（SPA/登录墙页面）
- `blocked` — Cloudflare/Yahoo 等区域限制
- `error` — 抓取失败

抓取实现：[`fetch-extract.py`](../scripts/fetch-extract.py)；批量检索：[`batch-search-fetch.sh`](../scripts/batch-search-fetch.sh) `YYYY-MM-DD`；单条：[`search-fetch.sh`](../scripts/search-fetch.sh)

## 使用规则

1. **先缓存、后写报告** — 调整报告只读 `_search-cache`，除非用户要求重新检索/抓取。
2. **引用必须可点击且可验证** — `[标题](url) · YYYY-MM-DD`；数字优先来自 `fetched` 正文；撰写后运行 `verify-report.py`（见 [review-guide.md](review-guide.md)）。
3. **禁止引用 discarded** — 仅 `results`（`discard_reason` 为空）与 `fetched` 可作来源。
4. **抓取优先级** — 每个标的 Top 5 条：公司公告 / 交易所 / 主流财经媒体 PDF 摘要页；跳过登录墙、纯行情页。
5. **来源分级写入事实表** — A：公司公告/交易所/监管披露/公司官网/官方统计；B：主流财经媒体/券商研报/行业协会/专业机构；C：行情聚合页/搜索摘要/转载页。核心财务与估值数字不得只依赖 C 级来源。
6. **抓取状态约束** — `ok` 可作核心来源；`partial` 只能辅助；`blocked` / `error` 不得作为核心数字依据。
7. **Agent 维护** — **搜索 query 词**、**报告模板**由 Agent 按时效手写更新；**禁止**用代码生成报告正文。
8. **代码仅用于检索** — 见 [batch-search-fetch.sh](../scripts/batch-search-fetch.sh) / [search-fetch.sh](../scripts/search-fetch.sh)；不得用于批量写 `report.md`。

## 并行与环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `PARALLEL_JOBS` | 8 | `batch-search-fetch.sh` 并行 query 数 |
| `FETCH_PARALLEL` | 5 | 单条 query 内并行 URL 抓取数 |
| `MAX_FETCH` | 5 | 每条 query 最多抓取链接数 |
| `MAX_CHARS` | 500000 | 单页正文上限 |
| `FORCE_REFETCH` | 0 | 1=忽略已有 `fetched/*.md` |

同 `{code}.json` / `macro/{topic}.json` 的并发写入由 `json-flock.py` 串行化，不同 KEY 之间无锁竞争。

## 个股报告头部

```markdown
> **检索缓存**：[`603288.json`](...) · [`fetched/`](...)
```
