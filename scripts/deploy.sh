#!/usr/bin/env bash
# Install Smart Cascade core with selected runners, the OMP profile, and optional Autopilot.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_SOURCE="$REPO_ROOT/sources/smart-cascade-skill"
OMP_PROFILE_SOURCE="$REPO_ROOT/sources/smart-cascade-omp/agent"
AUTOPILOT_SOURCE="$REPO_ROOT/sources/hermes-skills/autopilot"
OMP_RUNNER_SOURCE="$SKILL_SOURCE/runners/omp"
OMP_SKILLS_ROOT="${SMART_CASCADE_SKILLS_ROOT:-$HOME/.omp/skills}"
PROFILES_ROOT="${SMART_CASCADE_PROFILES_ROOT:-$HOME/.omp/profiles}"
HERMES_SKILLS_ROOT="${SMART_CASCADE_HERMES_SKILLS_ROOT:-$HOME/.hermes/skills}"
PROFILE_SELECTION="smart-cascade-omp"
PROFILE_NAME=""
AUTOPILOT_RELATIVE="autonomous-ai-agents/autopilot"
DRY_RUN=0
RUNNERS=()

fail() { printf 'error: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }
run() {
  if [[ $DRY_RUN == 1 ]]; then
    printf '  [dry-run]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

usage() {
  cat <<'USAGE'
usage: deploy.sh <command> [options]

commands:
  verify       check common dependencies and selected-runner installation drift
  skill        install/update the Skill core and selected runner directories
  profile      install/update the selected OMP profile's roles and config.yml
  autopilot    install/update the optional Hermes Autopilot supervision skill
  all          install skill, the selected OMP profile when omp is selected, then autopilot

options:
  --runner NAME          select a Skill runner; repeat to install several
                         default: omp (the only production runner, preserving existing installs)
  --profile NAME|PATH    OMP profile name or full profile directory
                         default: smart-cascade-omp; path overrides --profiles-root
  --dry-run              print planned writes without changing files
  --profiles-root DIR    profiles root for a profile name

environment:
  SMART_CASCADE_SKILLS_ROOT         OMP skills root (default ~/.omp/skills)
  SMART_CASCADE_PROFILES_ROOT       OMP profiles root (default ~/.omp/profiles)
  SMART_CASCADE_HERMES_SKILLS_ROOT  Hermes skills root (default ~/.hermes/skills)
  SMART_CASCADE_OMP_BIN             explicit OMP executable for verify
USAGE
}

runner_selected() {
  local expected=$1 runner
  for runner in "${RUNNERS[@]}"; do
    [[ $runner == "$expected" ]] && return 0
  done
  return 1
}

validate_runners() {
  ((${#RUNNERS[@]})) || RUNNERS=(omp)
  local runner existing duplicate
  local -a unique=()
  for runner in "${RUNNERS[@]}"; do
    [[ $runner =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "invalid runner name: $runner"
    [[ -d $SKILL_SOURCE/runners/$runner ]] || fail "runner source missing: $SKILL_SOURCE/runners/$runner"
    duplicate=0
    for existing in "${unique[@]}"; do
      [[ $runner == "$existing" ]] && duplicate=1
    done
    ((duplicate)) || unique+=("$runner")
  done
  RUNNERS=("${unique[@]}")
}

resolve_profile_target() {
  if [[ $PROFILE_SELECTION == */* ]]; then
    local profile_path
    profile_path=$(PROFILE_SELECTION="$PROFILE_SELECTION" python3 -c 'import os; print(os.path.realpath(os.path.expandvars(os.path.expanduser(os.environ["PROFILE_SELECTION"]))))')
    [[ $profile_path != / ]] || fail "OMP profile path is invalid"
    PROFILE_NAME=$(basename "$profile_path")
    PROFILES_ROOT=$(dirname "$profile_path")
  else
    [[ -n $PROFILE_SELECTION && $PROFILE_SELECTION != . && $PROFILE_SELECTION != .. ]] \
      || fail "OMP profile name is invalid"
    PROFILE_NAME=$PROFILE_SELECTION
  fi
}

require_omp_profile_selection() {
  runner_selected omp || fail "profile is OMP-only; select it with --runner omp"
}

install_skill() {
  local destination="$OMP_SKILLS_ROOT/smart-cascade" runner
  info "installing Smart Cascade Skill"
  info "  core    from $SKILL_SOURCE"
  info "  runners ${RUNNERS[*]}"
  info "  to      $destination"
  run mkdir -p "$(dirname "$destination")"
  run rm -rf "$destination"
  if [[ $DRY_RUN == 1 ]]; then
    printf '  [dry-run] copy core and selected runners excluding __pycache__ and *.pyc\n'
    return
  fi
  mkdir -p "$destination/runners"
  tar -C "$SKILL_SOURCE" --exclude='./runners' --exclude='__pycache__' --exclude='*.pyc' -cf - . \
    | tar -C "$destination" -xf -
  for runner in "${RUNNERS[@]}"; do
    tar -C "$SKILL_SOURCE/runners" --exclude='__pycache__' --exclude='*.pyc' -cf - "$runner" \
      | tar -C "$destination/runners" -xf -
  done
}

copy_tree() {
  local source=$1 destination=$2 label=$3
  [[ -d $source ]] || fail "$label source missing: $source"
  info "installing $label"
  info "  from $source"
  info "  to   $destination"
  run mkdir -p "$(dirname "$destination")"
  run rm -rf "$destination"
  # tar rather than cp -a so build artifacts stay out of the installed tree
  if [[ $DRY_RUN == 1 ]]; then
    printf '  [dry-run] copy tree excluding __pycache__ and *.pyc\n'
  else
    mkdir -p "$destination"
    tar -C "$source" --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$destination" -xf -
  fi
}

report_tree_drift() {
  local source=$1 destination=$2 label=$3
  if [[ ! -d $destination ]]; then
    info "  $label  not installed"
  elif diff -qr --exclude='__pycache__' --exclude='*.pyc' "$source" "$destination" >/dev/null; then
    info "  $label  in sync"
  else
    info "  $label  differs"
  fi
}

report_skill_drift() {
  local destination="$OMP_SKILLS_ROOT/smart-cascade" runner temporary differs=0
  if [[ ! -d $destination ]]; then
    info "  skill  not installed"
    return
  fi
  temporary=$(mktemp -d)
  mkdir -p "$temporary/runners"
  tar -C "$SKILL_SOURCE" --exclude='./runners' --exclude='__pycache__' --exclude='*.pyc' -cf - . \
    | tar -C "$temporary" -xf -
  for runner in "${RUNNERS[@]}"; do
    tar -C "$SKILL_SOURCE/runners" --exclude='__pycache__' --exclude='*.pyc' -cf - "$runner" \
      | tar -C "$temporary/runners" -xf -
  done
  diff -qr --exclude='__pycache__' --exclude='*.pyc' "$temporary" "$destination" >/dev/null || differs=1
  rm -rf "$temporary"
  [[ $differs == 0 ]] && info "  skill  in sync" || info "  skill  differs"
}

report_profile_drift() {
  local destination="$PROFILES_ROOT/$PROFILE_NAME/agent"
  if [[ ! -d $destination ]]; then
    info "  profile $PROFILE_NAME  not installed"
    return
  fi
  local differs=0 role agent
  for agent in "$OMP_PROFILE_SOURCE"/agents/*.md; do
    [[ -e $agent ]] || break
    cmp -s "$agent" "$destination/agents/$(basename "$agent")" || differs=1
  done
  for role in "$OMP_RUNNER_SOURCE"/roles/*.md; do
    cmp -s "$role" "$destination/agents/$(basename "$role")" || differs=1
  done
  cmp -s "$OMP_PROFILE_SOURCE/config.yml" "$destination/config.yml" || differs=1
  [[ $differs == 0 ]] && info "  profile $PROFILE_NAME  in sync" || info "  profile $PROFILE_NAME  differs"
}

cmd_verify() {
  local failed=0
  info "=== required ==="
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    info "  python3  $(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
  else
    info "  python3  MISSING or < 3.11"
    failed=1
  fi
  if python3 -c 'import yaml' 2>/dev/null; then
    info "  PyYAML   ok"
  else
    info "  PyYAML   MISSING"
    failed=1
  fi

  info ""
  info "=== optional runtime ==="
  command -v bun >/dev/null 2>&1 && info "  bun      $(bun --version)" || info "  bun      missing (native smoke unavailable)"
  if runner_selected omp; then
    # OMP is typically installed by bun into ~/.bun/bin, which is often absent
    # from PATH. Do not fall back to `pi`: an unrelated package also provides it.
    local omp_bin="${SMART_CASCADE_OMP_BIN:-}"
    if [[ -z $omp_bin ]]; then
      local candidate
      for candidate in "$HOME/.bun/bin/omp" "$(command -v omp 2>/dev/null || true)"; do
        if [[ -n $candidate && -x $candidate ]]; then
          omp_bin="$candidate"
          break
        fi
      done
    fi
    if [[ -n $omp_bin && -x $omp_bin ]]; then
      local pkg_root="" probe
      probe="$(dirname "$(readlink -f "$omp_bin")")"
      while [[ $probe != "/" ]]; do
        if [[ -f $probe/package.json ]] \
           && grep -q '"@oh-my-pi/pi-coding-agent"' "$probe/package.json" 2>/dev/null; then
          pkg_root="$probe"
          break
        fi
        probe="$(dirname "$probe")"
      done
      if [[ -n $pkg_root ]]; then
        local pkg_version
        pkg_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
          "$pkg_root/package.json" 2>/dev/null || echo '?')"
        info "  omp      $omp_bin  (@oh-my-pi/pi-coding-agent $pkg_version)"
      else
        info "  omp      $omp_bin  (NOT owned by @oh-my-pi/pi-coding-agent)"
      fi
    else
      info "  omp      missing (production admission unavailable)"
    fi
  else
    info "  omp      skipped (runner not selected)"
  fi

  info ""
  info "=== source preflight ==="
  if SMART_CASCADE_PROJECT_ROOT="$REPO_ROOT" bash "$SKILL_SOURCE/bootstrap/init-environment.sh" >/dev/null 2>&1; then
    info "  CORE_READY"
  else
    info "  core preflight FAILED"
    failed=1
  fi

  info ""
  info "=== installation drift ==="
  report_skill_drift
  runner_selected omp && report_profile_drift
  report_tree_drift "$AUTOPILOT_SOURCE" "$HERMES_SKILLS_ROOT/$AUTOPILOT_RELATIVE" "autopilot"

  [[ $failed == 0 ]] || return 1
  info ""
  info "RESULT: required dependencies satisfied"
}

cmd_skill() {
  install_skill
}

cmd_omp_profile() {
  require_omp_profile_selection
  local destination="$PROFILES_ROOT/$PROFILE_NAME/agent"
  [[ -d $OMP_PROFILE_SOURCE ]] || fail "OMP profile source missing: $OMP_PROFILE_SOURCE"
  [[ -d $OMP_RUNNER_SOURCE/roles ]] || fail "OMP runner role source missing: $OMP_RUNNER_SOURCE/roles"
  info "installing OMP profile projection"
  info "  profile $PROFILE_NAME"
  info "  roles   from $OMP_RUNNER_SOURCE/roles"
  info "  config  from $OMP_PROFILE_SOURCE/config.yml"
  info "  to      $destination"
  run mkdir -p "$destination/agents"
  # The profile owns generic agent definitions; the OMP runner owns the
  # smart-cascade-* definitions checked by its adapter.
  local agent
  for agent in "$OMP_PROFILE_SOURCE"/agents/*.md; do
    [[ -e $agent ]] || break
    run cp "$agent" "$destination/agents/$(basename "$agent")"
  done
  local role
  for role in "$OMP_RUNNER_SOURCE"/roles/*.md; do
    run cp "$role" "$destination/agents/$(basename "$role")"
  done
  run cp "$OMP_PROFILE_SOURCE/config.yml" "$destination/config.yml"
  info "  runtime state untouched: models.yml, *.db, sessions/, terminal-sessions/, extensions/, logs/"
}

cmd_autopilot() {
  copy_tree "$AUTOPILOT_SOURCE" "$HERMES_SKILLS_ROOT/$AUTOPILOT_RELATIVE" "Autopilot supervision skill"
}

command=${1:-}
[[ $# -gt 0 ]] && shift || true
while [[ $# -gt 0 ]]; do
  case $1 in
    --runner) [[ $# -ge 2 && -n $2 ]] || fail "--runner needs a value"; RUNNERS+=("$2"); shift 2 ;;
    --profile) [[ $# -ge 2 && -n $2 ]] || fail "--profile needs a value"; PROFILE_SELECTION=$2; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --profiles-root) [[ $# -ge 2 && -n $2 ]] || fail "--profiles-root needs a value"; PROFILES_ROOT=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done
case $command in
  verify|skill|profile|all) validate_runners ;;
esac
case $command in
  verify|profile|all) runner_selected omp && resolve_profile_target ;;
esac

[[ $DRY_RUN == 1 ]] && { info "DRY RUN — no files will be written"; info ""; }
case $command in
  verify) cmd_verify ;;
  skill) cmd_skill ;;
  profile) cmd_omp_profile ;;
  autopilot) cmd_autopilot ;;
  all)
    cmd_skill
    if runner_selected omp; then info ""; cmd_omp_profile; else info ""; info "skipping OMP profile: omp runner not selected"; fi
    info ""
    cmd_autopilot
    ;;
  ""|-h|--help) usage ;;
  *) fail "unknown command: $command (see --help)" ;;
esac
