# 部署

Smart Cascade 分成三个独立安装层：

```text
~/.omp/skills/smart-cascade/                    Skill core 与选中的 runners/<name>/
~/.omp/profiles/<name>/agent/                  OMP runner 专属 profile 配置与 subagent 定义
~/.hermes/skills/autonomous-ai-agents/autopilot/  可选外部监督文档
<project>/.smart-cascade/                      queue、override 和运行状态
```

项目目录不再携带 bootstrap 代码。安装 Skill 后，代码位置与被检查项目完全解耦。

## 快速安装

```bash
./scripts/deploy.sh verify --runner omp --profile smart-cascade-omp
./scripts/deploy.sh skill --runner omp --dry-run
./scripts/deploy.sh profile --runner omp --profile smart-cascade-omp --dry-run
./scripts/deploy.sh autopilot --dry-run

./scripts/deploy.sh skill --runner omp
./scripts/deploy.sh profile --runner omp --profile smart-cascade-omp
./scripts/deploy.sh autopilot   # 仅需要外部监督时
```

`--runner NAME` 可重复；Skill core 始终安装，只复制选中的 `runners/<name>/`。省略 `--runner` 时默认 `omp`，因为它是当前唯一生产 runner，并保持旧命令兼容。`--profile NAME|PATH` 与 adapter 的 profile override 语义一致：名称安装到 profiles root 下，完整目录直接决定 root 与 name；默认 `smart-cascade-omp`。`all` 安装 Skill、选中 `omp` 时安装实际选中的 OMP profile，再安装 Autopilot。`--dry-run` 只打印计划；`--profiles-root DIR` 对 profile 名仍有效，完整 profile 路径优先。

## 依赖

- Python 3.11+：`tomllib`、core、adapter 与控制脚本。
- PyYAML：runner/profile 配置和项目 override。
- OMP：生产 admission 与原生 task/Hub 路径。
- Bun：仅原生 smoke。

## Skill

```bash
./scripts/deploy.sh skill --runner omp
```

安装平台无关 core 和选中的 runner 到 `~/.omp/skills/smart-cascade/`。例如只选 `omp` 时包含：

```text
SKILL.md
bootstrap/{initialize,contracts,frontier,state,validate-queue}.py
bootstrap/{init-environment.sh,manifest.json,runner-interface.json,root-init.md}
scripts/smart_cascade_dispatch.py
runners/omp/{adapter,normalize,test-adapter}.py
runners/omp/runner-launch.yaml
runners/omp/roles/*.md
```

其他未选中的 `runners/<name>/` 不会出现在安装树。确定性测试随 core/所选 runner 保留，`__pycache__` 和 `*.pyc` 始终排除。Skill 自包含，不引用 Autopilot 目录，也不要求目标项目与 Skill 位于同一目录树。

## OMP profile

```bash
./scripts/deploy.sh profile --runner omp [--profile NAME|PATH] [--profiles-root DIR]
```

`profile` 是 OMP runner 专属安装动作；没有选择 `omp` 会直接失败。`--profile` 默认 `smart-cascade-omp`，可传名称或完整 profile 目录，安装目标与 adapter `check --profile` 一致。它同步两类 agent 定义到所选 `<profiles-root>/<profile-name>/agent/agents/`：profile 自带的 `sources/smart-cascade-omp/agent/agents/*.md`，以及 OMP runner 拥有的 `sources/smart-cascade-skill/runners/omp/roles/*.md`。后者是 OMP schema，不属于平台无关 Skill core；profile 是它们的安装投影，OMP adapter 也用同一份做身份核对。`config.yml` 来自 profile 源。不会触碰：

```text
models.yml  *.db  sessions/  terminal-sessions/  extensions/  logs/
```

`models.yml` 含本机 provider 配置，必须单独维护。`agent/models.redacted.yml` 仅用于核对模型角色形状。

`verify --runner omp --profile NAME|PATH` 才执行 OMP executable/package 探测，并对同一实际目标 profile 做 drift；未选 `omp` 时跳过这些 OMP 专属检查。Skill drift 只比较 core 与本次选中的 runner，不会因源树里存在未安装 runner 而误报。

## Autopilot

```bash
./scripts/deploy.sh autopilot
```

安装可选 Hermes 外部监督文档。Autopilot 只包含 `SKILL.md` 与 references，通过已安装的 `herdr` skill 完成 Root 启动、初始化、控制和观察；它不拥有生产调度或 Git。

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
  bash ~/.omp/skills/smart-cascade/bootstrap/init-environment.sh
```

预期 `CORE_READY`。显式授权后创建运行目录：

```bash
SMART_CASCADE_PROJECT_ROOT=/path/to/project \
SMART_CASCADE_CREATE_STATE=1 \
  bash ~/.omp/skills/smart-cascade/bootstrap/init-environment.sh
```

## 验证

```bash
python3 sources/smart-cascade-skill/runners/omp/test-adapter.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-contracts.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-dispatch.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-frontier.py
python3 sources/smart-cascade-skill/scripts/test-smart-cascade-state.py

bun run sources/smart-cascade-omp/smoke/run.ts
bun run sources/smart-cascade-omp/smoke/recovery.ts
```

Smoke 会调用真实 OMP runtime 和 provider；外部 API 阻塞不等于 deterministic core 失败。
