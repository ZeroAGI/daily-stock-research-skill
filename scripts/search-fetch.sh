#!/usr/bin/env bash
# SerpApi 检索 + 并行抓取链接正文并落盘（禁止写 report.md）
# 检索缓存仅供研究参考，不构成投资建议。
set -euo pipefail

DATE="${1:?用法: search-fetch.sh YYYY-MM-DD <stock|macro> <code|topic> [query...]}"
KIND="${2:?stock|macro}"
KEY="${3:?code or topic name}"
shift 3
QUERY="${*:-}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACT="$SCRIPT_DIR/fetch-extract.py"
DATE_FILTER="$SCRIPT_DIR/date-filter.py"
FLOCK="$SCRIPT_DIR/json-flock.py"
CACHE="$ROOT/reports/$DATE/_search-cache"
SETTINGS="$ROOT/config/settings.yaml"
if [[ -z "${SERPAPI_ENDPOINT:-}" && -f "$SETTINGS" ]]; then
  EP="$(python3 -c "
import yaml, sys
try:
    with open(sys.argv[1]) as f:
        s = yaml.safe_load(f) or {}
    base = (s.get('serpapi') or {}).get('base_url', '')
    st = (s.get('serpapi') or {}).get('search_type', 'search/advanced')
    print(f'{base.rstrip(\"/\")}/{st.lstrip(\"/\")}' if base else '')
except Exception:
    pass
" "$SETTINGS" 2>/dev/null || true)"
fi
EP="${EP:-${SERPAPI_ENDPOINT:-https://serpapi.com/search.json}}"
MAX_FETCH="${MAX_FETCH:-5}"
MAX_CHARS="${MAX_CHARS:-500000}"
FETCH_PARALLEL="${FETCH_PARALLEL:-5}"
export MAX_CHARS

mkdir -p "$CACHE"

if [[ "$KIND" == "stock" ]]; then
  JSON="$CACHE/stocks/${KEY}.json"
  FETCH_DIR="$CACHE/stocks/${KEY}/fetched"
elif [[ "$KIND" == "macro" ]]; then
  JSON="$CACHE/macro/${KEY}.json"
  FETCH_DIR="$CACHE/macro/fetched"
else
  echo "KIND 须为 stock 或 macro" >&2; exit 1
fi

mkdir -p "$FETCH_DIR"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
QUERY_ID="$(printf '%s\n%s\n%s\n%s\n%s' "$KIND" "$KEY" "$QUERY" "$NOW" "$RANDOM" | shasum -a 256 | cut -c1-16)"

if [[ -z "$QUERY" ]]; then
  echo "需要 query" >&2; exit 1
fi

hash_url() { printf '%s' "$1" | shasum -a 256 | cut -c1-12; }

# 单 URL 抓取，写入 out；结果行写入 result_file（供并行汇总）
fetch_one() {
  local title="$1" url="$2" snippet="$3" out="$4" result_file="$5"
  local status body h
  h="$(hash_url "$url")"

  if [[ -f "$out" && "${FORCE_REFETCH:-0}" != "1" ]]; then
    echo "Skip existing fetch: $url"
    status="$(grep -m1 '^\*\*Status\*\*:' "$out" 2>/dev/null | sed 's/.*: //' || echo "ok")"
  else
    echo "Fetch: $url"
    local result
    result="$(LC_ALL=en_US.UTF-8 python3 "$EXTRACT" "$url" 2>/dev/null || echo '{"status":"error","body":""}')"
    status="$(echo "$result" | jq -r '.status')"
    body="$(echo "$result" | jq -r '.body')"
    {
      echo "# ${title}"
      echo "- **URL**: ${url}"
      echo "- **Fetched**: ${NOW}"
      echo "- **Status**: ${status}"
      echo ""
      if [[ -n "$body" && "$body" != "null" ]]; then
        echo "$body"
      else
        echo "_（未能提取正文）_"
      fi
      if [[ "$status" != "ok" && -n "$snippet" && "$snippet" != "null" ]]; then
        echo ""
        echo "## SerpApi Snippet（检索摘要）"
        echo ""
        echo "$snippet"
      fi
    } > "$out"
  fi

  local excerpt rel_path
  excerpt="$(LC_ALL=C head -c 500 "$out" | LC_ALL=C tr '\n' ' ')"
  if [[ "$KIND" == "stock" ]]; then
    rel_path="stocks/${KEY}/fetched/$(basename "$out")"
  else
    rel_path="macro/fetched/$(basename "$out")"
  fi
  jq -n \
    --arg url "$url" --arg title "$title" --arg t "$NOW" \
    --arg path "$rel_path" --arg ex "$excerpt" --arg st "$status" \
    '{url:$url, title:$title, fetched_at:$t, content_path:$path, status:$st, excerpt:$ex}' \
    > "$result_file"
}

merge_fetched_entry() {
  local entry_json="$1"
  python3 "$FLOCK" "$JSON" bash -c '
    set -euo pipefail
    jq --slurpfile ent "$1" \
      ".fetched = ((.fetched // []) | map(select(.url != \$ent[0].url)) + \$ent)" \
      "$2" > "$2.tmp" && mv "$2.tmp" "$2"
  ' bash "$entry_json" "$JSON"
}

echo "Search: $QUERY"

# --- SerpApi + merge query（持锁）---
python3 "$FLOCK" "$JSON" bash -c '
  set -euo pipefail
  JSON="$1"; QUERY="$2"; NOW="$3"; EP="$4"; QUERY_ID="$5"
  : "${SERPAPI_KEY:?SERPAPI_KEY required}"
  if [[ "$EP" == *"serp.hk"* ]]; then
    PAYLOAD="$(jq -n --arg q "$QUERY" "{q:\$q,num:8}")"
    RESP="$(curl -sS \
      -H "Authorization: Bearer ${SERPAPI_KEY}" \
      -H "Content-Type: application/json" \
      "$EP" \
      -X POST -d "$PAYLOAD" \
      --compressed)"
  else
    RESP="$(curl -sS -G "$EP" \
      --data-urlencode "engine=google" \
      --data-urlencode "q=$QUERY" \
      --data-urlencode "num=8" \
      --data-urlencode "api_key=${SERPAPI_KEY}" \
      --compressed)"
  fi
  TMP="$(mktemp)"
  if [[ -f "$JSON" ]]; then
    if jq -e "type == \"array\"" "$JSON" >/dev/null 2>&1; then
      jq "{queries: [], fetched: .}" "$JSON" > "$TMP"
    else
      cp "$JSON" "$TMP"
    fi
  else
    echo "{\"queries\":[],\"fetched\":[]}" > "$TMP"
  fi
  echo "$RESP" | jq --arg id "$QUERY_ID" --arg q "$QUERY" --arg t "$NOW" \
    "if .result.organic then
       {id:\$id, q:\$q, searched_at:\$t, results: [.result.organic[]? | {title, link, snippet, date: (.date // null)}]}
     elif .organic_results then
       {id:\$id, q:\$q, searched_at:\$t, results: [.organic_results[]? | {title, link, snippet, date: .date}]}
     else empty end" \
    | jq -s --slurpfile base "$TMP" \
      "\$base[0] + {queries: (\$base[0].queries + [.[-1]]), fetched: (\$base[0].fetched // [])}" \
    > "${TMP}.new" 2>/dev/null || jq -n --slurpfile base "$TMP" --arg id "$QUERY_ID" --arg q "$QUERY" --arg t "$NOW" \
      "\$base[0] + {
        queries: (\$base[0].queries + [{
          id: \$id,
          q: \$q,
          searched_at: \$t,
          results: [],
          error: \"serpapi_parse_failed\"
        }]),
        fetched: (\$base[0].fetched // [])
      }" > "${TMP}.new"
  jq "if .queries then . else {queries:[.], fetched:(.fetched//[])} end |
      if (.fetched | type) != \"array\" then .fetched = [] else . end" "${TMP}.new" > "$JSON"
  rm -f "$TMP" "${TMP}.new"
' bash "$JSON" "$QUERY" "$NOW" "$EP" "$QUERY_ID"

# --- 按时效过滤：过期结果不 fetch、不入 results（写入 discarded）---
FILTERED="$(mktemp)"
jq -c --arg id "$QUERY_ID" '([.queries[]? | select(.id == $id)][0].results) // []' "$JSON" \
  | python3 "$DATE_FILTER" filter --report-date "$DATE" --kind "$KIND" --query "$QUERY" \
  > "$FILTERED"

KEPT_COUNT="$(jq '.kept | length' "$FILTERED")"
DISCARDED_COUNT="$(jq '.discarded | length' "$FILTERED")"
if [[ "$DISCARDED_COUNT" -gt 0 ]]; then
  echo "Date filter: kept=$KEPT_COUNT discarded=$DISCARDED_COUNT (class=$(jq -r '.query_class' "$FILTERED"), max_age=$(jq -r '.max_age_days' "$FILTERED")d)"
  jq -c '.discarded[]' "$FILTERED" | while read -r d; do
    echo "  discard: $(echo "$d" | jq -r '.discard_reason') — $(echo "$d" | jq -r '.link')"
  done
fi

python3 "$FLOCK" "$JSON" bash -c '
  set -euo pipefail
  FILTERED="$1"; JSON="$2"; QUERY_ID="$3"
  jq --slurpfile f "$FILTERED" --arg id "$QUERY_ID" \
    ".queries = ((.queries // []) | map(
      if .id == \$id then
        .results = \$f[0].kept |
        .discarded = \$f[0].discarded |
        .filter_meta = {
          query_class: \$f[0].query_class,
          max_age_days: \$f[0].max_age_days
        }
      else . end
    ))" "$JSON" > "$JSON.tmp" && mv "$JSON.tmp" "$JSON"
' bash "$FILTERED" "$JSON" "$QUERY_ID"

rm -f "$FILTERED"

# --- 并行 fetch Top N（仅 kept results）---
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FETCHED=0
PIDS=()
RESULT_FILES=()

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  title="$(echo "$line" | jq -r '.title')"
  url="$(echo "$line" | jq -r '.link')"
  snippet="$(echo "$line" | jq -r '.snippet // ""')"
  [[ "$url" == "null" || -z "$url" ]] && continue
  [[ "$url" =~ \.(pdf|PDF)(\?|$) ]] && { echo "Skip PDF: $url"; continue; }

  h="$(hash_url "$url")"
  out="$FETCH_DIR/${h}.md"
  rf="$WORK/${h}.json"

  # 限制并发
  while ((${#PIDS[@]} >= FETCH_PARALLEL)); do
    wait "${PIDS[0]}" 2>/dev/null || true
    PIDS=("${PIDS[@]:1}")
  done

  fetch_one "$title" "$url" "$snippet" "$out" "$rf" &
  PIDS+=($!)
  RESULT_FILES+=("$rf")
  FETCHED=$((FETCHED + 1))
  [[ "$FETCHED" -ge "$MAX_FETCH" ]] && break
done < <(jq -c --arg id "$QUERY_ID" '.queries[]? | select(.id == $id) | .results[]? | select(.link!=null and (.discard_reason==null or .discard_reason==""))' "$JSON")

if ((${#PIDS[@]} > 0)); then
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
fi

# 持锁批量写入 fetched 索引
for rf in "${RESULT_FILES[@]:-}"; do
  [[ -f "$rf" ]] || continue
  merge_fetched_entry "$rf"
done

echo "Done: $JSON (+$FETCHED fetched, parallel=$FETCH_PARALLEL)"
