#!/usr/bin/env bash
# agent-watch — 通用 Herdr agent 守望器
#
#   agent-watch heartbeat   睡一个周期，采集产出指纹，比对上轮，退出（唤醒监督者）
#   agent-watch guard       阻塞等落定状态（idle/done/blocked），异常即退出
#   agent-watch status      一次性快照，不睡不循环
#   agent-watch selftest    只验数据源是否可用
#
# 配置全部走环境变量或 flag，没有硬编码的 session / 仓库 / agent 名。
#   AW_SESSION   herdr session 名        (--session)   默认取唯一的活跃 session
#   AW_REPO      要盯产出的 git 仓库     (--repo)      默认取 pane 的 cwd
#   AW_SESSDIR   agent session jsonl 目录 (--sessdir)  默认从 pane cwd + profile 推断
#   AW_OUT       证据落盘目录            (--out)       默认 ~/.cache/agent-watch/<session>
#   AW_MINUTES   heartbeat 周期(分钟)    (--minutes)   默认 10
#   AW_BASE      产出计数的 git 基线     (--base)      默认 HEAD 所在分支的上游/初始
#
# 血泪教训，改之前先读：
#   1. agent 名不可信。root 会在重连后丢失变匿名；agent list 里的 "omp" 是类型不是
#      目标名。一律从 pane list 找挂着 agent 的 pane，用 pane id 当 target。
#   2. agent_status 会撒谎。OMP 干活时长期显示 idle；herdr 的 agent_session 若被
#      一次性子进程污染成 kind:id，状态会永久钉死。idle/done ≠ 完成。
#   3. pane 读空是「观测不可用」，不是「没有活动」。绝不能当否定证据。
#   4. pane read 是纯文本不是 JSON，别 json.load。
#   5. 判活看单调增长的量：session jsonl 字节数、context%、pane revision。

set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

MODE="${1:-status}"; shift 2>/dev/null || true

while [ $# -gt 0 ]; do
  case "$1" in
    --session) AW_SESSION="$2"; shift 2 ;;
    --repo)    AW_REPO="$2";    shift 2 ;;
    --sessdir) AW_SESSDIR="$2"; shift 2 ;;
    --out)     AW_OUT="$2";     shift 2 ;;
    --minutes) AW_MINUTES="$2"; shift 2 ;;
    --base)    AW_BASE="$2";    shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

hd(){ herdr ${AW_SESSION:+--session "$AW_SESSION"} "$@" 2>/dev/null; }

# ── session：没给就遍历 running session，挑挂着 agent 且最活跃的那个 ────
#    注意 session list 输出的是表格不是 JSON（pane list 才是 JSON）。
#    多个 session 可能都挂着 agent（default 里常有闲置的），按 pane revision
#    取最高的——干活的那个 pane 刷新最频繁。
if [ -z "${AW_SESSION:-}" ]; then
  best=""; bestrev=-1
  for s in $(herdr session list 2>/dev/null | awk 'NR>1 && $2=="running" {print $1}'); do
    rev=$(herdr --session "$s" pane list 2>/dev/null | python3 -c "
import json,sys
try:
    ps=[p for p in json.load(sys.stdin)['result']['panes'] if p.get('agent')]
    print(max((int(p.get('revision') or 0) for p in ps), default=-1))
except Exception: print(-1)" 2>/dev/null)
    [ -z "$rev" ] && rev=-1
    if [ "$rev" -gt "$bestrev" ]; then bestrev="$rev"; best="$s"; fi
  done
  [ "$bestrev" -lt 0 ] && { echo "找不到挂着 agent 的 session，用 --session 指定" >&2; exit 2; }
  AW_SESSION="$best"
fi

# ── pane：找挂着 agent 的那个，整个脚本唯一的 target 来源 ───────────────
panes_json(){ hd pane list; }

pane_field(){  # $1 = 字段名
  panes_json | python3 -c "
import json,sys
try:
    ps=json.load(sys.stdin)['result']['panes']
    p=next(x for x in ps if x.get('agent'))
    print(p.get('$1','') or '')
except Exception: print('')" 2>/dev/null
}

PANE=$(pane_field pane_id)
[ -z "$PANE" ] && PANE="w1:p1"   # 兜底，但下面自检会抓到真实不可用

pane_read(){ hd pane read "$PANE" --source visible --lines "${1:-60}"; }
status_of(){ s=$(pane_field agent_status); echo "${s:-unreachable}"; }

# ── 仓库：没给就用 pane 的 cwd ─────────────────────────────────────────
if [ -z "${AW_REPO:-}" ]; then
  AW_REPO=$(pane_field cwd)
  [ -z "$AW_REPO" ] && AW_REPO="$PWD"
fi
AW_REPO=$(git -C "$AW_REPO" rev-parse --show-toplevel 2>/dev/null || echo "$AW_REPO")

# ── session jsonl 目录：没给就按 pane cwd 反查 OMP session 目录 ────────
if [ -z "${AW_SESSDIR:-}" ]; then
  slug=$(printf '%s' "$AW_REPO" | sed "s|^$HOME||; s|/|-|g")
  for prof in "$HOME"/.omp/profiles/*/agent/sessions "$HOME"/.omp/agent/sessions; do
    [ -d "$prof$slug" ] && { AW_SESSDIR="$prof$slug"; break; }
    [ -d "$prof" ] && { AW_SESSDIR="$prof"; break; }
  done
fi

. "$(dirname "${BASH_SOURCE[0]}")/config.sh"
AW_OUT="${AW_OUT:-$(eval echo "$(ap_cfg observation.watch_output_dir "$HOME/.cache/agent-watch")")/$AW_SESSION}"
AW_MINUTES="${AW_MINUTES:-$(ap_cfg observation.interval_minutes 10)}"
mkdir -p "$AW_OUT"
STATE="$AW_OUT/.fingerprint"
LOG="$AW_OUT/watch.log"
note(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# ── 指纹：只取会单调变化的真实产出信号 ─────────────────────────────────
fingerprint(){
  local head dirty sess ctx rev
  head=$(git -C "$AW_REPO" rev-parse --short HEAD 2>/dev/null || echo '?')
  dirty=$(git -C "$AW_REPO" status --porcelain 2>/dev/null | wc -l)
  sess=$(cat "${AW_SESSDIR:-/nonexistent}"/*.jsonl "${AW_SESSDIR:-/nonexistent}"/*/*.jsonl 2>/dev/null | wc -c)
  rev=$(pane_field revision); rev="${rev:-?}"
  # context%：OMP 每消耗一次就涨，最灵敏。footer 会随 TODO 面板高度浮动，多抓几行。
  ctx=$(pane_read 40 | grep -oE '[0-9]+\.[0-9]+%/' | tail -1 | tr -d '%/')
  [ -z "$ctx" ] && ctx="unread"   # 抓不到就明说，不伪装成新值
  echo "${head}|${dirty}|${sess:-0}|${ctx}|${rev}"
}

report(){  # $1=判定 $2=证据文件 $3=上轮指纹 $4=本轮指纹
  IFS='|' read -r H D SZ C R  <<< "$4"
  IFS='|' read -r PH PD PSZ PC PR <<< "${3:-?|?|?|?|?}"
  cat <<EOF

=== $(date '+%F %T')  [$AW_SESSION $PANE] ===
状态     : $(status_of)   （idle 不代表停工，仅供参考）
HEAD     : $H   $( [ "$H"  != "$PH"  ] && echo "← 变了（上轮 $PH）" )
未提交   : $D   $( [ "$D"  != "$PD"  ] && echo "← 变了（上轮 $PD）" )
session  : ${SZ}B $( [ "$SZ" != "$PSZ" ] && echo "← 增长（上轮 ${PSZ}B）" )
context  : ${C}%  $( [ "$C"  != "$PC"  ] && echo "← 变了（上轮 ${PC}%）" )
revision : $R   $( [ "$R"  != "$PR"  ] && echo "← 变了（上轮 $PR）" )
判定     : $1
仓库     : $AW_REPO
证据     : $2

--- pane 尾部 ---
$(grep -v '^[[:space:]]*$' "$2" 2>/dev/null | tail -8 | cut -c1-150)
EOF
}

selftest(){
  local st p f bad=0
  st=$(status_of); p=$(pane_read 20); f=$(fingerprint)
  echo "session  = $AW_SESSION"
  echo "pane     = $PANE"
  echo "status   = $st"
  echo "pane_len = $(printf '%s' "$p" | wc -c)B"
  echo "repo     = $AW_REPO"
  echo "sessdir  = ${AW_SESSDIR:-<未找到>}"
  echo "fp       = $f"
  [ "$st" = "unreachable" ] && { echo "✗ herdr 不可达"; bad=1; }
  [ -z "$(printf '%s' "$p" | tr -d '[:space:]')" ] && { echo "✗ pane 读空 —— 观测不可用"; bad=1; }
  [ "${f%%|*}" = "?" ] && { echo "✗ 仓库读不到 HEAD"; bad=1; }
  [ "$bad" = 0 ] && echo "✓ 数据源全部可用"
  return "$bad"
}

snapshot(){
  local ev; ev="$AW_OUT/snap-$(date +%H%M%S).txt"
  pane_read 60 > "$ev" 2>&1
  local now prev; now=$(fingerprint); prev=$(cat "$STATE" 2>/dev/null || echo "")
  local v="有进展"
  [ "$now" = "$prev" ] && v="⚠ 指纹与上轮完全相同 —— 可能真的停了"
  [ "$(wc -c < "$ev")" -lt 50 ] && v="⚠ pane 读取异常 —— 无法观测，不代表停工"
  case "$(status_of)" in
    unreachable) v="⚠ herdr 不可达" ;;
    blocked)     v="⚠ BLOCKED —— 需要人介入" ;;
  esac
  echo "$now" > "$STATE"
  report "$v" "$ev" "$prev" "$now"
}

case "$MODE" in
  selftest) selftest ;;

  status) snapshot ;;

  heartbeat)
    sleep "$(python3 -c "print(int(float('$AW_MINUTES')*60))")"
    snapshot
    echo
    echo ">>> 看完请重新起一个心跳续上。"
    ;;

  guard)
    selftest >/dev/null || { echo "自检失败，拒绝无声守望："; selftest; exit 1; }
    note "guard started fp=$(fingerprint)"
    PREV=$(fingerprint); STALL=0
    wake(){
      local ev="$AW_OUT/wake-$(date +%H%M%S).txt"
      pane_read 60 > "$ev" 2>&1
      note "WAKE: $1"
      echo "=== WAKE ==="
      report "$1 — $2" "$ev" "$PREV" "$(fingerprint)"
      exit 0
    }
    while :; do
      hd agent wait "$PANE" --until idle --until done --until blocked --timeout 900000 >/dev/null 2>&1
      st=$(status_of)
      [ "$st" = "unreachable" ] && wake "agent 不可达" "run 可能已结束或崩溃"

      p=$(pane_read 60)
      [ -z "$(printf '%s' "$p" | tr -d '[:space:]')" ] \
        && wake "pane 读取返回空" "读空是缺陷不是否定结果，已失去判断依据"

      cur=$(fingerprint)
      [ "$st" = "blocked" ] && wake "BLOCKED — 有对话框等人应答" "status=blocked"

      # 完成标记优先于 idle 判断
      printf '%s' "$p" | grep -qE "Commit boundary|run complete|RUN_COMPLETE" \
        && wake "疑似全部完成" "pane 出现完成标记"

      if [ "$st" = "idle" ] || [ "$st" = "done" ]; then
        if printf '%s' "$p" | grep -qE "waiting on [0-9]+ job|⟨task⟩|Subagents|Waiting for"; then
          note "idle 但仍在等 child/外部 — 继续守望 (fp=$cur)"
        else
          wake "agent 停下且没在等 child" "status=$st"
        fi
      fi

      if [ "$cur" = "$PREV" ]; then
        STALL=$((STALL+1))
        [ "$STALL" -ge 4 ] && wake "长时间零产出" "连续 $STALL 轮指纹未变 fp=$cur"
      else
        STALL=0; PREV="$cur"; note "进展 fp=$cur st=$st"
      fi
      sleep 20
    done
    ;;

  *) echo "用法: agent-watch {heartbeat|guard|status|selftest} [--session S] [--repo R] [--minutes N]" >&2; exit 2 ;;
esac
