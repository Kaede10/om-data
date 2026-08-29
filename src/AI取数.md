# WrenAI 项目洞察报告

## 一、项目概述

WrenAI 是由 Canner 团队开发的开源 **生成式商业智能（GenBI）引擎**，在 GitHub 上已获得超过 13,000 颗星。它的核心定位是：让用户通过自然语言提问，系统自动生成准确的 SQL 查询、可视化图表甚至可部署的仪表板，将数据分析的门槛降到最低。

简单说，它就是“一个自带 AI 分析师的开源版 Metabase”。


## 二、模块架构与实现

### 2.1 三大核心服务

WrenAI 采用微服务架构，分为三个独立服务：

| 服务 | 技术栈 | 职责 |
|------|--------|------|
| **Wren UI** | Next.js 14 + Apollo GraphQL (TypeScript) | 用户交互界面：连接数据源、定义模型、提问、查看结果 |
| **Wren AI Service** | Python 3.12 + FastAPI | AI 核心：检索上下文、提示词构建、SQL 生成、结果校验 |
| **Wren AI Core** | Rust (WASM) + SQLGlot | 语义引擎：管理 MDL 元数据、SQL 计划与执行 |

代码仓库采用 **monorepo** 结构，`wren-ui/`、`wren-ai-service/` 和 `wren-launcher/` 三个目录分别对应上述服务。

### 2.2 数据流：从提问到结果

用户提问后，完整的处理流程如下：

```
用户提问 → Wren UI 接收
    ↓
Wren AI Service 检索相关业务上下文（从 Qdrant 向量库）
    ↓
Wren AI Service 基于上下文生成 SQL
    ↓
Wren AI Core 验证并执行 SQL（通过 SQL 规划器和数据库连接器）
    ↓
Wren UI 展示结果、图表和后续建议问题
```

### 2.3 关键技术组件

**① Wren CLI —— 代理与开发者的统一接口**

CLI 是 WrenAI 的“指挥中心”，提供以下命令：

- `wren query` — 执行 SQL 并返回结果
- `wren dry-plan` — 展示展开后的 SQL 但不执行（干跑校验）
- `wren dry-run` — 校验 SQL 语法但不返回数据行
- `wren memory` — 管理上下文索引、召回样例、存储已确认的查询

**② 项目上下文（Project Context）—— 业务口径的“源代码”**

WrenAI 最独特的设计在于：所有业务定义都作为 **可版本化的文件资产** 存储在项目目录中：

- `MDL 源文件` — 定义模型、列、关系、视图和指标
- `knowledge/rules/` — 业务规则
- `knowledge/sql/` — 已确认的自然语言→SQL 对
- `target/mdl.json` — 编译后的 MDL 清单
- `.wren/memory/` — LanceDB 本地向量索引（从 knowledge/ 构建）

这意味着 **口径变更走 Git 评审与回滚，而非散落在提示词里**。

**③ 正确性原语（Correctness Primitives）**

WrenAI 把校验做成一等 API，而非“隐藏特性”：

| 原语 | 作用 |
|------|------|
| Schema linking | 通过 MDL + 记忆检索，定位相关模型和列 |
| Value profiling | 了解数据中实际出现的值（如 status=4 的含义） |
| Dry-plan | 先展示展开 SQL，不真实执行 |
| Structured errors | 错误带修复提示结构化返回 |
| Eval runner | 持续回归测试，防止口径变更导致历史查询出错 |

### 2.4 Wren AI Service 内部架构（管道模式）

Python 服务采用 **pipeline-based** 架构：

- `src/pipelines/indexing/` — 将 MDL schema、表描述、历史 Q&A 对索引到 Qdrant 向量库
- `src/pipelines/retrieval/` — 从 Qdrant 语义检索相关上下文
- `src/pipelines/generation/` — SQL 生成、图表生成、意图分类
- `src/pipelines/ask/` — 编排 retrieval + generation 完成端到端取数

### 2.5 Wren UI 内部架构（Next.js + GraphQL）

前端采用 Next.js 14，在 API Routes 中嵌入 Apollo GraphQL 服务端：

```
src/apollo/server/
  ├── resolvers/      — GraphQL 解析器（ask、model、project 等）
  ├── services/       — 业务逻辑层（askingService、deployService 等）
  ├── repositories/   — 数据访问层（Knex + SQLite/PostgreSQL）
  └── adaptors/       — 外部服务适配器（AI Service、Engine）
```

前端 React 组件按页面组织：home、setup、modeling、knowledge。


## 三、独特先进性与设计哲学

### 3.1 核心理念：“正确性是一个体系”

WrenAI 的官方文档有一句关键表述：

> “Text-to-SQL 不会因为一个元数据字段或一句巧妙的提示词就变得可靠。它只有在多个组件协同工作时才变得可靠。”

这与大多数“套壳 ChatGPT + 数据库”的方案形成鲜明对比。WrenAI 的先进性不在于单一功能，而在于 **将校验、治理、记忆、执行拆解为可编排的原语，由 AI Agent 按需调用**。

### 3.2 区别于其他方案

| 对比维度 | 纯 LLM Agent | 传统 BI 工具 | 纯语义层 | **WrenAI** |
|----------|-------------|-------------|---------|------------|
| 能写 SQL | ✅（常出错）| ❌ | ❌ | ✅ 受治理的 |
| 理解业务定义 | ❌ | 部分（工具内）| ✅（仅 schema）| ✅ + 非 schema 知识 |
| 生成并部署仪表板 | ❌ | ✅（手动）| ❌ | ✅ Agent 驱动 |
| 通过 Agent 工作 | ✅ | ❌ | ❌ | ✅ |
| 开放、可审查、Git 友好的上下文 | ❌ | ❌ | 部分 | ✅ |

### 3.3 灵活性亮点

- **多数据源支持**：PostgreSQL、MySQL、BigQuery、Snowflake、ClickHouse 等 20+ 种
- **多 LLM 支持**：OpenAI、DeepSeek、Gemini、Claude、Ollama 本地模型等
- **部署灵活**：支持 Docker 一键部署、Kubernetes，也可使用云端托管服务
- **CLI + SDK + WASM**：可在浏览器中直接运行 Wren Engine（通过 WASM），处理 CSV/JSON/Parquet 数据


## 四、前端实现总结

### 4.1 技术选型

| 层面 | 技术 | 用途 |
|------|------|------|
| 框架 | Next.js 14 | 全栈应用（含 API Routes）|
| 语言 | TypeScript | 全栈类型安全 |
| GraphQL | Apollo Server + Client | API 层，统一前后端数据契约 |
| ORM | Knex | 数据访问层（SQLite/PostgreSQL）|
| 包管理 | Yarn 4.5.3 | monorepo 依赖管理 |

### 4.2 架构模式：**分层 GraphQL 后端**

Wren UI 的独特之处在于：**GraphQL 服务端直接嵌入 Next.js API Routes 中**，而非独立部署：

```
前端 React 组件 → GraphQL Client → Next.js API Routes → Apollo Server
    ↓
Apollo Server 通过 Adapter 层调用：
    - Wren AI Service (Python FastAPI)
    - Wren Engine (Rust WASM)
    - 数据库 Repository
```

这种模式的好处：
- **单进程部署**：无需独立 GraphQL 服务
- **清晰的关注点分离**：resolvers → services → repositories → adaptors
- **易于扩展**：新增业务功能只需在对应层添加代码

### 4.3 前端功能模块

- **页面组织**：按业务流程划分（setup 配置 → modeling 建模 → knowledge 知识 → home 取数）
- **交互体验**：自然语言输入框带提示、结果展示含 SQL 追溯、图表自动渲染
- **状态管理**：通过 Apollo Client 缓存管理服务端状态


## 五、关键洞察

1. **WrenAI 不是“AI 套壳”，而是一个可治理的数据分析基础设施**。它把业务口径定义从数据库 schema 和提示词中抽离出来，变成可版本化、可审查的“数据资产”。

2. **“正确性原语”设计值得借鉴**：把 dry-run、结构化错误、eval runner 作为一等 API 暴露给 AI Agent，而非内置黑盒逻辑，让 Agent 能够自主编排和执行校验。

3. **前端实现采用“嵌入式 GraphQL”架构**，既享受了 GraphQL 的类型安全和灵活性，又简化了部署复杂度，适合中小团队快速落地。

4. **项目已进入成熟期**：CLI + SDK + WASM 多种使用方式并存，既可完整部署，也可作为 SDK 嵌入现有系统。
