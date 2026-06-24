---
name: daily-stock-research
description: >-
  基于 config/industries.yaml 股票池：Step2 按时效更新 queries → SerpApi 检索+链接抓取（可脚本、落盘缓存）→ Agent 先写个股报告、后写整体报告。当日全部产出落盘于 reports/{date}/。引用须含 URL 超链接。严禁用代码生成报告正文。所有产出仅供研究参考，不构成投资建议。
---

# 每日股票池研究报告

> **免责声明**：本 Skill 及全部产出（事实表、个股报告、日报、经验库）仅供研究参考，**不构成投资建议**。

## 核心原则

### 代码边界（严格执行）

| 允许用代码/脚本 | **严禁**用代码 |
|-----------------|----------------|
| SerpApi 检索（curl / [search-fetch.sh](scripts/search-fetch.sh)）(fetch 不要截断！) | 批量生成 `report.md` |
| 对搜索结果 `link` 抓取正文并写入 `_search-cache/**/fetched/` | 批量生成 `daily-research-report.md` |
| 合并/追加缓存 JSON | `python`、项目 pipeline、任意「报告生成器」 |

**报告正文、估值算法及其结论、高低估分析** — 必须由 Agent 阅读缓存后**手写** Markdown。

### 其他原则

1. **当日产出统一落盘** — 报告、检索缓存等**所有当日新增文件**均写入 `reports/<YYYY-MM-DD>/`（见 Step 3）。经验库 `reports/_lessons/` 为跨日累积，不在此列。
2. **检索 + 抓取必须落盘** — SerpApi 摘要 → `_search-cache/stocks/{code}.json`；链接正文 → `_search-cache/stocks/{code}/fetched/*.md`（见 [guides/search-cache-guide.md](guides/search-cache-guide.md)）。改报告**先读缓存**。
3. **撰写顺序** — **先**各股 `report.md`，**最后** `daily-research-report.md`。
4. **Query 与模板由 Agent 维护** — Step 2 根据**当日时效**更新 `industries.yaml` 中的事件型 queries；常规年份/月份/报告期优先使用 `{year}`、`{month}`、`{latest_quarter}`、`{last_fy}` 占位符，减少每日手改；报告模板 `templates/report-template.md` / `templates/stock-report-template.md` / `templates/facts-template.md` 由 Agent 手动维护；**不**用脚本改模板。
5. **以 `config/industries.yaml` 为股票池来源** — `sector → sub_sector → stocks`。
6. **宏观共享、微观分层** — 板块宏观检索+抓取缓存后，再逐股微观检索+抓取。
7. **引用** — 每条信息 `[标题](url) · YYYY-MM-DD`；**url 与标题必须来自当日缓存且 fetch 正文可印证**；优先引用 `fetched` 正文中的数据。
8. **时效过滤（强制）** — `search-fetch.sh` 自动丢弃过期 SerpApi 结果（写入 `discarded`，不 fetch）；报告**禁止**引用 `discarded` 链接。规则见 [guides/search-cache-guide.md](guides/search-cache-guide.md) §时效。
9. **撰写后 Review（强制）** — 每只 `report.md` 与 `daily-research-report.md` 写完后立即执行 [guides/review-guide.md](guides/review-guide.md) 核对 + `verify-report.py`；未通过不得进入下一步。
10. **彼得林奇公司分类先于估值（强制）** — 个股估值前必须先判断公司属于：缓慢增长型公司、稳定增长型公司、快速增长型公司、周期型公司、隐蔽资产型公司、困境反转型公司；分类需有财务/业务/行业周期依据，并决定后续估值锚（如股息与现金流、成长 PEG、周期底部/顶部盈利、资产重估、反转兑现概率等）。分类后的必填输出：三类增长型公司写当前增长率；周期型公司写当前位置（衰退/复苏/过热/滞胀）；隐蔽资产型公司写资产类型和价值；困境反转型公司写反转措施和预期收益。
11. **事实表先于报告（强制）** — 个股报告正文前必须先手写 `facts.md`，把关键财务、估值、资讯、宏观传导变量逐条整理为“数值 + 口径 + 数据日期 + 来源 + 原文摘录”；报告正文只能引用 `facts.md` 已确认的核心数字。
12. **来源分级（强制）** — 财务与估值核心数字优先使用一手/准一手来源：公司公告、交易所、监管披露、公司官网/IR；主流财经媒体和券商研报仅作补充；SerpApi snippet、行情聚合页、抓取失败页不得作为核心数字来源。
13. **复盘** — 更新 `reports/_lessons/lessons-learned.md`。
14. **免责声明（强制）** — 每份 `facts.md`、`report.md`、`daily-research-report.md` 及 `lessons-learned.md` 末尾须注明「不构成投资建议」。
15. **事件驱动因子时效检查（强制）** — 凡高/低估分析引用**地缘危机、停火/停战/协议、政策落地、监管变化**等「状态性」宏观事件作为核心支撑，且该事件最新缓存来源距今 **>45 天**，必须在撰写前追加一条事件现状 query（含当月年月，如 `霍尔木兹海峡危机 最新 2026年6月`）并 fetch 前 2 条结果，再用最新状态更新分析结论。引用中标注 `【事件当前状态：{仍持续 | 已解除 | 谈判中 | 已变化} · YYYY-MM-DD】`。

## 工作流

```
Task Progress:
- [ ] 1. 读取 config/industries.yaml 与 config/settings.yaml
- [ ] 2. 根据当日时效更新 industries.yaml 中的 queries
- [ ] 3. 读取历史报告与经验库（回看 7 日）
- [ ] 4. 宏观检索 + **抓取 Top5 链接正文** → `_search-cache/macro/`（过期结果自动丢弃）
- [ ] 5. 逐股检索 + **抓取 Top5 链接正文** → `_search-cache/stocks/{code}.json` + `fetched/`
- [ ] 6. 逐股整理 facts.md（来源分级、口径、原文摘录、冲突来源说明）
- [ ] 7. 对照缓存与历史，复盘验证既往判断
- [ ] 8. **先**撰写各股 report.md → **每只写完即 Review**（verify-report + 人工核对）
- [ ] 9. **最后**撰写 daily-research-report.md → **整体 Review**（verify-report --strict）
- [ ] 10. 更新 reports/_lessons/lessons-learned.md
```

### Step 1：读取配置

首次使用：从 `config/*.example.yaml` 复制为 `config/industries.yaml` 与 `config/settings.yaml`（详见仓库 [README.md](README.md)）。

读取：
- `config/industries.yaml` — 行业、子行业、个股、宏观 queries、news_queries（query 由 Agent 根据时效维护）
- `config/settings.yaml` — SerpApi 端点（默认 `https://serpapi.com/search.json`）

### Step 2：更新 industries.yaml queries 时效

**目标**：确保 `config/industries.yaml` 中所有 sector 的 `macro.queries`、`linkage_queries`、`news_queries` 与今日日期（`{YYYY-MM-DD}`）保持一致，再进行检索。常规时效字段优先写成占位符，由 `expand-queries.py` 展开。

**检查与更新规则**：

1. **年份 / 季度替换**：扫描全部 queries，将常规年份（如 `2026`）尽量替换为 `{year}`；将常规季度/报告期尽量替换为 `{latest_quarter}`（今日 2026-06-24 → `2026 一季报`）；全年年报参考 `{last_fy}`（今日 2026-06-24 → `2025`）。
2. **月份关键词**：含月份的 queries（如 `June 2026`、`2026年6月`）若不是特定历史事件，优先替换为 `{month}`/`{year}` 占位符；事件现状 query 可保留明确年月。
3. **事件驱动 query**：
   - **新增**：近期出现重大宏观事件（地缘危机升级、OPEC 决议、央行政策、重要行业政策落地）时，为对应 sector 追加含当月的事件现状 query（如 `"霍尔木兹海峡 最新动态 2026年6月"`）。
   - **移除 / 注释**：已明确结束或解除的事件 query（如停战协议已签署、临时政策已退出）可删除或注释说明。
4. **补全缺失 queries**：若某 sector 只有 `macro: enabled: true` 而无 `queries:` 字段，参照行业特征补写 2–4 条当季宏观 queries（参见 § 行业传导速查）。
5. **写回文件**：直接编辑 `config/industries.yaml` 对应 queries 字段；**不用脚本**，由 Agent 手动修改。
6. **记录变更**：在 Task Progress 旁注明哪些 sector 的 queries 做了更新及原因（一行简述即可）。

> **示例**（今日 2026-06-24）：`"Brent crude oil price today outlook {year}-{month}"` 会展开到当月；`"{name} {code} {latest_quarter} 净利润 营收"` → `"中国海油 600938 2026 一季报 净利润 营收"`；`"{name} {last_fy} 年报 分红"` → `"中国海油 2025 年报 分红"`。

### Step 3：读取历史与经验库

1. 读取 `reports/_lessons/lessons-learned.md`（分析偏见校正、待验证清单）。
2. 按日期倒序扫描 `reports/<YYYY-MM-DD>/daily-research-report.md`，默认回看 **7 日**。
3. 同目录下 `reports/<YYYY-MM-DD>/<sector>/**/report.md` 个股报告一并纳入对照。
4. **无历史日报** → 首跑模式：今日判断作基线，提取可验证条目写入待验证清单（详见 [guides/retrospective-guide.md](guides/retrospective-guide.md)）。

### Step 4：输出路径（当日目录 `reports/<YYYY-MM-DD>/`）

**当日根目录** — 报告、检索缓存等**所有当日新增文件**均在此目录下：

```
reports/<YYYY-MM-DD>/
  daily-research-report.md          # 整体报告（必读入口，最后撰写）
  <sector>/<sub_sector>/<name>/facts.md    # 个股事实表（报告前手写）
  <sector>/<sub_sector>/<name>/report.md   # 个股详细报告（每只 yaml 池内个股一份）
  _search-cache/                    # 检索与抓取缓存（见 guides/search-cache-guide.md）
    macro/{topic}.json
    macro/fetched/*.md
    stocks/{code}.json
    stocks/{code}/fetched/*.md
```

**经验库**（跨日累积，不在当日目录内）：
```
reports/_lessons/lessons-learned.md
```
批量检索+抓取可用：
- **[batch-search-fetch.sh](scripts/batch-search-fetch.sh)** — 从 `industries.yaml` 展开全部任务，`parallel -j N` 并行（推荐）
- **[search-fetch.sh](scripts/search-fetch.sh)** — 单条 query（`MAX_FETCH=5` 默认）

规范见 [guides/search-cache-guide.md](guides/search-cache-guide.md)。

**链接规则**：总览表中每只个股链到对应 `report.md`；个股报告顶部链回 `daily-research-report.md`。

### Step 5：宏观检索与链接抓取

对每个 `sector` 执行 SerpApi（query 由 Agent 按**当日年月**拟定，可更新 yaml `macro.queries`，如有相关新事件也可以检索相关事实）：

1. 写入 `_search-cache/macro/{sector}.json`
2. **时效过滤**：`date-filter.py` 按 query 类型丢弃过期结果 → `discarded[]`，**不 fetch**
3. 对过滤后 Top 2–3 条 **fetch 正文** → `macro/fetched/{hash}.md`，索引写入 JSON `fetched[]`
4. 分析时**仅读** `results`（非 discarded）与 `fetched` 正文；snippet 仅作线索

### Step 6：微观检索与链接抓取

对 yaml 池内**每一只个股**（query 含 `{year}` / `{month}` / `{latest_quarter}` / `{last_fy}` 等占位符，由 `expand-queries.py` 展开）：

**资讯 query 示例**（按日替换）：
- `{name} {code} 2026 一季报 净利润 营收`
- `{name} 2025 年报 分红`
- `{name} PE PB 估值 2026`

**权威来源定向补抓 query（强制补充）**：
- `{name} {code} {latest_quarter} 财报 公告 site:sse.com.cn OR site:szse.cn`
- `{name} {code} {last_fy} 年报 公告 site:sse.com.cn OR site:szse.cn`
- `{name} {code} investor relations annual report`
- `{name} {code} PE PB 股息率 数据日期`

流程：
1. SerpApi → `stocks/{code}.json`（`queries[]` 可多条 merge）
2. **时效过滤** → 过期写入 `discarded[]`，不 fetch
3. 抓取公告/研报/财经媒体链接 → `stocks/{code}/fetched/*.md`
4. 抓取失败记 `status: error`，不编造正文
5. **事件状态核查**（强制）：读取历史报告或宏观缓存，识别当前个股高/低估逻辑是否依赖「地缘危机、停火协议、政策变化」等进行中事件。若依赖且现有相关来源 >45 天，**立即追加事件现状 query**（含当月，如 `霍尔木兹海峡 美伊谈判 最新 2026年6月`），fetch 前 2 条，记入 `fetched/`。否则该高/低估理由不得援引该事件前提。

效率低时对多标的循环调用 `search-fetch.sh`；**不得**用脚本写报告。

### Step 6.5：事实表 `facts.md`（强制）

每只股票在 `report.md` 前先手写 `facts.md`，路径与个股报告同目录：

```markdown
# {name}（{code}）事实表

| 类型 | 指标/事件 | 数值/结论 | 口径 | 数据日期 | 来源等级 | 来源 | 原文摘录 |
|------|-----------|-----------|------|----------|----------|------|----------|
| 财务 | 营收 |  | 2026 Q1 / FY / TTM 等 | YYYY-MM-DD | A/B/C | [标题](url) · YYYY-MM-DD | “...” |
```

来源等级：
- **A**：公司公告、交易所、监管披露、公司官网/IR、官方统计机构。
- **B**：主流财经媒体、券商研报、行业协会、EIA/IEA/OPEC 等专业机构。
- **C**：行情聚合页、搜索摘要、博客/转载页；只能作线索，不得作为核心数字来源。

事实表规则：
- 财务数字、估值指标、分红、核心宏观变量必须进入 `facts.md` 后才能写入报告。
- 每条核心数字需写清口径：Q1/FY/TTM、同比/环比、静态/前瞻、数据日期。
- 同一指标出现冲突来源时，必须新增“冲突说明”行，写明差异口径、采用值与原因。
- `fetched_status` 为 `partial` 的来源只能作辅助；`blocked` / `error` 不得作为核心数字来源。
- 缺少 A/B 级来源时，报告中必须标注“来源可靠性较低”，不得给高置信度。

### Step 7：撰写顺序与 Review（强制）

1. 读取 `_search-cache/stocks/{code}.json`、`fetched/*.md` 与同目录 `facts.md`（**跳过 `discarded`**），**先**完成各股 `report.md`。
2. **个股 Review**（每只完成后立即）：
   - 运行 `verify-report.py <该股 report.md> <_search-cache/>`
   - 按 [guides/review-guide.md](guides/review-guide.md) 人工核对引用与数据
   - 未通过 → 修正报告或补检索后重写，直至通过
3. 全部个股 Review 通过后，**最后**撰写 `daily-research-report.md`（从个股报告汇总估值表与链接）。
4. **整体 Review**：
   - `verify-report.py daily-research-report.md _search-cache/ --strict`
   - 重点核对：宏观现价 vs 预测分写、关键变量表数字与 `fetched` 一致
   - 未通过 → 修正后重跑
5. 整体报告中的宏观部分仅读取 `_search-cache/macro/` 中**未丢弃**来源。

### Step 8：历史分析复盘（整体报告第五节，必填）

在撰写当日判断**之前**，用 Step 5–6 检索到的最新资讯验证历史报告：

1. 从往期报告 + `lessons-learned.md` 待验证清单提取可验证判断。
2. 逐条标注：✅ 正确 / ⚠️ 部分正确 / ❌ 错误 / ⏳ 待验证。
3. 分析偏差根因（宏观突变、数据滞后、情绪误判等，见 retrospective-guide）。
4. 提炼 1–5 条**可执行**经验，写入报告并更新 `lessons-learned.md`。
5. 将今日核心判断追加到待验证清单（宏观 +7 日、个股/板块 +30 日验证截止）。

完整规则：[guides/retrospective-guide.md](guides/retrospective-guide.md)

### Step 9：分析维度（双层）

**整体报告** `daily-research-report.md`：

| 章节 | 内容 |
|------|------|
| 全局宏观 | 市场环境、关键变量、**整体投资结论（一段话）** |
| 个股估值总览 | **每只个股一行**：高低估结论 + 关键指标（**必须标注口径**）+ **来源** + 详情链接 |
| 分行业宏观 | 板块景气/政策/资讯；**禁止在此写板块级合并高低估** |
| 跨板块配置 | 板块权重倾向 + 首选个股链接 |
| 历史复盘 | 见 Step 8 |

**个股报告** `report.md`（模板见 [templates/stock-report-template.md](templates/stock-report-template.md)）：

| 维度 | 内容 |
|------|------|
| 最新资讯 | 近一周公告、新闻、分析师动作 |
| 基本面与财务 | 营收/利润/毛利率/ROE/现金流；**每项标明 Q1 YoY、FY YoY、TTM 等** |
| 公司分类（彼得林奇） | 估值前先判定：缓慢增长型 / 稳定增长型 / 快速增长型 / 周期型 / 隐蔽资产型 / 困境反转型；写明证据与估值锚；三类增长型写当前增长率，周期型写当前位置（衰退/复苏/过热/滞胀），隐蔽资产型写资产类型和价值，困境反转型写措施和预期收益 |
| 估值指标 | PE/PB/股息率/历史分位；**标明 TTM/静态/前瞻及数据日期**；估值方法须匹配公司分类 |
| 高估原因 | **个股**估值溢价、情绪、预期过高等（绑定指标）；引用地缘/政策/危机等状态性事件，须加注 `【事件当前状态：{仍持续|已解除|谈判中|已变化} · YYYY-MM-DD，来源：[标题](url)】` |
| 低估原因 | **个股**估值分位、拐点、分红、错杀等（绑定指标）；同高估原因，状态性事件须标注当前状态 |
| 综合判断 | 高估/合理/低估 + 偏多/中性/偏空 + 置信度 |

**口径强制规则**（违反则视为不合格报告）：

- 利润增速、营收增速必须写清：**哪个报告期、同比还是环比**（例：`2026 Q1 归母净利 +7.2% YoY`）。
- PE 必须写清：**TTM / 静态 / FY2026E**，并附数据日期。
- 估值前必须写出**彼得林奇公司分类**，并说明为什么该分类适用；估值锚必须随分类调整，禁止所有公司都机械套用 PE/PB 分位。
- 分类专属字段必须完整：缓慢增长型/稳定增长型/快速增长型公司写当前增长率（收入、利润或关键经营指标，注明口径与日期）；周期型公司写当前位置（衰退/复苏/过热/滞胀）及判断依据；隐蔽资产型公司写资产类型和价值（账面值/估值/重估空间，注明口径）；困境反转型公司写已采取/待兑现的反转措施和预期收益（成本节约、盈利改善、现金流改善或估值修复等）。
- 不得用板块平均或「三桶油」混写替代个股高低估。
- 估值结论必须写为“结论 + 区间/条件 + 置信度”，并列出 1–2 个可证伪条件（如油价、订单、净息差、销量、利润率阈值）。
- 宏观变量必须区分：当前现值、最新官方滞后数据、机构预测，不得互相替代。
- 报告中所有核心数字必须能追溯到同目录 `facts.md`，且 `facts.md` 已写明来源等级和原文摘录。

**引用来源强制规则**（违反则视为不合格报告）：

- **每一条**财务数字、估值、资讯、宏观变量、高低估理由均须附来源，格式：**`[来源标题](url) · YYYY-MM-DD`**（引用位置必须是可点击超链接，url 来自当日检索缓存 **`results` 或 `fetched`，禁止 `discarded`**）。
- **引用三一致**：链接 URL、标题、发布日期均须与缓存记录一致；数字须能在对应 `fetched/*.md` 正文中找到或交叉验证。
- **现价与预测分写**：如 Brent 现货、社零当月同比等「水平」写现货/官方值；EIA/投行均价预测须标明「预测」且不得填入「今日关键变量」现价栏。
- 整体报告：宏观 bullet、关键变量表、板块景气、个股总览表均须带链接化来源；文末 **引用来源索引**（含 URL）。
- 个股报告：财务表「来源」列、资讯表「引用」列必须为超链接；高低估理由写为 `… 〔来源：[标题](url) · 日期〕`。
- 估值结论若为综合判断：`〔综合判断，依据：[来源1](url1)；[来源2](url2)〕`。
- A/B/C 来源等级需体现在 `facts.md`；核心财务与估值结论不得只依赖 C 级来源。

### Step 10：报告模板

- 整体报告：[templates/report-template.md](templates/report-template.md)
- 个股报告：[templates/stock-report-template.md](templates/stock-report-template.md)
- 个股事实表：[templates/facts-template.md](templates/facts-template.md)
- 第五节「历史分析复盘」在跨板块配置之后、风险清单之前。

## 检索技巧

### 并行提速（推荐）

| 阶段 | 并行方式 | 环境变量 |
|------|----------|----------|
| **全池检索** | `batch-search-fetch.sh YYYY-MM-DD` | `PARALLEL_JOBS=8`（默认 8） |
| **单条 query 内 fetch** | `search-fetch.sh` 自动并行 URL | `FETCH_PARALLEL=5`（默认 5） |
| **JSON 写入** | `json-flock.py`（fcntl，macOS/Linux） | 同 KEY 多 query 可安全并行 |
| **个股报告** | 7 个 Task subagent 各写 1 份 `report.md` | 缓存完成后启动 |
| **流水线** | 某股缓存就绪 → 立即写该股报告 | 不必等全池抓完 |

```bash
# 一键全池
export PARALLEL_JOBS=8 MAX_CHARS=500000 MAX_FETCH=5 FETCH_PARALLEL=5
scripts/batch-search-fetch.sh 2026-06-24

# 只补某只股票
scripts/batch-search-fetch.sh 2026-06-24 --code 600938

# 只跑宏观
scripts/batch-search-fetch.sh 2026-06-24 --macro-only

# 只跑某板块
scripts/batch-search-fetch.sh 2026-06-24 --sector 石油
```

**不可并行**：`daily-research-report.md`（依赖全部个股报告）；用脚本批量生成报告正文。

### 其他技巧

- **交叉验证**：油价、利率、社零等关键数字至少 2 个**未丢弃**来源；分歧时写明区间与口径。
- **中英文**：`expand-queries.py` 会为 yaml `aliases` 追加别名 query；重要标的仍可手动补更精确的英文 query。
- **避免幻觉**：无法检索到的财务数字标注「未检索到」，不编造。
- **引用格式**：`[标题](url) · YYYY-MM-DD`；日期取自 `parsed_date` 或正文，禁止臆造。
- **抓取正文**：财报/公告页信息密度远高于 snippet；财务数字必须尽量来自 `fetched`。
- **缓存优先**：改报告只读 `_search-cache`；补数据用 `search-fetch.sh` 追加 query/fetch。
- **Query 时效**：Agent 每次运行检查 queries 是否含当前季/年（如 2026 Q1、FY2025）。
- **过期丢弃**：`search-fetch.sh` 日志出现 `discard:` 的链接不得写入报告；有效来源不足时追加含当月的 query 重搜。

## 附加资源

- 检索+抓取脚本：[batch-search-fetch.sh](scripts/batch-search-fetch.sh)（**推荐**，全池并行）、[search-fetch.sh](scripts/search-fetch.sh)（单条 query）、[expand-queries.py](scripts/expand-queries.py)（展开 yaml 任务）、[json-flock.py](scripts/json-flock.py)（JSON 锁）
- **时效过滤**：[date-filter.py](scripts/date-filter.py)（`search-fetch.sh` 内建调用）
- **报告 Review**：[guides/review-guide.md](guides/review-guide.md)、[verify-report.py](scripts/verify-report.py)
- 检索缓存规范：[guides/search-cache-guide.md](guides/search-cache-guide.md)
- 整体报告模板：[templates/report-template.md](templates/report-template.md)
- 个股报告模板：[templates/stock-report-template.md](templates/stock-report-template.md)
- 个股事实表模板：[templates/facts-template.md](templates/facts-template.md)
- 第五节「历史分析复盘」在跨板块配置之后、风险清单之前。
- 复盘与经验沉淀：[guides/retrospective-guide.md](guides/retrospective-guide.md)
- 累积经验库：`reports/_lessons/lessons-learned.md`
- SerpApi 调用：环境变量 `SERPAPI_KEY`（见仓库 [README.md](README.md)）；可选安装 [serpapi-web-search](https://github.com/serpapi/serpapi-mcp) skill 作补充检索
- 股票池配置：`config/industries.yaml`（从 `config/industries.example.yaml` 复制）

## 行业传导速查

| Sector | 宏观锚 | 个股弹性 |
|--------|--------|----------|
| 石油 | 布伦特油价 | 海油>中石油>中石化；油服滞后 |
| 新能源 | 锂价、装机量、产能过剩 | 电池龙头>锂矿；光伏承压 |
| AI | 算力 Capex、出口管制 | 光模块>芯片>应用 |
| 银行 | 净息差、LPR、资产质量 | 招行>股份行>国有大行 |
| 公用事业 | 电价、来水、核电核准 | 长江电力高分红>火电 |
| 基建 | 专项债、新签订单 | 出海/城更>传统房建 |
| 消费 | 社零、批价、原奶/猪价 | 茅台>区域酒；美的>格力 |
