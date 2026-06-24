#!/usr/bin/env bash
# 从 industries.yaml 展开全部检索任务，并行调用 search-fetch.sh
# 禁止：批量生成 report.md
# 检索缓存仅供研究参考，不构成投资建议。
set -euo pipefail

DATE="${1:?用法: batch-search-fetch.sh YYYY-MM-DD [expand-queries.py 额外参数]}"
shift || true

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SF="$SCRIPT_DIR/search-fetch.sh"
EXPAND="$SCRIPT_DIR/expand-queries.py"
PARALLEL_JOBS="${PARALLEL_JOBS:-8}"
export MAX_CHARS="${MAX_CHARS:-500000}"
export MAX_FETCH="${MAX_FETCH:-5}"
export FETCH_PARALLEL="${FETCH_PARALLEL:-5}"

chmod +x "$SF" "$EXPAND" "$SCRIPT_DIR/json-flock.py" "$SCRIPT_DIR/date-filter.py" "$SCRIPT_DIR/verify-report.py" 2>/dev/null || true

echo "=== batch-search-fetch $DATE (jobs=$PARALLEL_JOBS, fetch_parallel=$FETCH_PARALLEL) ==="

run_job() {
  local kind="$1" key="$2" query="$3"
  # 引号包裹 query，避免分词
  "$SF" "$DATE" "$kind" "$key" "$query"
}

export -f run_job
export SF DATE

# TSV: kind \t key \t query
python3 "$EXPAND" --date "$DATE" "$@" \
  | parallel --colsep '\t' -j "$PARALLEL_JOBS" --line-buffer \
      'run_job {1} {2} {3}'

echo "=== Summary ==="
CACHE="$ROOT/reports/$DATE/_search-cache"
for f in "$CACHE"/macro/*.json "$CACHE"/stocks/*.json; do
  [[ -f "$f" ]] || continue
  echo "$(basename "$f"): queries=$(jq '.queries|length' "$f") fetched=$(jq '.fetched|length' "$f")"
done
grep -r "truncated" "$CACHE" 2>/dev/null && echo "WARNING: truncated content found" || echo "No truncation markers"
