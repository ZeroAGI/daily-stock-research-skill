# 报告撰写后 Review 规范

> **免责声明**：本规范及经其校验的报告产出仅供研究参考，**不构成投资建议**。

每份报告**写完即审**，通过后方可进入下一步。脚本辅助 + Agent 人工核对。

## 触发时机

| 步骤 | 产出 | Review |
|------|------|--------|
| Step 7a | 每只 `report.md` | **个股 Review**（该股写完立即执行） |
| Step 7b | `daily-research-report.md` | **整体 Review**（全部个股通过后执行） |

## 自动化检查

```bash
DATE=2026-06-24
CACHE="reports/$DATE/_search-cache"

# 个股
python3 scripts/verify-report.py \
  "reports/$DATE/石油/油气开采/中国海油/report.md" "$CACHE"

# 整体
python3 scripts/verify-report.py \
  "reports/$DATE/daily-research-report.md" "$CACHE" --strict
```

`verify-report.py` 检查项：
- 每个 `[标题](url)` 必须存在于当日 `_search-cache`（`results` 或 `fetched`）
- **禁止**引用 `discarded` 中的过期链接
- 引用标题与缓存 `title` 须语义一致（防链错文，如社零链到沃尔玛）
- 引用日期 `· YYYY-MM-DD` 须与缓存 `parsed_date` 一致（不一致则改或删）
- 缺少引用日期、没有 fetched 正文索引、抓取失败会输出 warning；整体报告 `--strict` 下 warning 也视为失败
- 个股报告要求同目录存在 `facts.md`，且报告中的核心数字可回溯到事实表
- 财务/估值表缺少口径、数据日期、来源等级，或综合判断缺少可证伪条件，会输出 warning
- `partial` 来源只能辅助；`blocked` / `error` 来源不得作为核心数字依据

退出码非 0 → **必须修正后重跑**，不得跳过。

## Agent 人工核对清单（强制）

### A. 引用准确性
1. 财务/宏观数字优先来自 `fetched/*.md` 正文，而非 snippet。
2. 引用 URL 与论述主题一致（打开 `fetched` 确认含该数字或表述）。
3. 引用日期 = 来源发布日（`parsed_date` 或正文/URL 日期），**禁止**臆造日期。

### B. 数据准确性
1. **现价类**（油价、汇率、指数）：须为 report 日前 **7 日内**来源；写清是现货还是预测（EIA/投行 forecast 不得当日价混用）。
2. **月度宏观**（社零、CPI、PMI）：须为最近一期官方发布；同比数字与绝对额、报告期一致。
3. **季报/年报**：标明 Q1/FY、YoY；PE 标明 TTM/静态/前瞻。
4. 关键宏观数字 **≥2 个独立来源**交叉验证；分歧写区间并说明口径。
5. 个股核心数字先进入 `facts.md`，事实表须包含来源等级（A/B/C）和原文摘录。
6. 同一指标多来源冲突时，必须写“冲突来源说明”，不得任选一个数字。

### C. 时效
1. 仅使用 `results`（`discard_reason` 为空）与 `fetched`；**不得**使用 `queries[].discarded`。
2. 若有效来源不足，**追加检索**（更新 query 含当月）并 fetch，不得沿用过期缓存写结论。

### D. 个股 Review 通过标准
- [ ] `verify-report.py` 退出码 0
- [ ] 文末含「不构成投资建议」免责声明
- [ ] 同目录 `facts.md` 已完成，核心数字、口径、数据日期、来源等级、原文摘录齐全
- [ ] 财务表每行有来源且口径标注
- [ ] 估值前已判断彼得林奇公司分类，且估值锚与分类一致
- [ ] 高低估理由绑定可量化指标
- [ ] 综合判断包含估值区间/适用条件、置信度、可证伪条件
- [ ] 状态性事件（地缘/政策）有 `【事件当前状态：…】` 标注

### E. 整体 Review 通过标准
- [ ] `verify-report.py --strict` 退出码 0
- [ ] 文末含「不构成投资建议」免责声明
- [ ] 「今日关键变量」现货与预测分栏或分句，不混写
- [ ] 个股总览表与各股 `report.md` 估值结论一致
- [ ] 引用来源索引表 URL 与正文一致

## 修正循环

```
撰写 → verify-report → 失败？→ 改报告或补检索+fetch → 再 verify → 通过
```
