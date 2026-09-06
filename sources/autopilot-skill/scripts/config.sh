#!/usr/bin/env bash
# config.sh — 读取 autopilot-config.yaml 的单个标量值
#
# 被 agent-watch.sh source。让脚本默认值来自同一份配置，
# 而不是各写各的字面量。
#
#   ap_cfg <点路径> <兜底值>
#
# 例：ap_cfg observation.interval_minutes 10
#
# 找不到配置文件、缺少 key、或没有 YAML 解析器时一律返回兜底值——
# 配置缺失不该让监督脚本罢工。
# 环境变量优先级仍高于本文件：调用方写 "${AW_MINUTES:-$(ap_cfg ...)}"。

AP_CONFIG="${AP_CONFIG:-$(dirname "${BASH_SOURCE[0]}")/../autopilot-config.yaml}"

ap_cfg(){
  local key="$1" fallback="${2:-}"
  [ -f "$AP_CONFIG" ] || { printf '%s' "$fallback"; return; }
  command -v python3 >/dev/null 2>&1 || { printf '%s' "$fallback"; return; }
  python3 - "$AP_CONFIG" "$key" "$fallback" <<'PY' 2>/dev/null || printf '%s' "$fallback"
import sys
path, key, fallback = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    import yaml
    with open(path) as f:
        data = yaml.safe_load(f) or {}
except Exception:
    print(fallback); raise SystemExit
cur = data
for part in key.split("."):
    if not isinstance(cur, dict) or part not in cur:
        print(fallback); raise SystemExit
    cur = cur[part]
if isinstance(cur, bool):
    print("true" if cur else "false")
elif cur is None or isinstance(cur, (dict, list)):
    print(fallback)
else:
    print(cur)
PY
}
