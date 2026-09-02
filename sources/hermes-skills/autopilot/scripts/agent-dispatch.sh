#!/usr/bin/env bash
# agent-dispatch.sh — 带送达证明的 agent prompt 派发
#
# 问题：herdr agent prompt 的失败输出不能证明未送达。agent_prompt_stalled 和
# timeout 都可能发生在 prompt 已写入 session 之后，此时重发会造成双写。
# 唯一可靠的判据是 runner session 里那个 prompt 是否真的出现了。
#
# 做法：每次派发生成唯一 marker 随 packet 送出，然后在 runner session
# transcript 里数它。0 次 = 确未送达，可安全重发；1 次 = 已送达，不管 CLI
# 报什么错都不得重发；2 次以上 = 已双写，告知 Root 按一次处理，不停 run。
#
# 用法：
#   agent-dispatch.sh send   --file PACKET.md [--session S] [--pane P]
#   agent-dispatch.sh verify --marker MARKER  [--session S] [--pane P]
#   agent-dispatch.sh list
#
# send 退出码：0 已送达 / 3 未证明送达（packet 保留可重发）/ 4 双写（告知 Root，不重发）/ 2 用法或环境错
#
# 环境变量（均可用同名 --flag 覆盖，优先级高于 autopilot-config.yaml）：
#   AD_SESSION   Herdr session 名     默认自动发现最活跃的 agent-bearing pane
#   AD_PANE      pane id (如 w1:p1)   默认同上
#   AD_SESSFILE  runner session jsonl 默认取 pane 自报的 agent_session.value
#   AD_STORE     派发记录目录         默认取配置 observation.dispatch_store_dir
#
# 送达等待时长取配置 observation.dispatch_verify_timeout_seconds（默认 30 秒）。
#
# 记录：每次 send 在 $AD_STORE/<marker>/ 留 packet.md、meta.json、verify.log。
# 这些是证据，脚本从不改写已有记录的 packet。

set -uo pipefail

AD_STORE="${AD_STORE:-}"
AD_SESSION="${AD_SESSION:-}"
AD_PANE="${AD_PANE:-}"
AD_SESSFILE="${AD_SESSFILE:-}"
PACKET=""
MARKER=""
MODE="${1:-}"
[ $# -gt 0 ] && shift

while [ $# -gt 0 ]; do
  case "$1" in
    --file)     PACKET="$2"; shift 2 ;;
    --marker)   MARKER="$2"; shift 2 ;;
    --session)  AD_SESSION="$2"; shift 2 ;;
    --pane)     AD_PANE="$2"; shift 2 ;;
    --sessfile) AD_SESSFILE="$2"; shift 2 ;;
    --store)    AD_STORE="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

die(){ echo "✗ $*" >&2; exit 2; }
command -v herdr >/dev/null 2>&1 || die "缺少命令: herdr"
command -v python3 >/dev/null 2>&1 || die "缺少命令: python3"

# 配置兜底放在参数解析之后：--store 优先于配置，配置优先于内置默认
. "$(dirname "${BASH_SOURCE[0]}")/config.sh"
AD_STORE="${AD_STORE:-$(eval echo "$(ap_cfg observation.dispatch_store_dir "$HOME/.cache/agent-dispatch")")}"
AD_TIMEOUT="$(ap_cfg observation.dispatch_verify_timeout_seconds 30)"

# ── pane 发现 ─────────────────────────────────────────────────────────
# agent 名不是稳定目标（重连后变匿名，agent list 里的 omp 是类型不是名字），
# 一律解析 pane id。pane list 是 JSON，用 python 解析而不是 awk 切列。
# 多个 session 都有 agent 时按 revision 选最活跃的，避免误选 default 里的闲置 pane。
discover_pane(){
  [ -n "$AD_PANE" ] && [ -n "$AD_SESSION" ] && [ -n "$AD_SESSFILE" ] && return 0

  local sessions
  if [ -n "$AD_SESSION" ]; then
    sessions="$AD_SESSION"
  else
    sessions=$(herdr session list 2>/dev/null | awk 'NR>1 && $2=="running"{print $1}')
  fi
  [ -z "$sessions" ] && die "没有 running 的 Herdr session"

  local best="" s out
  for s in $sessions; do
    out=$(herdr pane list --session "$s" 2>/dev/null) || continue
    best=$(printf '%s\n%s' "$best" "$(printf '%s' "$out" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit()
for p in d.get("result",{}).get("panes",[]):
    if not p.get("agent"): continue
    sess=(p.get("agent_session") or {})
    # kind 必须是 path：--no-session 的探针会落 kind:id 且钉死 idle，不可作为目标
    if sess.get("kind")!="path": continue
    print(p.get("revision",0), "'"$s"'", p.get("pane_id",""), sess.get("value",""))
')")
  done

  local pick
  pick=$(printf '%s' "$best" | grep -v '^$' | sort -rn | head -1)
  [ -z "$pick" ] && die "找不到承载 agent 且 session kind=path 的 pane"

  AD_SESSION=$(echo "$pick" | awk '{print $2}')
  AD_PANE=$(echo "$pick" | awk '{print $3}')
  AD_SESSFILE=$(echo "$pick" | awk '{print $4}')
  [ -f "$AD_SESSFILE" ] || die "pane 自报的 session 文件不存在: $AD_SESSFILE"
}

# ── 在 session transcript 里数 marker 字面量 ──────────────────────────
# packet 正文不得含 marker，否则回显污染计数（send 前会检查）。
count_marker(){
  local n
  n=$(grep -c -- "$1" "$AD_SESSFILE" 2>/dev/null)
  echo "${n:-0}"
}

case "$MODE" in
  list)
    [ -d "$AD_STORE" ] || { echo "(无派发记录)"; exit 0; }
    shopt -s nullglob
    for d in "$AD_STORE"/*/; do
      printf '%-40s %s\n' "$(basename "$d")" \
        "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("status","?"))' \
           "$d/meta.json" 2>/dev/null || echo '?')"
    done
    ;;

  verify)
    [ -n "$MARKER" ] || die "verify 需要 --marker"
    discover_pane
    n=$(count_marker "$MARKER")
    echo "marker   = $MARKER"
    echo "sessfile = $AD_SESSFILE"
    echo "出现次数 = $n"
    case "$n" in
      0) echo "→ 未送达，可安全重发"; exit 3 ;;
      1) echo "→ 已送达一次，不得重发"; exit 0 ;;
      *) echo "→ ⚠ 出现 $n 次，已双写。告知 Root 按一次处理，不要重发"; exit 4 ;;
    esac
    ;;

  send)
    [ -n "$PACKET" ] || die "send 需要 --file"
    [ -f "$PACKET" ] || die "packet 不存在: $PACKET"
    discover_pane

    digest=$(sha256sum "$PACKET" | cut -d' ' -f1)
    marker="AD-$(date +%Y%m%d-%H%M%S)-${digest:0:16}"

    grep -q -- "$marker" "$PACKET" && die "packet 正文已含 marker，会污染计数"
    pre=$(count_marker "$marker")
    [ "$pre" != "0" ] && die "marker 在派发前已出现 $pre 次，中止"

    rec="$AD_STORE/$marker"; mkdir -p "$rec"
    cp "$PACKET" "$rec/packet.md"
    body="$(cat "$PACKET")

<!-- dispatch marker: $marker -->"

    python3 -c '
import json,sys
json.dump({"marker":sys.argv[1],"status":"prepared","packet":sys.argv[2],
"digest":"sha256:"+sys.argv[3],"session":sys.argv[4],"pane":sys.argv[5],
"sessfile":sys.argv[6],"sent_at":sys.argv[7]}, open(sys.argv[8],"w"),
ensure_ascii=False, indent=1)
' "$marker" "$(realpath "$PACKET")" "$digest" "$AD_SESSION" "$AD_PANE" \
  "$AD_SESSFILE" "$(date -Is)" "$rec/meta.json"

    set_status(){ python3 -c '
import json,sys
p=sys.argv[1]; d=json.load(open(p)); d["status"]=sys.argv[2]
json.dump(d, open(p,"w"), ensure_ascii=False, indent=1)
' "$rec/meta.json" "$1"; }

    echo "marker   = $marker"
    echo "target   = $AD_SESSION / $AD_PANE"
    echo "sessfile = $AD_SESSFILE"
    echo "记录     = $rec"
    echo "--- 派发中 ---"

    # TEXT 是位置参数，不是 stdin
    # AD_PROMPT_ARGS 仅供自测注入 --wait/--timeout 以复现 CLI 报错场景
    # shellcheck disable=SC2086
    herdr agent prompt "$AD_PANE" "$body" --session "$AD_SESSION" ${AD_PROMPT_ARGS:-} \
      > "$rec/send.log" 2>&1
    cli=$?
    echo "herdr exit = $cli"

    # 关键：CLI 退出码不作为送达判据，一律回 session 里数 marker。
    # agent_prompt_stalled / timeout 都可能发生在写入之后。
    n=0
    for _ in $(seq $(( AD_TIMEOUT / 2 ))); do
      sleep 2
      n=$(count_marker "$marker")
      [ "$n" != "0" ] && break
    done

    { echo "herdr_exit=$cli"; echo "marker_count=$n"; echo "checked_at=$(date -Is)"; } \
      > "$rec/verify.log"

    case "$n" in
      0)
        set_status undelivered
        echo "✗ ${AD_TIMEOUT} 秒内未在 session 中观察到 marker"
        echo "  → 未证明送达。可用同一 packet 重发，或手动复核："
        echo "     grep -c '$marker' $AD_SESSFILE"
        exit 3 ;;
      1)
        set_status delivered
        echo "✓ 已送达（marker 出现 1 次）"
        [ "$cli" != "0" ] && \
          echo "  注意：herdr 报错 exit=$cli，但 prompt 确已送达，不得重发"
        exit 0 ;;
      *)
        set_status duplicated
        echo "⚠ marker 出现 $n 次，已双写。告知 Root 该指令到达两次、按一次处理；不要重发"
        exit 4 ;;
    esac
    ;;

  *)
    sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
    exit 2 ;;
esac
