---
name: smart-cascade
description: "分层模型编排，适用于中等到复杂任务。必须通过 /smart-cascade 显式调用 — 永不自动触发。判断者接收所有任务：简单任务直接处理，复杂任务移交规划者。规划者规划并经顾问审查，然后拆分为原子任务分发给并行执行者 worker。Worker 失败时通过规划者→顾问升级链处理。"
---

# Smart Cascade — 分层模型编排

根据复杂度在判断者 → 规划者 → 顾问 → 执行者 worker 之间路由任务。
使用内联 advisor agent 调用进行层间升级。

## 调用方式

本 skill 必须**显式调用** — 永不自动触发。

```
/smart-cascade "构建用户认证的 REST API"
/smart-cascade "重构支付模块"
```

## 配置

在调用时指定参数可覆盖默认模型：

```
/smart-cascade --judge=sonnet --advisor=opus --planner=sonnet --executor=haiku "你的任务"
```

或在与本 skill 文件同级目录下创建 `smart-cascade.json` 配置文件来持久化偏好设置：

```json
{
  "judge": "sonnet",
  "advisor": "opus",
  "planner": "sonnet",
  "executor": "haiku"
}
```

手动创建或编辑此文件，无需每次调用时都指定参数。

| 角色 | 参数 | 内置默认值 | 用途 |
|---|---|---|---|
| **判断者（Judge）** | `--judge` | `sonnet` | 入口 — 复杂度检测、简单任务执行、移交规划者 |
| **顾问（Advisor）** | `--advisor` | `opus` | 深度审查、风险分析（Phase 2） |
| **规划者（Planner）** | `--planner` | `sonnet` | 规划、精炼、升级指导（Phase 1、3、5、5.5） |
| **执行者（Executor）** | `--executor` | `haiku` | 原子任务执行（Phase 4 worker） |

**解析优先级（从高到低）：**
1. 调用时传入的 CLI 参数（`--judge=...`）
2. 与 skill 文件同级的 `smart-cascade.json` 配置文件
3. 内置默认值（`sonnet` / `opus` / `sonnet` / `haiku`）

**读取配置：** 每次级联开始时，依次检查 CLI 参数、读取同级目录下的 `smart-cascade.json`（如存在）、最后回退到内置默认值，解析四个模型变量 — `{JUDGE_MODEL}`、`{ADVISOR_MODEL}`、`{PLANNER_MODEL}`、`{EXECUTOR_MODEL}`。接受任何有效的 Claude 模型 ID（如 `claude-opus-4-5`、`claude-sonnet-4-5`、`claude-haiku-4-5`）。

## Phase 0：复杂度门控

**判断者**接收所有任务，评估复杂度并路由：

| 复杂度 | 信号 | 操作 |
|---|---|---|
| **简单** | 单次问答、单文件、少于 3 步、无需规划 | 判断者直接处理 — 跳过级联 |
| **中等** | 多文件、功能实现、调试、需要规划 | 判断者移交规划者 — 从 Phase 1 进入级联 |
| **规划** | 架构设计、跨服务、需要任务拆分 | 判断者移交规划者 — 从 Phase 1 进入级联 |

如果是简单任务：**判断者直接执行** — 不分发任何 subagent，不进入级联。
如果是中等/规划任务：**判断者分发规划者 subagent** 并退出，规划者接管后续所有阶段。

**模型层级快捷路径：**
- **以 {JUDGE_MODEL} 运行：** 评估复杂度。简单 → 直接处理。中等/规划 → 分发 {PLANNER_MODEL} subagent 执行 Phase 1。
- **以 {PLANNER_MODEL} 运行：** 你由判断者移交而来。跳过 Phase 1 subagent 分发 — 直接自己规划，输出 `CONFIDENT:` 或 `UNCERTAIN:` 信号，然后进入 Phase 2。
- **以 {ADVISOR_MODEL} 运行：** 跳过 Phase 1 和 Phase 2 — 直接自己规划，然后进入 Phase 3 进行任务拆分。自我审查没有价值。

---

## Phase 1：规划者规划

生成一个 {PLANNER_MODEL} subagent 来尝试任务并自我评估信心。

```yaml
Agent:
  description: "规划者规划与信心评估"
  model: "{PLANNER_MODEL}"
  prompt: |
    你是一个规划-执行者。尝试完整规划（在适用的情况下实现）以下任务。
    仔细考虑范围、风险和方法。

    完成尝试后，在响应末尾单独一行输出以下信心信号之一：
      CONFIDENT: <一句话总结你的计划>
      UNCERTAIN: <一句话描述你不确定的地方>

    不要省略信心信号，它驱动下一步操作。

    <task>
    {用户的任务}
    </task>

    <context>
    {从对话历史构建的紧凑交接 — task / situation / blocked_on / attempted / files_in_play}
    </context>
```

分别捕获规划者的完整响应和信心信号。

**解析信心信号：** 从最后一行向上扫描。匹配第一个以 `CONFIDENT:` 或 `UNCERTAIN:` 开头的行。如果在最后 10 行内都未找到，视为 UNCERTAIN 并注明："规划者响应中缺少信心信号"。

---

## Phase 2：顾问咨询

根据规划者的信心信号分为两条路径。

### Path A — UNCERTAIN：顾问深度求解

从规划者的 Phase 1 输出构建紧凑交接，然后直接生成顾问：

```yaml
Agent:
  description: "顾问深度求解 — 规划者不确定"
  model: "{ADVISOR_MODEL}"
  prompt: |
    你是一个顾问。仅提供深度专家指导 — 不做实现。
    充分思考权衡、风险、边界情况和替代方案。

    如果以下交接信息不足以自信地给出建议，仅回复：
      NEED_MORE_CONTEXT: <一句话 — 具体缺少什么>
    否则按以下结构回复：
    1. **评估** — 当前情况是什么
    2. **建议** — 应该做什么以及为什么
    3. **风险** — 可能出什么问题
    4. **步骤** — 具体的下一步操作（这些将被提炼后传递给执行者）

    <handoff>
    task: <一行 — 规划者试图规划什么>
    situation: <来自规划者 Phase 1 尝试的 2-3 句话>
    blocked_on: <规划者的 UNCERTAIN 信号原文>
    attempted:
    - 规划者 Phase 1 尝试 → {规划者尝试了什么以及在哪里不确定}
    </handoff>
```

如果顾问返回 `NEED_MORE_CONTEXT`，附加对话摘录并重新分发一次。如果仍然不足，带着规划者的 Phase 1 输出和缺口说明继续进入 Phase 3。

### Path B — CONFIDENT：顾问轻量审查

生成一个简短的顾问审查：

```yaml
Agent:
  description: "顾问轻量审查规划者计划"
  model: "{ADVISOR_MODEL}"
  prompt: |
    简要审查以下计划。你不需要实现任何东西。
    识别：缺口、风险、遗漏的边界情况或排序问题。
    简洁 — 这是健全性检查，不是深度审计。
    如果计划可靠，用一句话说明并停止。

    <planner_plan>
    {规划者 Phase 1 的完整响应}
    </planner_plan>

    按以下结构回复：
    - **Verdict**: SOLID | NEEDS_REVISION
    - **Issues**（如果 NEEDS_REVISION）：要点列表，具体且可操作
    - **Suggestions**：可选，最多 3 条
```

---

## Phase 3：规划者精炼 + 计划拆分

将顾问反馈回传给规划者，然后拆分为原子任务。

**基于 Phase 2 结果的精炼轮数：**
- **Path B → SOLID**（或 Phase 2 被跳过）：0 轮精炼 — 分发 Phase 3 agent 仅做任务拆分（无需精炼，但拆分仍需要一次规划者 pass）。
- **Path B → NEEDS_REVISION**：1 轮精炼，解决顾问提出的具体问题，然后任务拆分。
- **Path A（顾问深度求解）**：始终 1 轮精炼 — 规划者之前不确定，顾问提供了实质性指导，必须纳入。
- 如果 1 轮后计划仍有未解决的缺口，仍然继续任务拆分并附带缺口说明：`> *精炼未完全收敛 — 带着已知缺口继续：{list}*`

**模型层级快捷路径：** 如果编排器本身就是 {PLANNER_MODEL}，直接执行精炼和任务拆分 — 不分发规划者 subagent。这同样适用于 Phase 5 升级顾问和 Phase 5.5 集成检查：规划者编排器内联处理这些工作，而不是分发规划者 subagent。当以 {EXECUTOR_MODEL} 或 {ADVISOR_MODEL} 运行时分发规划者 subagent。

```yaml
Agent:
  description: "规划者精炼与任务拆分"
  model: "{PLANNER_MODEL}"
  prompt: |
    你有一个初始计划。{如果存在 advisor_feedback："一位顾问已审查了它 —
    在拆分之前先解决他们的反馈。" 否则：
    "未执行顾问审查 — 直接进行任务拆分。"}

    <initial_plan>
    {Phase 1 计划 — 来自规划者 subagent，或编排器自己直接规划的}
    </initial_plan>

    {仅在顾问反馈存在时包含此块：}
    <advisor_feedback>
    {顾问 Phase 2 响应}
    </advisor_feedback>

    输出你精炼后的计划，然后以以下精确的 JSON 格式结尾
    （使用 JSON 而非 YAML — 解析更可靠）：

    TASK_LIST_START
    [
      {
        "id": "T1",
        "title": "一行标题",
        "description": "2-3 句话：做什么，而非怎么做",
        "inputs": "此任务依赖的文件、数据或结果",
        "outputs": "此任务产出什么",
        "acceptance": "一行：如何验证正确完成",
        "depends_on": []
      },
      {
        "id": "T2",
        ...
      }
    ]
    TASK_LIST_END

    任务列表规则：
    - 每个任务必须能由单个模型一次完成
    - 任何任务都不应需要架构决策 — 这些在计划中已解决
    - 最大化并行：仅在严格必要时添加 depends_on
    - 通常 3-8 个任务；超过 10 个说明计划需要进一步精炼
```

**解析任务列表：** 提取 `TASK_LIST_START` 和 `TASK_LIST_END` 标记之间的文本。解析为 JSON。如果 JSON 解析失败，尝试宽松解析（去除尾部逗号、修复未加引号的键）。如果仍然失败，要求规划者仅重新输出任务列表。

---

## Phase 4：执行者并行分发

根据依赖图按**波次**分发任务：

1. **Wave 0：** 所有 `depends_on` 为空的任务 — 并行分发。
2. **等待** Wave 0 完成。
3. **Wave 1：** 所有 `depends_on` 已满足的任务 — 并行分发。
4. **重复**直到所有任务都已分发。

如果检测到循环依赖，立即通知用户 — 任务拆分有问题。

**并发限制：** 每波次最多并行分发 **4 个 worker**。如果一个波次有超过 4 个就绪任务，多余的排队等待，有空位时再分发。

每个任务分配一个独立的执行者 worker agent：

```yaml
Agent:
  description: "执行者 worker — {task.id}: {task.title}"
  model: "{EXECUTOR_MODEL}"
  prompt: |
    你是一个执行者。严格完成以下任务，不要偏离范围。
    不要做架构决策 — 如果遇到需要决策的情况，报告 BLOCKED。

    <task>
    id: {task.id}
    title: {task.title}
    description: {task.description}
    inputs: {task.inputs}
    outputs: {task.outputs}
    acceptance: {task.acceptance}
    </task>

    <predecessor_outputs>
    {对于 depends_on 中每个已完成的任务，包含：
      - {dep.id}: {dep.DONE 摘要}
    如果 depends_on 为空，完全省略此块。}
    </predecessor_outputs>

    <plan_context>
    {规划者精炼后的计划摘要 — 省略完整任务列表}
    </plan_context>

    在响应末尾输出以下之一：
      DONE: <一行总结产出了什么>
      BLOCKED: <一句话 — 具体的阻塞原因，不要含糊>
```

跟踪 worker 状态：`pending | running | done | blocked | failed`。
依赖满足后，分发排队的任务。

---

## Phase 5：Worker 升级

当 worker 报告 `BLOCKED` 时：

**首先分类阻塞类型：**

| 阻塞类型 | 信号 | 操作 |
|---|---|---|
| **环境** | 缺少依赖、权限拒绝、命令未找到 | 自动修复（install、chmod 等）— 不计入升级次数 |
| **逻辑/设计** | 架构问题、需求模糊、约束冲突 | 升级到规划者 |
| **未知** | 其他情况 | 升级到规划者 |

对于环境类阻塞，尝试自动修复后重新分发同一任务。**每个任务最多 2 次自动修复尝试** — 如果环境问题在 2 次后仍然存在，作为逻辑/设计类阻塞升级（计入三振限制）。

对于逻辑/设计类阻塞，升级链路如下：

**第一振 — 规划者独立处理：**

1. 为阻塞构建紧凑交接：
   - `task`：被阻塞的任务标题
   - `situation`：计划上下文 + worker 尝试了什么
   - `blocked_on`：worker 的 BLOCKED 消息原文
   - `attempted`：worker 的部分输出（如有）
   - `files_in_play`：任务输入/输出

2. 生成规划者升级顾问：

   ```yaml
   Agent:
     description: "规划者升级顾问 — 任务 {task.id} 被阻塞（第 1 次）"
     model: "{PLANNER_MODEL}"
     prompt: |
       一个执行者在任务上被阻塞。提供一个可操作的指令来解除阻塞。
       不要提供分析、替代方案或推理 —
       输出一个执行者可以立即执行的具体指令。
       如果你对解决方案没有把握，在末尾加上：UNCERTAIN: <一句话说明原因>

       <handoff>
       task: {task.title}
       situation: {plan_context 摘要 — 最多 2 句话}
       blocked_on: {worker 的 BLOCKED 消息原文}
       attempted: {worker 的部分输出（如有）}
       files_in_play: {任务输入/输出}
       </handoff>

       输出格式（严格）：
       DIRECTIVE: <一句话 — 执行者 worker 下一步应该做什么>
   ```

3. 如果规划者输出 `UNCERTAIN`，立即进入**第二振 — 规划者 + 顾问**（不重新分发 worker）。
4. 否则提取 `DIRECTIVE` 并重新分发 worker。

**第二振 — 规划者 + 顾问（规划者不确定，或第一振后 worker 再次 BLOCKED）：**

1. 生成顾问深度求解：

   ```yaml
   Agent:
     description: "顾问深度求解 — 任务 {task.id} 被阻塞（第 2 次）"
     model: "{ADVISOR_MODEL}"
     prompt: |
       规划者无法解决一个 worker 阻塞。请提供深度专家指导。
       分析根本原因、风险，并给出最佳解决路径。

       <handoff>
       task: {task.title}
       situation: {plan_context 摘要 — 最多 2 句话}
       blocked_on: {worker 的 BLOCKED 消息原文}
       planner_uncertain: {规划者的 UNCERTAIN 信号（如有），否则填"规划者给出了指令但 worker 仍然阻塞"}
       files_in_play: {任务输入/输出}
       </handoff>

       按以下结构回复：
       1. **根本原因** — 为什么会阻塞
       2. **解决方案** — 最佳解决路径
       3. **指令** — 给执行者的一条具体操作指令
   ```

2. 规划者将顾问的「指令」提炼为单句 `DIRECTIVE`（绝不将顾问原始输出传递给执行者）。
3. 重新分发 worker，附加提炼后的指令。

**第三振 — 通知用户：**

如果 worker 在第二振后再次报告 `BLOCKED` → 直接通知用户。总共三振（第一振 → 第二振 → 第三振 = 通知用户）。

**当任务达到 `failed` 状态（三振用尽）时：**
1. 记录最终阻塞原因并将任务详情通知用户。
2. 将所有传递依赖于失败任务的任务标记为 `failed` — 它们无法继续。
3. 继续分发不依赖于失败任务的剩余任务。
4. 不等待用户输入 — 在所有剩余任务达到终态后继续进入 Phase 5.5/6 处理部分结果。

---

## Phase 5.5：集成检查

**如果少于 2 个任务达到 `done` 状态则跳过此阶段** — 单个完成的任务没有一致性可检查。

在收集结果之前，运行一个轻量规划者 pass 验证跨任务一致性：

```yaml
Agent:
  description: "规划者集成检查"
  model: "{PLANNER_MODEL}"
  prompt: |
    审查所有已完成 worker 任务的输出，检查跨任务一致性。
    检查：文件冲突、矛盾的修改、缺失的胶水代码、
    相互依赖任务之间的接口不匹配。

    <task_outputs>
    {对于每个已完成的任务：
      - {task.id}: {task.title} → {DONE 摘要}
      - 涉及的文件：{修改/创建的文件列表}
    }
    </task_outputs>

    回复以下之一：
      CONSISTENT: <一句话确认>
      CONFLICTS: <具体冲突的要点列表>
```

如果 `CONFLICTS`：对简单情况尝试自动解决（如合并排序）。对于非平凡冲突，在进入 Phase 6 之前将冲突列表通知用户。

---

## Phase 6：结果收集

当所有 worker 达到终态（`done` 或 `failed`）后：

1. 按任务顺序（T1, T2, ... Tn）汇总输出。
2. 向用户展示摘要：

```
## 级联完成

计划：{来自规划者的一行摘要}
任务：{N} 完成 | {M} 升级处理 | {K} 失败
集成：{CONSISTENT | "N 个冲突已解决" | "N 个冲突已通知用户" | "已跳过（<2 个完成任务）" | "已跳过（agent 失败）"}

### 结果
{按顺序的任务输出}

### 备注
{任何升级、降级、集成冲突或部分失败}

### 失败任务（如有）
{对于每个失败任务：任务 id、标题、最终 BLOCKED 消息、以及被跳过的下游任务列表}
```

---

## 预算与取消

**Token 预算：** 进入级联前估算成本：
- Phase 1（规划者规划）：~2-4k tokens
- Phase 2（顾问审查）：~1-3k tokens
- Phase 3（规划者精炼）：~2-4k tokens
- Phase 4（执行者 workers）：~1-2k tokens（配置/文档）到 ~4-8k tokens（代码生成）× N 个任务
- Phase 5（升级处理）：~1-2k tokens/次
- Phase 5.5（集成检查）：~1-2k tokens

如果估算总量超过 **50k tokens**，在继续之前警告用户。对于估算超过 **100k tokens** 的任务，需要用户明确确认。

**取消：** 在每个阶段边界（阶段之间，而非 agent 执行中途），检查用户是否发出了取消信号。如果是：
- 收集已完成阶段的部分结果
- 展示可用内容并注明：`> *级联在 Phase {N} 取消。以下为部分结果。*`
- 不再分发更多 agent

---

## 降级规则

- **规划者 agent 失败（Phase 1）** → 重新运行 Phase 1 一次。如果再次失败 → 用当前模型直接处理任务，警告用户。
- **规划者 agent 失败（Phase 3）** → 重试一次。如果再次失败 → 编排器使用 Phase 1 计划和可用的顾问反馈直接尝试任务拆分。注明：`> *Phase 3 agent 失败 — 编排器直接执行任务拆分。*`
- **顾问 agent 失败** → 跳过 Phase 2，使用规划者的 Phase 1 输出原样进入 Phase 3。注明：`> *顾问审查已跳过（{原因}）— 使用未审查的计划继续。*`
- **执行者 worker 失败（崩溃，非 BLOCKED）** → 重试一次。如果再次失败 → 规划者临时充当 worker 直接执行任务，注明：`> *执行者在任务 {id} 上崩溃 — 规划者作为临时 worker 执行。*` 在 Phase 6 摘要中报告。
- **规划者升级 agent 失败（Phase 5）** → 规划者直接作为临时 worker 处理被阻塞的任务，注明：`> *升级 agent 失败 — 规划者直接执行任务 {id}。*`
- **集成检查 agent 失败（Phase 5.5）** → 跳过集成检查，进入 Phase 6。注明：`> *集成检查已跳过（{原因}）— 结果可能存在跨任务不一致。*`

---

## 规则

- 先门控：判断者评估所有任务 — 简单任务永远不进入级联。
- 信心信号是强制的：如果规划者省略了它，视为 UNCERTAIN。
- 默认并行：同时分发所有独立任务。
- 仅原子任务：如果一个任务需要决策，它就不是原子的 — 精炼拆分。
- 每个任务最多三次升级：BLOCKED → 规划者（第一振）→ 重试 → 规划者不确定或再次 BLOCKED → 规划者+顾问（第二振）→ 重试 → 再次 BLOCKED → 通知用户（第三振）。
- 所有 agent（判断者、规划者、顾问、执行者）均可调用用户已安装的 skill（如 `/tdd`、`/code-review`）。**例外：禁止调用 `/smart-cascade` 自身** — 不允许递归级联。
- **判断者是入口。** 所有任务先经过判断者。简单任务由判断者直接处理；复杂任务移交规划者，判断者完全退出。
- **规划者规划，不执行。** 规划者的角色是规划、精炼和升级指导，不得直接执行分配给执行者 worker 的任务。显式例外（最后手段降级）：
  - 执行者 worker 在同一任务上崩溃两次 → 规划者作为临时 worker 执行，注明：`> *执行者在任务 {id} 上崩溃 — 规划者作为临时 worker 执行。*`
  - 升级 agent 失败 → 规划者直接执行被阻塞的任务，注明：`> *升级 agent 失败 — 规划者直接执行任务 {id}。*`
  - 执行者确认不可用（API 错误、模型宕机）→ 规划者作为最后手段执行，注明：`> *执行者不可用 — 规划者作为降级方案执行任务 {id}。*`
- **顾问顾问，不执行。** 顾问的角色仅限于审查和深度分析。在任何情况下都不得执行任务，包括执行者不可用时。如果执行者和规划者都不可用，直接将任务通知用户。
- **向下传指令，向上传摘要。** 信息在每个层级边界必须经过提炼后再传递：
  - **向下（→ 执行者）：** 仅传操作指令 — *做什么*和*验收标准*。不传权衡分析、替代方案、风险评估或顾问推理。执行者无法利用这些，且浪费 token。
  - **向上（→ 规划者/顾问）：** 紧凑摘要 — *发生了什么*和*什么失败了*。不传冗长日志或完整输出。
  - **永远不要将原始顾问输出传递给执行层。** 规划者必须将顾问的分析提炼为具体操作指令后才能传递给执行者。顾问的推理仅供规划者消费。
  - **给执行者的升级指导 = 一条指令。** 重新分发被阻塞的任务时，`escalation_guidance` 必须是单条可操作指令，而非完整的规划者分析。
