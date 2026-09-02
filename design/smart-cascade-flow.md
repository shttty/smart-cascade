# Smart Cascade 实现规格

状态：当前实现主规格。实现 Smart Cascade 时以本文件为唯一流程来源；[`decisions.md`](decisions.md) 只记录取舍理由。已废弃的 Smart Cascade 自有 runtime 方案仅保留在维护者本地归档，不作为实现依据。

## 1. 定位

Smart Cascade 是一个运行工作流，入口是当前 Agent session 中的 `smart-cascade` Skill。

任务规划、需求拆分、ticket 编制属于前置工作，由 `to-ticket`、重构规划或其他规划 Skill 完成。Smart Cascade 不抢任务规划，也不负责创建或改写任务队列。

Smart Cascade 只消费一份已经存在的、符合规范的静态队列：

```text
.smart-cascade/queue.toml
```

## 2. 外部承载是可选项

Herdr 不是 Smart Cascade 的必要依赖。当前实现目标使用 native OMP task、Agent Hub、structured settlement 和 `isolated=true` patch retention；Herdr 只可选地承载或监督 Root session。

Autopilot 是与用户对接的外部控制和监督层，但不是 Root 正常生产路径中的第二个调度器或验收者：

- 人类可以直接监督当前运行；
- Autopilot 可以远程观察、提醒、报告、暂停、恢复和介入；
- Root 拥有生产调度和 slice 内技术验收权；
- 用户与 Autopilot 决定是否接受 Root 的结果、是否要求继续返工；
- Autopilot 可以因为边界、身份、证据或恢复问题阻断 Root，但不在正常路径上重复裁决每个 candidate；
- Herdr 只是用户或 Autopilot 可以选择的 transport/承载方式；
- Smart Cascade 不启动 Herdr，也不创建或猜测要接管的 session、workspace、pane。

用户或 Autopilot 负责决定：

```text
使用哪个承载工具
连接哪个 session
观察或接管哪个 Root
```

Root 不需要 Autopilot 驻留在每个 child 调度步骤上，可以脱离外部监督独立完成自己的生产闭环；Autopilot 在 Root 报告、请求外部决定、需要恢复或出现边界问题时重新接入。

## 3. 启动方式

推荐流程：

```text
启动普通 Agent session
  → 完成前置任务
  → 建立明确 Git checkpoint
  → 调用 smart-cascade Skill
  → 检查 queue 是否存在并通过机械校验
  → 展示运行边界
  → 明确询问用户是否开始
  → 用户确认
  → 当前 session 原地成为 Root
  → Root 执行完整 Smart Cascade
```

`smart-cascade` Skill 不应：

- 启动另一个 Agent session；
- 启动 Herdr；
- 创建 workspace、pane 或 worktree；
- 自动创建 queue；
- 自动修复 queue；
- 用户未确认就开始流水线。

用户确认的含义是：接受当前 queue、当前 Git 基线和当前运行边界，并允许 Root 开始生产调度。

## 4. 运行前置条件

Smart Cascade 启动前只要求：

1. `.smart-cascade/queue.toml` 存在；
2. queue 通过机械验证；
3. 当前 OMP profile 支持 native task、Agent Hub 和 session resume；
4. 写任务使用 `isolated=true`，profile 配置为 `task.isolation.mode=auto`、`apply=false`、`merge=patch`；
5. 子任务使用 strict structured settlement；
6. 父级能读取并验证 native task 返回的 authoritative retained patch，再串行应用；
7. 用户明确确认开始。

queue 的生成不属于 Smart Cascade。符合 Smart Cascade 要求的 queue 应由独立的 Queue 编制 Skill 生成或审查。它可以接收 `to-ticket`、重构计划和其他任务拆分产物。

Smart Cascade 对已有 queue 做的是拒绝无效输入，而不是重新设计任务：

```bash
python3 ~/.omp/skills/smart-cascade/bootstrap/validate-queue.py .smart-cascade/queue.toml
```

## 5. Queue 的职责

`.smart-cascade/queue.toml` 是静态输入，只描述顶层 slice：

```toml
[[slices]]
id = "stable-slice-id"
depends_on = []
scope = "一个有明确完成条件的顶层目标"
write_set = ["src/**"]
checks = ["具体、可运行的检查命令"]

```

Queue 不包含：

- child 列表；
- pending/working/rework 等运行状态；
- attempt；
- worktree；
- patch 路径；
- Agent/session；
- candidate；
- 运行原因和结果；
- `parallel` 标志。

顶层 slice 可以比传统按“核心实现、测试、文档”分类的拆分更细，但 queue 仍然只表达用户目标和顶层边界。具体 child 由 Leader 读代码后动态决定。

## 6. Root 的职责

用户确认后，当前 session 作为 Root。Root 是唯一的顶层生产协调者，也是运行内的技术验收 authority，负责：

- 读取完整 queue；
- 根据依赖和写集计算可执行 slice；
- 启动每个 slice 的 Leader；
- 验证 Leader 返回的 candidate、patch、changed paths、postcondition 和 checks；
- 冻结候选；
- 决定 slice 通过或返工；
- 执行 Git commit/integration；
- 推进依赖；
- 继续无关的可执行 slice；
- 在必要时请求 Advisor；
- 处理最终阻塞和清理。

Root 不直接替代 Leader/Executor 完成产品实现。

Root 的 `PASS` 是对当前 slice contract、postcondition 和 checks 的技术验收，不等于用户对最终交付的接受。Root 可以在技术上通过后继续独立推进；Root 报告结果后，用户与 Autopilot 决定是否收货、是否重新打开该 slice，或是否要求继续返工。

Root 必须验证 Leader settlement、authoritative retained patch、实际 changed paths、queue checks 和 slice postcondition。需要执行写入型或会污染现场的最终检查时，Root 从明确 base 加载 Leader patch 到一次性验证 candidate；不能用 Leader 自报结果替代 Root 的最终技术判断。

Root 负责 slice candidate 的有效性、最终验证和 Git 操作；native OMP 为 Leader 创建 `isolated=true` candidate。Leader 在自己的 isolation 中组装 child patch。Root 不在 Leader 运行期间修改同一生产基线；只有在 Leader settlement 或被终止并交出可验证 patch 后，Root 才进行最终验证和 commit/integration。

Slice 层流程：

```text
Root 启动 Leader
  → Leader 动态拆 child 并执行
  → Leader 返回候选和证据
  → Root 验证候选
  → Root 技术通过：commit/integration、推进依赖
  → Root 不通过：决定 slice REWORK
  → Root 或 Leader 因能力不足：请求 Advisor
```

## 7. Leader 的动态 patch decomposition

Leader 不按预先规划的功能类别拆 child，也不要求 queue 预先列出 child。

Leader 先读取实际代码，然后描述：

- 哪个文件大概哪里需要修改；
- 预期达到什么效果；
- 允许修改的路径；
- 必须满足的 postcondition；
- 需要执行的 focused check。

只要一个修改可以作为独立 patch 生成、验证和合并，就可以派出一个 Executor。

例如：

```text
child-a
  file: src/runtime.ts
  region: loadConfig 附近
  effect: 调整配置优先级

child-b
  file: src/runtime.ts
  region: reconcileSession 附近
  effect: 处理已删除 session

child-c
  file: tests/runtime.test.ts
  region: session recovery tests
  effect: 增加对应回归覆盖
```

这些 child 不是“核心实现/边界行为/测试”三种类别，而是三个独立 patch。

### 同一文件的激进拆分

已经处于 native OMP isolation 时，同一文件允许多个并行 Executor：

- 没有已知逻辑依赖；
- 预计 hunks 不重叠；
- 每个修改的效果可以单独描述；
- Leader 可以在取得 patch 后按确定顺序串行应用。

不要求 Leader 在执行前证明绝对安全。默认策略是乐观拆分：

```text
预计独立且 hunks 不重叠 → 拆成多个 child
已知有逻辑依赖或必须共享中间状态 → 合并 child
不确定但没有已知依赖 → 先拆，使用真实 patch 验证
```

并行的是 patch 生成；patch 应用仍由 Leader 串行完成；最终以累计 slice checks 验证组合结果。

### Native OMP isolation 与 patch 组装

Root 通过 native OMP task 为一个 slice 启动 `isolated=true` Leader。OMP 创建 Leader isolation；Leader 是该 isolated candidate 的唯一 assembly writer：

```text
Root
  → task(isolated=true) 启动 Leader
      → OMP 创建 Leader isolated candidate
      → Leader 以 task(isolated=true) 启动 Executor
          → OMP 创建 Executor isolation
          → Executor 实现并运行 focused check
          → native task settlement 返回 authoritative retained patch
      → Leader 在自己的 isolated candidate 中按确定顺序验证并应用 patch
      → Leader 运行组合后的 slice checks
  → Leader settlement 返回 assembled retained patch 和证据
  → Root 验证，必要时加载到一次性 verification candidate
  → Root 技术 PASS 后 apply、commit/integration
```

约束如下：

- Executor 只写自己的 OMP isolation，不直接写 Leader candidate；
- Executor isolation 由 native OMP `isolated=true` task 从当前 parent candidate 上下文准备；
- Executor 返回 patch 和证据，不为 child 创建生产 commit；
- Leader 负责 patch 的保守检查、串行应用、冲突处理和组合验证；
- Leader 在 assembly 期间是自己的 isolated candidate 的唯一写入者；
- Leader settlement 或被 Root 终止并交出可验证 patch 后，Root 才能做最终验证和 Git 操作；
- Leader 无法解决的冲突回到 child 重派、child 合并或 slice REWORK，不由 Root 直接替代 Leader 做普通产品实现。

因此，Root 拥有 candidate validity 和最终 Git authority，不等于 Root 是 child patch assembler；Leader 拥有 slice 内 assembly 写入权，也不因此获得最终 commit/integration authority。OMP 拥有临时 isolation 的创建、patch capture 和清理。

### 通过真实失败收敛写集

初次执行不因为假想冲突提前合并写集。

只有出现真实证据时，下一次 slice REWORK 才合并受影响的 child：

- patch 实际冲突；
- 实际 hunks 重叠；
- 累计 slice checks 因独立修改的组合产生意外；
- Leader 无法可靠裁决两个 patch 的组合方式。

只合并出问题的 child。无冲突且已经验证的 child 保留，不因局部失败让整个 slice 退化成一个 writer。

```text
第一次：尽量细分、尽量并行
  → 真实 patch 无冲突：保持粒度
  → 真实 patch 冲突或累计测试失败：下一次只合并相关写集
```

### 恢复后的 child 重新划分

slice 是稳定的产品目标、边界和验收契约；child 是 Leader 针对当前代码现场形成的临时执行分解。slice 恢复后允许重新观察现场并重新划分 child，不要求复原旧的 child 拓扑。

重新划分必须满足：

- 不扩大 slice 的 scope、write set、postcondition 或架构边界；
- 先检查当前 worktree、已应用变更和已有 artifact，再决定还缺什么；
- 旧 child 的 session/消息是历史上下文，不自动代表当前 child 仍然 active；
- child state 中的计数只在复用同一 logical child 时继续使用，重新形成的新 child 按当前分解处理；
- slice-level rework 不因重新划 child 而清零。

不为 child 重新划分引入 `plan`、`generation` 或额外的持久状态机。当前 child 拓扑和 Leader 的判断由可恢复的 OMP session 承载。

## 8. Executor 的职责

Executor 只处理一个具体 patch assignment，并在 native OMP 为它创建的独立 isolation 中工作：

- 读取指定文件和相关上下文；
- 只在自己的 isolation 中完成修改；
- 只触碰 packet 允许的路径；
- 运行指定的 focused checks；
- 返回结构化 settlement；
- 交付真实 patch。

小任务完成并交付 patch 后，child session 可以由 OMP 按原生策略清理；需要继续上下文时保留并复用 OMP session。child 的生命周期、session、settlement 和 patch artifact 由 native OMP task runtime 负责，不复制到 Smart Cascade 状态文件。

## 9. Advisor 的职责

Advisor 是按需创建的能力升级和独立复核 subagent，不属于正常的 Root → Leader → Executor 拓扑，也不是 Root 技术 PASS 的固定盖章角色。

### 触发条件

Advisor 可以在以下情况介入：

- 任务超出当前 Root 或 Leader 的能力范围；
- Leader 无法形成可靠的 child decomposition；
- Root 无法判断如何处理跨 child 或跨 slice 问题；
- 普通 REWORK 多次后仍未达标；
- 需要更强分析来定位复杂 bug、架构或恢复问题；
- 需要独立复核高风险 candidate。

### 不能绕过的边界

Advisor 不能解决：

- 用户未作出的产品决策；
- 权限不足；
- 未授权的 write set 扩大；
- 缺失凭据或外部环境；
- 未批准的架构范围；
- Root 的生产 Git authority。

Advisor 提供分析、方案、拆分建议、验证建议和复核证据；Root 仍负责运行内决定和执行，用户与 Autopilot 仍负责外部交付接受与继续返工的决定。

### REWORK 能力阈值

REWORK 次数按稳定的 logical slice 或 child 记录，不因更换临时 attempt、worktree、session 或模型而清零。

每当累计 REWORK 次数达到 3 的倍数，只产生一次升级建议，不自动创建 Advisor，也不自动阻塞当前生产闭环。升级动作按层级区分：slice 层可请求 Advisor；child 层先改派升级后的 semantic Executor，必要时再请求 Advisor。

```text
rework = 1 → 普通 REWORK
rework = 2 → 普通 REWORK
rework = 3 → 触发一次升级
rework = 4 → 普通 REWORK
rework = 5 → 普通 REWORK
rework = 6 → 再次触发一次升级
```

脚本在递增后判断：

```text
rework += 1
rework % 3 == 0 → 返回升级动作
否则            → 返回继续动作
```

升级建议只在第 3、6、9……次产生，不会因为 `rework > 2` 而在后续每次 REWORK 都重复自动创建 Advisor。升级后的执行仍保留累计次数。

## 10. Child 的升级路径

child 层由 Leader 管理。Leader 可以在 child 失败后再次派出同一 logical child 的新 Executor。

当 child 达到升级点时，升级的是 semantic Executor，不是 mechanical Executor。升级后的角色仍然是 Executor，不称为 Advisor，也不引入 `Advisor Executor` 混合角色：

```text
semantic Executor
  normal profile
      → child REWORK 达到 3 的倍数
escalated semantic Executor
  stronger profile
```

具体 model/provider/effort 由 runner 配置映射，不写死在 Smart Cascade 流程中。若 runner 将 `luna:max` 配置为 stronger profile，它仍然属于 escalated semantic Executor；`luna:max` 不是 Advisor。Mechanical Executor 只处理已完全确定的机械变换，不因为机械任务失败就盲目切换到 stronger semantic profile。如果机械任务出现语义歧义，返回 blocker，由 Leader 改派 semantic Executor。

Escalated semantic Executor 仍然无法完成时，Leader 通过交接通信报告真实原因，再决定请求 Advisor、合并相关 child 写集、阻塞该链或向用户升级。

## 11. 极简持久状态

持久状态不是生产事实数据库，也不是 OMP 生命周期副本。Root 和 Leader 的运行上下文、进度、当前 children 拓扑和判断由各自的 OMP session 承载；状态文件只保留跨 session 丢失后仍需要的 rework 计数。

只记录：

```text
rework 次数
```

不记录：

- pending；
- working；
- done；
- blocked；
- advisor；
- generation；
- owner_epoch；
- attempt；
- 原因；
- patch；
- checks；
- session/worktree；
- 当前 children 拓扑；
- candidate/evidence；
- Git commit。

这些信息分别由 queue、OMP subagent session、真实 patch/Git 结果和 Agent 交接通信提供。

### 状态文件结构

Root 和每个 slice/Leader 各有一份 state 文件；不建立 `children/` 二层目录：

```text
.smart-cascade/
└── state/
    ├── state.toml
    └── slice-a/
        └── state.toml
```

Root 的主状态只记录所有顶层 slice 的 slice-level rework：

```toml
# .smart-cascade/state/state.toml

[slices."slice-a"]
rework = 1
```

每个 slice 的状态只记录该 slice 的 child-level rework：

```toml
# .smart-cascade/state/slice-a/state.toml

[children."child-a"]
rework = 0

[children."child-b"]
rework = 2
```

child 在 Leader 动态拆分并实际派出时创建计数记录。state 中的 child 条目是计数，不是 active 拓扑；旧 child 条目不会因为存在就被视为当前 child，也不需要为重新划分建立 generation 或历史目录。

Root 只写 Root 状态文件；每个 Leader 只写自己 slice 的状态文件。由于正常路径按文件分离写入，不需要 owner epoch 或跨角色状态机；脚本内部使用临时文件和原子替换，防止写入中断。Leader 被 Root 终止后，迟到消息按已终止的 session/attempt 处理，不得覆盖当前 Root 对现场的判断。

### 状态脚本

不使用“根据参数数量猜测目标层级”的接口。slice 和 child 使用明确的命令空间；模型不直接编辑 TOML。

```bash
state.py slice get <slice-id>
state.py slice rework <slice-id>

state.py child get <slice-id> <child-id>
state.py child rework <slice-id> <child-id>
```

第一个参数明确说明要操作 Root 的 slice 状态还是 Leader 的 child 状态，后续参数固定，不依赖参数数量推断目标文件。

查询：

```bash
state.py slice get slice-a
state.py child get slice-a child-a
```

脚本只返回当前计数和动作结果。例如：

```text
slice-a rework=2
slice-a/child-a rework=1
```

更新命令自动递增次数，并在递增后按 `rework % 3 == 0` 返回下一步动作：

```text
state.py slice rework slice-a
→ rework=3 action=suggest_advisor

state.py child rework slice-a child-a
→ rework=3 action=upgrade_executor
```

非 3 的倍数返回：

```text
action=continue
```

状态文件仍然只保存数字：

```toml
rework = 3
```

动作只存在于脚本本次输出中，不写入 `advisor`、`upgrade` 或其他状态字段。slice 层的升级动作是建议请求 Advisor；child 层的升级动作是先改派 escalated semantic Executor。升级后的 semantic Executor 仍失败时，再由 Leader 通过交接通信请求 Advisor 或升级用户。脚本不自动创建 Advisor，也不把 Advisor 设为验收门槛。

失败原因、阻塞原因、为什么需要 Advisor、为什么需要合并写集，都通过 Agent 交接消息和可恢复的 OMP session 传递，不写入状态文件。

## 12. 运行时交接

交接消息承担状态文件不承担的信息：

- child 完成或未达标；
- patch 路径和真实变更证据；
- 失败原因；
- blocker 类型；
- Advisor 请求；
- 建议合并哪些 child 的写集；
- 下一次 REWORK 的剩余目标；
- 用户需要决定的事项。

交接消息使用 native OMP Agent Hub；Hub 是当前 OMP 生产路径的运行时通信面，不承担 Smart Cascade 业务状态数据库职责。

外部 Autopilot 的完成通知不属于当前核心生产闭环。后续可以通过可选 hook 在 Root 完成技术验收或集成后发送通知；hook 只负责对接和提醒，不替代 Root 验收，也不应成为 Root 继续运行的必要依赖。hook 尚未实现时，Root 不等待它。

## 13. OMP session 中断与恢复

Leader 是 Root 管理的 OMP subagent session。OMP 会持久化 session JSONL、session metadata、child lineage 和 native isolation artifact；Root resume 后可以重新观察原 child，并在明确继续时通过 Hub revive 原 child session。

这条恢复路径是“恢复 Root，再显式继续 child”，不是新增状态机：

- 当前进行中的 model request、tool runtime、process-local queue、event subscription 和未完成子任务不保证恢复；
- 已完成并写入 session 的上下文可以继续对话；
- Root resume 不会让 child 自动继续执行；原 isolated child 会以 `parked` 被重新发现；
- Root 后续发送继续消息后，Hub 可以按原 child identity revive，并继续同一 child session 和 isolated worktree；
- Root 恢复后应先重新观察现场，再决定继续原 child、重新划分尚未完成的 child，或从最后已验证 candidate 显式重新派发；
- Leader session 不可恢复时，不把缺失上下文伪装成已恢复；Leader 是 Root 管理的 subagent，不是独立 authority，不需要 `owner_epoch`、lease 或 fencing。

Root 自身失联时，Autopilot 负责外部恢复和重新接入；Autopilot 不需要驻留在 Root 的正常 child 调度临界路径中。

## 14. 最终拓扑

```text
任务规划 Skill / to-ticket / 重构计划
  → 前置任务语义

Queue 编制 Skill
  → .smart-cascade/queue.toml

用户当前 Agent session
  → smart-cascade Skill
      → 检查 queue
      → 机械验证
      → 展示边界
      → 询问用户是否开始
      → 当前 session 成为 Root
          → 动态拆分并调度 Leader
              → 按 patch seam 调度 Executor
                  → 返回 patch
              → 验证并串行合并 patch
          → Root 技术验收 slice
          → 技术 PASS / REWORK / BLOCKED
          → Root 独立推进或向 Autopilot 报告

Herdr
  └─ 可选承载或监控 transport

Autopilot ↔ 用户
  └─ 外部观察、提醒、防偏离、恢复、交付接受与继续返工决定
```

## 15. 实现工作

实现按本规格完成以下产物，不再为这些事项重新做架构选型：

1. `smart-cascade` Skill 入口和 Root prompt；
2. Root/Leader 对 native OMP task、Agent Hub、status、strict settlement 和 retained patch 的直接编排；
3. `.smart-cascade/state/state.toml` 与 `.smart-cascade/state/<slice-id>/state.toml` 的 rework 计数脚本；
4. semantic Executor 与 escalated semantic Executor 的 runner profile 映射；具体 model/provider/effort 留在 runner 配置；
5. child packet、slice settlement、patch 冲突合并和精确 REWORK packet；
6. Root resume 后先观察 parked child、显式继续原 session、不可恢复时从最后已验证 candidate 重新派发；
7. Root 技术结果报告，以及用户要求继续返工时重新打开 slice 的接口；完成通知保持可选 hook。

实现不得反向扩大 queue，不得新增 Smart Cascade child registry、lifecycle state machine、lease、fencing、tombstone 或 plugin runtime，也不得重新把 Herdr 或 Autopilot 变成核心生产依赖。
