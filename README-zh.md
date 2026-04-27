# smart-cascade

[English](README.md) | **中文**

Claude Code 分层模型编排 skill。根据任务复杂度在可配置的顾问 → 规划者 → 执行者层级之间路由，支持并行 worker 分发和自动升级处理。

## 工作原理

```mermaid
flowchart TD
    USER([👤 用户输入]) --> EXECUTOR

    subgraph LAYER1["🟢 执行者层 — 默认对话"]
        EXECUTOR[执行者\n轻量对话 / 简单任务]
        DETECT{任务复杂度\n检测}
        EXECUTOR --> DETECT
    end

    DETECT -- "简单任务" --> DONE([✅ 直接回复用户])
    DETECT -- "中等/规划任务" --> PLANNER_START

    subgraph LAYER2["🔵 规划者层 — 规划与协调"]
        PLANNER_START[启动规划者 Subagent]
        PLANNER_TRY[规划者尝试解决]
        PLANNER_CHECK{是否有把握？}
        PLANNER_START --> PLANNER_TRY
        PLANNER_TRY --> PLANNER_CHECK
    end

    PLANNER_CHECK -- "UNCERTAIN" --> ADVISOR_SOLVE
    PLANNER_CHECK -- "CONFIDENT" --> ADVISOR_REVIEW

    subgraph LAYER3["🟣 顾问层 — 深度推理"]
        ADVISOR_SOLVE[启动顾问 Subagent\n深度求解]
        ADVISOR_REVIEW[启动顾问 Subagent\n轻量审查]
    end

    ADVISOR_SOLVE --> MERGE
    ADVISOR_REVIEW --> MERGE

    MERGE([顾问反馈汇聚]) --> PLANNER_REFINE

    subgraph LAYER2B["🔵 规划者精炼轮次"]
        PLANNER_REFINE[规划者根据顾问反馈\n精炼计划]
        PLANNER_SPLIT[规划者将计划\n拆分为原子任务列表]
        PLANNER_REFINE --> PLANNER_SPLIT
    end

    PLANNER_SPLIT --> DISPATCH

    DISPATCH([任务分发]) --> T1 & T2 & T3

    subgraph LAYER4["🟢 执行者并行层"]
        T1[执行者 Worker 1\n原子任务 A]
        T2[执行者 Worker 2\n原子任务 B]
        T3[执行者 Worker N\n原子任务 ...]

        T1_CHECK{执行成功？}
        T2_CHECK{执行成功？}
        T3_CHECK{执行成功？}

        T1 --> T1_CHECK
        T2 --> T2_CHECK
        T3 --> T3_CHECK
    end

    T1_CHECK -- "✅ DONE" --> COLLECT
    T2_CHECK -- "✅ DONE" --> COLLECT
    T3_CHECK -- "✅ DONE" --> COLLECT

    T1_CHECK -- "❌ BLOCKED" --> ESC1
    T2_CHECK -- "❌ BLOCKED" --> ESC2
    T3_CHECK -- "❌ BLOCKED" --> ESC3

    subgraph ESC_LAYER["🔵 规划者升级处理"]
        ESC1[规划者解决\nWorker 1 阻塞]
        ESC2[规划者解决\nWorker 2 阻塞]
        ESC3[规划者解决\nWorker N 阻塞]
    end

    ESC1 -- "指令传回" --> T1
    ESC2 -- "指令传回" --> T2
    ESC3 -- "指令传回" --> T3

    COLLECT([📦 收集所有结果]) --> FINAL([✅ 最终输出])

    classDef executor fill:#1a3a2a,stroke:#4ade80,color:#86efac
    classDef planner fill:#1a2a3a,stroke:#38bdf8,color:#7dd3fc
    classDef advisor fill:#2a1a3a,stroke:#a78bfa,color:#c4b5fd
    classDef terminal fill:#1e2130,stroke:#64748b,color:#94a3b8
    classDef merge fill:#2a2a1a,stroke:#fbbf24,color:#fde68a

    class EXECUTOR,T1,T2,T3 executor
    class PLANNER_START,PLANNER_TRY,PLANNER_REFINE,PLANNER_SPLIT,ESC1,ESC2,ESC3 planner
    class ADVISOR_SOLVE,ADVISOR_REVIEW advisor
    class DONE,FINAL terminal
    class MERGE,DISPATCH,COLLECT merge
```

## 安装

将 skill 文件复制到 Claude Code skills 目录：

```bash
# 全局安装
cp SKILL.md ~/.claude/skills/smart-cascade.md

# 或项目级安装
cp SKILL.md .claude/skills/smart-cascade.md
```

可选：将配置文件复制到同级目录：

```bash
cp smart-cascade.json ~/.claude/skills/smart-cascade.json
```

## 使用

```
/smart-cascade "构建用户认证的 REST API"
/smart-cascade "重构支付模块"
```

本 skill 必须**显式调用** — 永不自动触发。

## 配置

### 方式一：CLI 参数（单次调用）

```
/smart-cascade --advisor=opus --planner=sonnet --executor=haiku "你的任务"
```

### 方式二：配置文件（持久化）

编辑与 skill 文件同级目录下的 `smart-cascade.json`：

```json
{
  "advisor": "opus",
  "planner": "sonnet",
  "executor": "haiku"
}
```

| 角色 | 默认值 | 用途 |
|---|---|---|
| `advisor` | `opus` | 深度审查与风险分析（Phase 2） |
| `planner` | `sonnet` | 规划、精炼、升级指导 |
| `executor` | `haiku` | 原子任务执行（并行 worker） |

**优先级：** CLI 参数 > 配置文件 > 内置默认值

接受任何有效的 Claude 模型 ID（如 `claude-opus-4-5`、`claude-sonnet-4-5`、`claude-haiku-4-5`）。

## 阶段说明

| 阶段 | 内容 |
|---|---|
| 0 | 复杂度门控 — 简单任务直接跳过级联 |
| 1 | 规划者尝试任务并输出信心信号 |
| 2 | 顾问深度求解（UNCERTAIN）或轻量审查（CONFIDENT） |
| 3 | 规划者精炼计划并拆分为原子任务 |
| 4 | 执行者 worker 按波次并行运行（最多 4 个并发） |
| 5 | 被阻塞的 worker 升级到规划者获取单条指令 |
| 5.5 | 跨任务集成一致性检查 |
| 6 | 汇总结果并展示 |

## Skill 定义

完整的中文 skill 定义（含所有 Phase 细节、降级规则、规则约束）：

[docs/smart-cascade-zh.md](docs/smart-cascade-zh.md)

## 文件说明

| 文件 | 描述 |
|---|---|
| `SKILL.md` | 英文 skill 定义 |
| `docs/smart-cascade-zh.md` | 中文 skill 定义 |
| `smart-cascade.json` | 模型配置文件 |

## 协议

MIT
