# smart-cascade

[English](README.md) | **中文**

Claude Code 分层模型编排 skill。根据任务复杂度在可配置的顾问 → 规划者 → 执行者层级之间路由，支持并行 worker 分发和自动升级处理。

## 工作原理

```mermaid
flowchart TD
    USER([👤 用户输入]) --> JUDGE

    subgraph LAYER1["⚖️ 判断者层 — 入口"]
        JUDGE[判断者\n所有任务从这里进入]
        DETECT{任务复杂度\n检测}
        JUDGE --> DETECT
    end

    DETECT -- "简单 — 判断者\n直接处理" --> DONE([✅ 直接回复用户])
    DETECT -- "中等/规划\n移交规划者" --> PLANNER_START

    subgraph LAYER2["🔵 规划者层 — 规划与协调"]
        PLANNER_START[启动规划者 Subagent]
        PLANNER_TRY[规划者尝试解决]
        PLANNER_CHECK{是否有把握？}
        PLANNER_START --> PLANNER_TRY
        PLANNER_TRY --> PLANNER_CHECK
    end

    PLANNER_CHECK -- "UNCERTAIN — 求助顾问" --> ADVISOR_SOLVE
    PLANNER_CHECK -- "CONFIDENT — 轻量审查" --> ADVISOR_REVIEW

    subgraph LAYER3["🟣 顾问层 — 深度推理"]
        ADVISOR_SOLVE[顾问深度求解\n规划者遇到困难 — 顾问解锁]
        ADVISOR_REVIEW[顾问轻量审查\n规划者有把握 — 健全性检查]
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

    T1_CHECK -- "❌ BLOCKED" --> ESC1_P
    T2_CHECK -- "❌ BLOCKED" --> ESC2_P
    T3_CHECK -- "❌ BLOCKED" --> ESC3_P

    subgraph ESC_LAYER["🔵🟣 升级处理 — 规划者 → 顾问（如需）"]
        ESC1_P[第一振：规划者\n尝试给出指令]
        ESC1_U{规划者\n有把握？}
        ESC1_A[第二振：顾问\n深度求解]
        ESC1_P --> ESC1_U
        ESC1_U -- "UNCERTAIN 或\n仍然 BLOCKED" --> ESC1_A
        ESC1_A -- "规划者提炼\n指令" --> ESC1_U

        ESC2_P[第一振：规划者\n尝试给出指令]
        ESC2_U{规划者\n有把握？}
        ESC2_A[第二振：顾问\n深度求解]
        ESC2_P --> ESC2_U
        ESC2_U -- "UNCERTAIN 或\n仍然 BLOCKED" --> ESC2_A
        ESC2_A -- "规划者提炼\n指令" --> ESC2_U

        ESC3_P[第一振：规划者\n尝试给出指令]
        ESC3_U{规划者\n有把握？}
        ESC3_A[第二振：顾问\n深度求解]
        ESC3_P --> ESC3_U
        ESC3_U -- "UNCERTAIN 或\n仍然 BLOCKED" --> ESC3_A
        ESC3_A -- "规划者提炼\n指令" --> ESC3_U
    end

    ESC1_U -- "指令传回" --> T1
    ESC2_U -- "指令传回" --> T2
    ESC3_U -- "指令传回" --> T3

    COLLECT([📦 收集所有结果]) --> FINAL([✅ 最终输出])

    classDef judge fill:#2a1a1a,stroke:#f97316,color:#fed7aa
    classDef executor fill:#1a3a2a,stroke:#4ade80,color:#86efac
    classDef planner fill:#1a2a3a,stroke:#38bdf8,color:#7dd3fc
    classDef advisor fill:#2a1a3a,stroke:#a78bfa,color:#c4b5fd
    classDef terminal fill:#1e2130,stroke:#64748b,color:#94a3b8
    classDef merge fill:#2a2a1a,stroke:#fbbf24,color:#fde68a

    class JUDGE judge
    class T1,T2,T3 executor
    class PLANNER_START,PLANNER_TRY,PLANNER_REFINE,PLANNER_SPLIT,ESC1_P,ESC2_P,ESC3_P planner
    class ADVISOR_SOLVE,ADVISOR_REVIEW,ESC1_A,ESC2_A,ESC3_A advisor
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
/smart-cascade --judge=sonnet --advisor=opus --planner=sonnet --executor=haiku "你的任务"
```

### 方式二：配置文件（持久化）

编辑与 skill 文件同级目录下的 `smart-cascade.json`：

```json
{
  "judge": "sonnet",
  "advisor": "opus",
  "planner": "sonnet",
  "executor": "haiku"
}
```

| 角色 | 默认值 | 用途 |
|---|---|---|
| `judge` | `sonnet` | 入口 — 复杂度检测、简单任务执行、移交规划者 |
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
| `docs/model-routing-workflow.html` | 可交互路由工作流图 |
| `smart-cascade.json` | 模型配置文件 |

## 协议

MIT
