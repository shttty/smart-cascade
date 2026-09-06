# 安装与配置（给 Agent）

用户将本页交给任意兼容 Agent 执行。安装使用通用 Skills CLI；复用用户已有、可以调用模型的 profile。首次安装和升级都走本页，不需要独立初始化 Skill。

先与用户确认使用哪个 runner，再按对应小节配置。`<skill-root>/runners/` 下的每个目录是一个可选 runner，各自带 adapter、normalization、launch 配置和角色定义。当前该目录只有 `omp/`，因此除非用户另有指定，选择 `omp`；Codex 和 Claude Code runner 计划后续加入。下文第 3、4 节是 OMP runner 的配置与验证；选择其他 runner 时改读该 runner 目录下的对应配置，不要把 OMP 的 profile 和角色写法套用过去。

## 1. 检查目标与依赖

- 确认所选 runner，以及它的运行目标。以下以 OMP runner 为例。
- 确认目标 OMP profile；安装 Agent 不在目标 OMP session 中时，先明确目标，不把安装 Agent 自己的环境当成 runner。
- 在目标 profile 的环境中运行 `omp --version`、`omp config path`、`omp models --json --no-extensions` 和 `omp config get modelRoles --json`。记录实际 agent 目录、可用 selector 和已有角色。`config path` 返回纯路径文本。
- Python 3.11+、PyYAML 和 OMP 18.0+ 是必要依赖。只补缺失项；安装软件前确认。没有可用模型时停在这里，让用户通过 OMP 自己完成 provider 配置；不请求、打印、复制或保存凭据。
- Bun 只在开发者原生 smoke 验证时单独检查。Autopilot 和 `ponytail` 都不是安装前提。

## 2. 安装 Skill

```bash
npx skills add https://github.com/shttty/smart-cascade/tree/main/sources/smart-cascade-skill --skill smart-cascade --agent universal --copy -g -y
```

安装源固定到主 Skill 子目录；仓库根级扫描可能先选中 `archive/` 中同名的历史 Skill。保留历史材料，不用根级同名匹配代替上面的精确来源。

记录 CLI 实际安装目录，以下称 `<skill-root>`。确认目标 OMP 能发现其中的 `SKILL.md`，且同目录保留完整 `bootstrap/`、`scripts/`、`runners/omp/`。若 CLI 不可用，将仓库的 `sources/smart-cascade-skill/` 完整复制到目标 OMP 实际 agent 目录的 `skills/smart-cascade/`；不把 bootstrap 复制进用户项目。

升级前备份将被替换的 Skill。检查同名旧副本和加载优先级：universal 全局安装当前实际写入 `~/.agents/skills/smart-cascade/`（跨 profile 可见），而 OMP native 的 `~/.omp/agent/skills/`（命名 profile 为 `~/.omp/profiles/<profile>/agent/skills/`）优先级更高，其中的旧副本会遮蔽共享副本。发现冲突时先展示冲突位置并确认迁移，不静默删除用户文件。以目标 session 实际加载的路径为准，不以“目录存在”代替成功。

## 3. 配置 OMP runner

保留已有且可解析的六角色映射；缺项时仅从刚才查询到的可用模型中建议：

- `smart-cascade-root`、`smart-cascade-leader`、`smart-cascade-advisor`、`smart-cascade-escalated-semantic`：优先已有 `default` 模型。
- `smart-cascade-semantic`、`smart-cascade-mechanical`：优先已有 `smol`，否则使用 default。
- 只有一个可用模型时，六角色都可用它；默认映射不可用时展示可用 selector 让用户选择，不猜 provider/model。

一次展示完整六角色映射、目标 profile 和必要设置差异，确认后才写入。先备份将替换的配置和 Smart Cascade 角色文件。通过 `omp config set modelRoles '<合并后的完整 JSON 映射>' --json` 写入六角色，保留其他已有角色；不要用只有六项的映射覆盖整个 `modelRoles`。

在同一目标 profile 环境中设置以下 native 边界；其余设置保持原样：

```bash
omp config set async.enabled true --json
omp config set task.batch true --json
omp config set task.maxRecursionDepth 2 --json
omp config set task.isolation.mode auto --json
omp config set task.isolation.apply false --json
omp config set task.isolation.merge patch --json
```

将 `<skill-root>/runners/omp/roles/*.md` 同步到已确认的 `<agent-dir>/agents/`。只同步 Smart Cascade 自己的五个角色定义；已有自定义差异先展示确认。provider、凭据、其他 agents 和 runtime state 保持不变。

### 可选：ponytail

角色保留 OMP 原生 `autoloadSkills: [ponytail]`：OMP 只加载目标 session 已发现的同名 Skill，未发现时跳过。已有则使用；没有则继续，不自动安装、不要求用户补装，也不作为 admission 或任务运行的阻塞项。

## 4. 验证与交付（OMP runner）

在同一目标 profile 下读回六角色映射和上面的必要设置，核对角色文件。随后用临时目录作为 project root 运行现有 admission：

```text
python3 <skill-root>/runners/omp/adapter.py check \
  --project-root <temporary-directory> \
  --omp-bin <actual-omp-executable> \
  --profile <full-profile-directory>
```

`<full-profile-directory>` 是已确认 `<agent-dir>` 的父目录，包含 `agent/`；不能把 agent 目录本身当成 profile 传入。检查命令会在临时 project 下记录 profile override；清理该临时目录，不改用户项目。

要求真实回执为 `ADAPTER_READY`，并报告实际 Skill 路径、profile 路径、最终六角色映射，以及 `ponytail` 已发现或已跳过。配置写入或读回失败时报告实际差异和备份位置，不宣布完成。安装不运行生产 smoke、不派生产任务；admission 成功也不等于完整生产链路已经实测。已有 session 尚未加载新配置时提示用户重载或另开同一 profile，不能把磁盘配置当成已生效的 session 状态。

## Autopilot

```bash
npx skills add shttty/smart-cascade --skill autopilot
```

Autopilot 位于 `sources/autopilot-skill/`，通过 `npx skills` 安装到用户选择的兼容 agent。它包含 `SKILL.md`、references 与 `scripts/`（`agent-watch.sh` 守望、`config.sh` 共享配置读取），通过 Herdr 自带的官方 skill 完成 Root 启动、初始化、控制和观察；它不拥有生产调度或 Git。

### commit 边界的双重验收

启用 Autopilot 后，Root 的 commit 对话不再自动走过去。Root 完成 slice 验收弹出对话时进入 `blocked`，`agent-watch.sh guard` 阻塞在 `herdr agent wait --until idle --until done --until blocked` 上被这个事件唤醒；Autopilot 取消自动选中的 commit 步骤按住边界，另起一个 pane 启动 verifier agent 独立跑一遍项目的高层验证入口，Root 自己也跑一遍。两份读数一致且通过才放行，否则作为 finding 交回 Root 走 `REWORK`。

verifier 的产出是边界证据而非 slice 判决：`PASS` / `REWORK` / `BLOCKED` 归 Root，Autopilot 不自己跑项目验证命令，也不 commit。

行为由 `autopilot-config.yaml` 控制：`commit_boundary.answer` 取 `recommend`（超时后自动选推荐值）或 `ask`（每次问人），`commit_boundary.auto_select_after_seconds` 是超时秒数，`verifier.enabled: false` 可跳过交叉检查只保留 Root 自己那份读数，`observation.interval_minutes: 0` 关闭周期观察（完成与 blocker 事件不受影响，始终即时）。

Smart Cascade adapter 只提供 admission `check`。运行时正确性由 Root 对 settlement、patch、checks 和 integration 的 candidate 验收保证。

## 项目配置

项目只需：

```text
.smart-cascade/queue.toml
.smart-cascade/override.yaml   # 可选，本地 profile 选择
.smart-cascade/control/        # 运行时 receipts/dispatches
.smart-cascade/state/          # 最小 rework counters
```

`adapter.py check --profile <name-or-full-path>` 成功后写入 `override.yaml`，字段只有 `profile_name` 与 `profiles_root`。未传 `--profile` 时先读 override，没有则使用 `runner-launch.yaml` 的默认 `profile_name`。

运行 core preflight：

```bash
SMART_CASCADE_PROJECT_ROOT=/path/to/project \
  bash "<skill-root>/bootstrap/init-environment.sh"
```

预期 `CORE_READY`。显式授权后创建运行目录：

```bash
SMART_CASCADE_PROJECT_ROOT=/path/to/project \
SMART_CASCADE_CREATE_STATE=1 \
  bash "<skill-root>/bootstrap/init-environment.sh"
```

## 开发者验证（不属于安装流程）

```bash
python3 sources/smart-cascade-skill/runners/omp/test-adapter.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-frontier.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-state.py

bun run sources/smart-cascade-omp/smoke/run.ts
bun run sources/smart-cascade-omp/smoke/recovery.ts
```

Smoke 会调用真实 OMP runtime 和 provider；外部 API 阻塞不等于 deterministic core 失败。
