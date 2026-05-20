---
name: smart-cascade
description: "分层模型编排，适用于中等到复杂任务。必须通过 /smart-cascade 显式调用 — 永不自动触发。判断者接收所有任务：简单任务直接处理，复杂任务移交规划者。规划者规划并经顾问审查，然后拆分为原子任务分发给并行执行者 worker。Worker 失败时通过规划者→顾问升级链处理。"
---

# Smart Cascade — 分层模型编排

根据复杂度在判断者 → 规划者 → 顾问 → 执行者 worker 之间路由任务。
使用专用 subagent，每个角色物理工具隔离。

## 调用方式

本 skill 必须**显式调用** — 永不自动触发。

```
/smart-cascade "构建用户认证的 REST API"
/smart-cascade "重构支付模块"
/smart-cascade --force-cascade "创建项目脚手架"
```

## Agents

Smart Cascade 使用四个专用 subagent。安装时与 skill 文件一起复制：

```bash
cp agents/*.md ~/.claude/agents/
# 或项目级：
cp agents/*.md .claude/agents/
```

| Agent | 文件 | 模型 | 工具 | 角色 |
|---|---|---|---|---|
| `smart-cascade-judge` | `agents/smart-cascade-judge.md` | sonnet | 全部 | 入口 — 复杂度门控 |
| `smart-cascade-planner` | `agents/smart-cascade-planner.md` | sonnet | Read, Grep, Glob, WebSearch, WebFetch | 仅规划 — 无文件写入 |
| `smart-cascade-advisor` | `agents/smart-cascade-advisor.md` | opus | Read, Grep, Glob, WebSearch, WebFetch | 仅顾问 — 无执行 |
| `smart-cascade-executor` | `agents/smart-cascade-executor.md` | haiku | 全部 | 原子任务执行 |

修改模型等级：编辑对应 agent 文件中的 `model:` 字段。

**标志（Flags）：**

| 标志 | 效果 |
|---|---|
| `--force-cascade` | 跳过简单路径 — 强制所有任务走完整 Phase 1-4 级联，无论判断者的复杂度评估结果。适用于安全敏感工作或执行 superpowers 计划。 |

**agent 启动失败时**（模型不可用、API 错误），立即停止并通知用户：

```
ERROR: smart-cascade-{role} agent 启动失败。
{haiku|sonnet|opus} 模型等级可能不可用。

修复方式：编辑 agent 文件并设置其他模型：
  ~/.claude/agents/smart-cascade-{role}.md  （全局）
  .claude/agents/smart-cascade-{role}.md    （项目）

或设置对应环境变量覆盖模型等级：
  ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME   — 用于 smart-cascade-executor
  ANTHROPIC_DEFAULT_SONNET_MODEL_NAME  — 用于 smart-cascade-judge、smart-cascade-planner
  ANTHROPIC_DEFAULT_OPUS_MODEL_NAME    — 用于 smart-cascade-advisor

不重试，不降级到其他 agent。级联已中止。
```

---

## Phase 0：复杂度门控

分发 `smart-cascade-judge`，传入任务和 `--force-cascade` 标志状态。

判断者评估复杂度并路由：

| 复杂度 | 信号 | 操作 |
|---|---|---|
| **简单** | 单次问答、单文件、少于 3 步、无需规划 | 判断者直接处理 — 跳过级联 |
| **中等** | 多文件、功能实现、调试、需要规划 | 判断者分发 `smart-cascade-planner` |
| **规划** | 架构设计、跨服务、需要任务拆分 | 判断者分发 `smart-cascade-planner` |

**`--force-cascade` 覆盖：** 设置后，判断者跳过简单路径 — 无论复杂度评估结果，均分发 `smart-cascade-planner`。

如果是简单任务（且未设置 `--force-cascade`）：判断者直接执行 — 不分发任何 subagent。
如果是中等/规划任务（或设置了 `--force-cascade`）：判断者分发 `smart-cascade-planner` 并退出。

---

## Phase 1：规划者规划

`smart-cascade-planner` 接收任务，产出计划和信心信号。

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "规划者规划与信心评估"
  prompt: |
    <task>
    {用户的任务}
    </task>

    <context>
    {紧凑交接 — task / situation / blocked_on / attempted / files_in_play}
    </context>

    在响应末尾输出以下之一：
      CONFIDENT: <一句话总结你的计划>
      UNCERTAIN: <一句话描述你不确定的地方>
```

分别捕获完整响应和信心信号。

**解析信心信号：** 从最后一行向上扫描。匹配第一个以 `CONFIDENT:` 或 `UNCERTAIN:` 开头的行。如果在最后 10 行内都未找到，视为 UNCERTAIN："规划者响应中缺少信心信号"。

---

## Phase 2：顾问咨询

根据规划者的信心信号分为两条路径。

### Path A — UNCERTAIN：顾问深度求解

```yaml
Agent:
  subagent_type: "smart-cascade-advisor"
  description: "顾问深度求解 — 规划者不确定"
  prompt: |
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

```yaml
Agent:
  subagent_type: "smart-cascade-advisor"
  description: "顾问轻量审查规划者计划"
  prompt: |
    <planner_plan>
    {规划者 Phase 1 的完整响应}
    </planner_plan>
```

---

## Phase 3：规划者精炼 + 计划拆分

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "规划者精炼与任务拆分"
  prompt: |
    <initial_plan>
    {Phase 1 计划}
    </initial_plan>

    {仅在顾问反馈存在时包含此块：}
    <advisor_feedback>
    {顾问 Phase 2 响应}
    </advisor_feedback>

    输出精炼后的计划，然后以以下格式结尾：

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
      }
    ]
    TASK_LIST_END
```

**基于 Phase 2 结果的精炼轮数：**
- Path B → SOLID（或 Phase 2 被跳过）：0 轮 — 仅任务拆分。
- Path B → NEEDS_REVISION：1 轮，解决顾问问题，然后拆分。
- Path A（深度求解）：始终 1 轮。
- 1 轮后仍有缺口：继续拆分并附带缺口说明 `> *精炼未完全收敛 — 已知缺口：{list}*`

**解析任务列表：** 提取 `TASK_LIST_START` / `TASK_LIST_END` 之间的文本，解析为 JSON。失败则宽松解析（去除尾部逗号、修复未加引号的键）。仍失败则要求规划者仅重新输出任务列表。

---

## Phase 4：执行者并行分发

根据依赖图按**波次**分发任务：

1. **Wave 0：** 所有 `depends_on` 为空的任务 — 并行分发。
2. 等待 Wave 0 完成。
3. **Wave N：** 所有 `depends_on` 已满足的任务 — 并行分发。
4. 重复直到所有任务分发完毕。

如果检测到循环依赖：立即通知用户 — 任务拆分有问题。

**并发限制：** 每波次最多 4 个 worker。多余的排队，有空位时分发。

```yaml
Agent:
  subagent_type: "smart-cascade-executor"
  description: "执行者 worker — {task.id}: {task.title}"
  prompt: |
    <task>
    id: {task.id}
    title: {task.title}
    description: {task.description}
    inputs: {task.inputs}
    outputs: {task.outputs}
    acceptance: {task.acceptance}
    </task>

    <predecessor_outputs>
    {对于 depends_on 中每个已完成的任务：
      - {dep.id}: {dep.DONE 摘要}
    如果 depends_on 为空，完全省略此块。}
    </predecessor_outputs>

    <plan_context>
    {规划者精炼后的计划摘要 — 省略完整任务列表}
    </plan_context>
```

跟踪 worker 状态：`pending | running | done | blocked | failed`。

---

## Phase 5：Worker 升级

当 worker 报告 `BLOCKED` 时：

**首先分类阻塞类型：**

| 阻塞类型 | 信号 | 操作 |
|---|---|---|
| **环境** | 缺少依赖、权限拒绝、命令未找到 | 自动修复（install、chmod 等）— 不计入升级次数 |
| **逻辑/设计** | 架构问题、需求模糊、约束冲突 | 升级到规划者 |
| **未知** | 其他情况 | 升级到规划者 |

环境类阻塞：自动修复后重新分发。**每个任务最多 2 次自动修复** — 仍失败则作为逻辑/设计类升级（计入三振限制）。

**第一振 — 规划者独立处理：**

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "规划者升级 — 任务 {task.id} 被阻塞（第 1 次）"
  prompt: |
    <handoff>
    task: {task.title}
    situation: {plan_context — 最多 2 句话}
    blocked_on: {worker 的 BLOCKED 消息原文}
    attempted: {worker 的部分输出（如有）}
    files_in_play: {任务输入/输出}
    </handoff>

    输出格式（严格）：
    DIRECTIVE: <一句话 — 执行者下一步应该做什么>

    如果不确定：UNCERTAIN: <一句话说明原因>
```

如果规划者输出 `UNCERTAIN` → 立即进入第二振（不重新分发 worker）。
否则提取 `DIRECTIVE` 并重新分发 worker。

**第二振 — 规划者 + 顾问：**

```yaml
Agent:
  subagent_type: "smart-cascade-advisor"
  description: "顾问深度求解 — 任务 {task.id} 被阻塞（第 2 次）"
  prompt: |
    <handoff>
    task: {task.title}
    situation: {plan_context — 最多 2 句话}
    blocked_on: {worker 的 BLOCKED 消息原文}
    planner_uncertain: {规划者的 UNCERTAIN 信号，或"规划者给出了指令但 worker 仍然阻塞"}
    files_in_play: {任务输入/输出}
    </handoff>
```

规划者将顾问的指令提炼为单句 `DIRECTIVE`（绝不将顾问原始输出传递给执行者）。重新分发 worker。

**第三振 — 通知用户。** 总共三振。

**当任务达到 `failed` 状态时：**
1. 记录最终阻塞原因并通知用户。
2. 将所有传递依赖于失败任务的任务标记为 `failed`。
3. 继续分发不依赖于失败任务的剩余任务。
4. 在所有剩余任务达到终态后继续进入 Phase 5.5/6。

---

## Phase 5.5：集成检查

**如果少于 2 个任务达到 `done` 状态则跳过。**

```yaml
Agent:
  subagent_type: "smart-cascade-planner"
  description: "规划者集成检查"
  prompt: |
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

如果 `CONFLICTS`：对简单情况尝试自动解决。非平凡冲突 → 在进入 Phase 6 之前通知用户。

---

## Phase 6：结果收集

```
## 级联完成

计划：{来自规划者的一行摘要}
任务：{N} 完成 | {M} 升级处理 | {K} 失败
集成：{CONSISTENT | "N 个冲突已解决" | "N 个冲突已通知用户" | "已跳过（<2 个完成任务）"}

### 结果
{按顺序的任务输出}

### 备注
{任何升级、集成冲突或部分失败}

### 失败任务（如有）
{任务 id、标题、最终 BLOCKED 消息、被跳过的下游任务列表}
```

---

## 预算与取消

**Token 预算估算：**
- Phase 1（规划者）：~2-4k tokens
- Phase 2（顾问）：~1-3k tokens
- Phase 3（规划者精炼）：~2-4k tokens
- Phase 4（执行者 workers）：~1-8k tokens × N 个任务
- Phase 5（升级处理）：~1-2k tokens/次
- Phase 5.5（集成检查）：~1-2k tokens

估算总量超过 **50k tokens** 时警告用户。超过 **100k tokens** 需要用户明确确认。

**取消：** 在每个阶段边界检查用户取消信号。如果取消：
- 收集已完成阶段的部分结果
- 注明：`> *级联在 Phase {N} 取消。以下为部分结果。*`
- 不再分发更多 agent

---

## 错误处理

**无静默降级。** 任何 agent 启动失败或崩溃，立即停止并通知用户（见上方错误消息模板）。

适用于所有角色：判断者、规划者、顾问、执行者、升级 agent、集成检查。

唯一例外：顾问返回 `NEED_MORE_CONTEXT` 时，附加上下文重新分发一次。仍不足则带缺口说明继续 Phase 3 — 这是内容问题，不是 agent 失败。

---

## 规则

- 先门控：判断者评估所有任务 — 简单任务永远不进入级联。
- 信心信号是强制的：如果规划者省略了它，视为 UNCERTAIN。
- 默认并行：同时分发所有独立任务。
- 仅原子任务：如果一个任务需要决策，它就不是原子的 — 精炼拆分。
- 每个任务最多三次升级：BLOCKED → 规划者（第一振）→ 重试 → 规划者不确定或再次 BLOCKED → 规划者+顾问（第二振）→ 重试 → 再次 BLOCKED → 通知用户（第三振）。
- 所有 agent 均可调用用户已安装的 skill（如 `/tdd`、`/code-review`）。**例外：禁止调用 `/smart-cascade` 自身** — 不允许递归级联。
- **判断者是入口。** 所有任务先经过判断者。
- **规划者规划，不执行。** 工具隔离由 agent 定义强制执行 — 规划者无 Write/Edit/Bash 权限。
- **顾问顾问，不执行。** 工具隔离由 agent 定义强制执行 — 顾问无 Write/Edit/Bash 权限。如果执行者和规划者都不可用，直接将任务通知用户。
- **向下传指令，向上传摘要。**
  - 向下（→ 执行者）：仅传操作指令 — 做什么和验收标准。不传权衡分析、顾问推理或替代方案。
  - 向上（→ 规划者/顾问）：紧凑摘要 — 发生了什么和什么失败了。
  - 永远不要将原始顾问输出传递给执行层。规划者必须提炼为单条指令后才能传递。
  - 给执行者的升级指导 = 一条指令，不是完整分析。
