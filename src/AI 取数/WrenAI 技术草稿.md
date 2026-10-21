# WrenAI 技术草稿

> **受众**：有后端/数据工程背景的工程师，对 Text-to-SQL、语义层有基本了解，不熟悉 WrenAI 具体实现
> **预计时长**：40-45 分钟（含 Q&A 5 分钟）
> **配套材料**：`WrenAI_技术分享报告.html`（投影展示）+ `README.md`（参考）

---

## §01 问题背景：schema 不等于理解

> 投影：标题 + openEuler 示例代码块 + 四条业务映射/过滤口径/规范/治理

各位好，今天分享的是 WrenAI——一个 Agent 驱动的 GenBI 上下文引擎。

先从一个真实场景切入。假设你让 Agent 查"openEuler 社区 24.03 版本合并的 PR 有多少"。Agent 看到数据库 schema 里有 `pull_requests` 表、有 `branch` 列，很自然地写出 `WHERE branch='24.03'`。但这个查询大概率是错的——因为"24.03 版本"在实际仓库里对应的不是叫 `24.03` 的分支，而是 `OLK-6.6` 分支，加上一个 2024 年 3 月底到 9 月底的时间窗口。

类似的问题还有很多：`pr_comments` 表里大量 CI 机器人评论要不要排除？哪些仓库是官方源、哪些是 fork？"有效贡献"到底怎么定义？这些都是 schema 回答不了的问题。

**核心论断**：Agent 在业务数据上的瓶颈是上下文，不是智力。给它再强的模型，不告诉它这些业务含义，它还是会写错 SQL。WrenAI 要做的就是把这层缺失的上下文补上。

---

## §02 整体架构：四层 + 上下文原语

> 投影：四层架构图（从上到下：Agent 交互层 → 上下文层 → 规划引擎 → 执行层）

这一页是全局架构。WrenAI 分四层，从上到下依次是：

**第一层是 Agent 交互层**——这是架构的第一层，不是外挂的消费者。包含三样东西：Wren CLI 是主接口，所有能力通过命令暴露；Skills 是 6 个 Markdown 工作流，Agent 通过 `wren skills get` 按需获取；MCP Server 把 18 个工具、6 个资源、1 个 prompt 暴露给 Claude Code、Cursor 等 Agent。

**第二层是上下文层**——这是 WrenAI 的核心。三块内容：MDL 是语义定义（模型、视图、关系、Cube）；`knowledge/` 目录是业务知识资产（rules、sql、glossary、metrics、caveats 五个子目录）；Memory 是前两者的语义索引，底层用 LanceDB。

**第三层是规划引擎**——把"针对模型的 SQL"展开成"数据库能执行的 SQL"。四个组件协作：sqlglot 做解析和方言转译，CTE Rewriter 把展开结果注入为 WITH 子句，Policy 做双层安全校验，wren-core 是 Rust 写的语义引擎，基于 Apache DataFusion。

**第四层是执行层**——工厂模式，22+ 数据源连接器，统一返回 pyarrow 表。

> 切换到：六个上下文原语流程图

这里要特别讲一下"上下文原语"的概念。WrenAI 把正确性做成了一组可编排的步骤，而不是一个黑盒。六个原语：schema linking（用 `wren memory fetch` 取相关 schema）、value profiling（了解数据实际值）、ambiguity detection（判断问题是否需要澄清）、generation trace（用 `wren dry-plan` 看展开过程）、retry and repair（用 `wren dry-run` 校验）、eval（检测回归）。Agent 决定每步什么时候做，trace 全程可见。

> 切换到：五层上下文模型

最后补充一个区分：你们可能听到"五层上下文"和"四层架构"两个概念，别搞混。四层是系统的架构分层——谁调用谁；五层是上下文的内容分类——什么信息放哪。五层里的前三层（结构、语义、业务）由 MDL 承载，第四层（操作）由 knowledge/rules 承载，第五层（行为）由 Memory 承载。注意第④层和第⑤层标了"已实现"和"演进中"——知识规则和 Memory 检索已经是可用功能，但查询时治理和自主学习闭环还在演进。

---

## §03 Agent 交互层：CLI + Skills + MCP

> 投影：CLI 命令参考代码块

先看 CLI。这是工程师日常打交道的主接口。几组核心命令：

查询与校验：`wren query --sql` 通过 MDL 执行，`wren dry-plan` 展开模型 SQL 但不执行，`wren dry-run` 校验 SQL 可执行。

项目管理：`wren context init` 初始化项目，`wren context build` 编译 MDL，`wren context upgrade` 升级 schema_version。连接配置用 `wren profile` 管理。

记忆：`wren memory index` 建索引，`recall` 召回历史，`fetch` 取 schema，`store` 存确认的问答对，`watch` 自动重索引。

Agent 接入：`wren skills get` 获取工作流指引，`wren ask` 包装提示词，`wren serve mcp` 启动 MCP Server。

GenBI 看板：`wren genbi build/register/verify/deploy`，后面单独讲。

> 切换到：6 个 Skills 工作流表

再看 Skills。这是 WrenAI 区别于其他工具的一个设计——它不把工作流藏在产品里，而是写成 Markdown 工作流，Agent 通过 `wren skills get <name>` 按需获取。内容随 CLI wheel 版本对齐，没有版本漂移。

6 个 Skill 各覆盖一个阶段：`onboarding` 是上手入门；`generate-mdl` 从数据库 schema 生成 MDL YAML；`usage` 是日常查询的完整流程——召回、取上下文、写 SQL、执行、存回；`enrich-context` 补充 schema 承载不了的业务上下文；`dlt-connector` 把 SaaS API 数据导入 DuckDB 再生成项目；`genbi` 构建和部署看板。

**关键点**：Skills 不隐藏原语。它们帮 Agent 在正确顺序使用 dry-plan、fetch、recall 等原语，而不是替代原语。

> 切换到：MCP Server + Ask 模块

MCP Server 有 18 个工具分四组：查询组（执行 SQL、试运行、查 Cube、dry-plan）、上下文组（取 MDL、列模型、描述模型）、知识组（取规则、召回历史、取上下文）、写入组（存问答对，默认关）。两个治理开关：`--no-connect` 纯转译模式禁用查库，`--allow-write` 才允许写入。安全方面有路径穿越防护和 N+1 截断探针。

Ask 模块解决一个实际问题：同一个问题，给弱模型和强模型的提示词应该不一样。`--guided` 给弱模型包 6 步严格 SOP，`--direct` 给强模型极简包装。**不设默认**——因为静默改默认会跨版本改变 Agent 行为，宁可报错让你二选一。

SDK 方面有 wren-langchain 和 wren-pydantic 两个集成，都包装同一个 plan-and-execute pipeline，CLI 只是 Typer 外壳。

---

## §04 上下文层：MDL + knowledge/ + Memory

> 投影：项目结构代码块（schema_version: 5）

这一章是全场的重点。先看一个 Wren 项目的完整目录结构。`wren_project.yml` 是项目元数据，`schema_version: 5` 是当前版本。`models/` 放模型定义，`views/` 放命名 SQL 视图，`cubes/` 放聚合对象，`relationships.yml` 放关系定义。

关键是 `knowledge/` 目录——这是 schema_version 5 新增的，包含五个子目录：`rules/` 是业务规则、Agent 行为指引；`sql/` 是 NL→SQL 对，是 Memory 的事实源；`glossary/` 是术语表；`metrics/` 是指标定义；`caveats/` 是注意事项。

`.wren/memory/` 是 LanceDB 派生索引，gitignored，可以随时从 knowledge/ 重建。`target/mdl.json` 是编译产物，也是 gitignored。

> 切换到：三者关系表

**这三个概念的关系是全场最需要记住的**：

- **MDL** 回答"数据是什么意思"——定义模型、列、关系、计算字段。Memory 的 `schema_items` 集合会索引它。
- **knowledge/** 回答"数据应该怎么用"——定义规则、术语、指标、注意事项。Memory 的 `schema_items` 集合也会索引它。
- **knowledge/sql/** 回答"以前怎么做对过"——是 NL→SQL 对。Memory 的 `query_history` 集合语义召回这些对。
- **Memory** 回答"需要时怎么检索到"——是前三者的派生索引。

关键区分：MDL 和 knowledge/ 是 Git 里的可评审文件，可以 diff、可以 PR；Memory 是派生索引，丢了可以重建。这就是"事实源与派生索引分离"的设计。

| 层 | 具体做什么 | 主要聚焦场景 | 在你架构中的对应 |
|---|---|---|---|
| **Models** | 定义表、列、主键、关系、计算列 | 让 AI 知道“有哪些表、列怎么关联”，是所有查询的基础 | `om-dataarts` 产出的事实表/维度表 |
| **relationships** | 声明两个模型之间的 join 条件 | 让引擎自动解析跨表查询，避免 AI 手写 JOIN 时连错表或漏条件 | - |
| **Views** | 封装命名 SQL，可引用 model/view，查询时内联展开 | 把 `om-dataarts` 里的复杂清洗、多表关联、单位换算固化，AI 直接查视图 | `magicAPI` 中那些写得极其复杂的接口 SQL |
| **Cubes** | 在 base model/view 之上声明 measures、dimensions、time_dimensions、hierarchies | 高频、口径已达成共识的指标，AI 用结构化参数查询 | `datastat` 看板上已稳定展示的核心指标聚合 |
| **knowledge/metrics** | 用 Markdown 记录指标公式、维度、排除条件、时间粒度等 | **指标级的口径说明**，比 Cube 轻量，适合口径仍在演进或需要向 AI 解释“为什么这么算”的指标 | `datastat` 看板上指标的定义文档、`magicAPI` 中的计算逻辑说明 |
| **knowledge/rules** | 全局或匹配式业务规则 | 跨指标通用的约束（排除测试账号、默认日期字段） | `magicAPI` 中散落的全局过滤条件 |
| **knowledge/glossary** | 定义业务术语，映射到具体模型/列/过滤条件 | 用户说“活跃客户”时，AI 知道对应的过滤条件 | 统一各端对业务术语的理解 |
| **knowledge/caveats** | 记录数据坑（单位、时区、脏数据标记） | 防止 AI 在查询中踩到已知的坑 | `om-dataarts` 清洗过程中发现的数据质量问题 |
| **knowledge/sql** | 已验证的“问题-SQL 对” | 复杂、易错的查询，AI 优先召回标准答案 | `magicAPI` 中已验证无误的复杂 SQL |

> 切换到：Memory 五阶段 SVG 图

最后看 Memory 的五阶段生命周期。这个图比较大，我快速过一下：

**阶段 1 初始化**：发现项目、加载 profile 和 MDL、构建引擎和 MemoryStore。

**阶段 2 索引构建**：`extract_schema_items` 提取 MDL + rules，`embeddings.py` 向量化（支持 ONNX 和 Sentence Transformers），`load_query_pairs` 从 `knowledge/sql/` 加载历史问答，写入 LanceDB。

**阶段 3 查询流水线**：用户提问 → Memory fetch + recall → Agent 生成 SQL → CTE 重写 + wren-core 展开 → 连接器执行 → pyarrow 表。

**阶段 4 反馈闭环**：确认的问答存回 `knowledge/sql/*.md`，同步到 LanceDB 索引，供未来召回。

**监控同步**：`watch_loop` 用 SHA-256 指纹（path + size + mtime_ns）检测文件变化，自动触发 reindex。

一句话总结 Memory：markdown 是事实源，LanceDB 是派生索引，失败不丢数据。

---

## §05 规划引擎：SQL planner + wren-core

> 投影：规划管线流程图（① → ⑥）

这一章讲 SQL 怎么从"模型名"变成"数据库能执行的 SQL"。这个流程和 `engine.py` 的 `_plan()` 方法完全一致，源码行号我都标了。

**第①步**：用户写 SQL，用的是模型名，比如 `FROM pr_review_comments`。

**第②步**：sqlglot 解析 SQL，限定表名和列名，识别出哪些是 MDL 模型引用。

**第③步**：输入端 Policy 校验。两个检查：只读校验始终开启，拒 DELETE/DDL；严格模式可选，只允许引用 MDL 声明的表。**注意：这步在展开之前执行**——阻止不安全语句进入引擎。

**第④步**：这是核心。wren-core 的 `transform_sql` 把每个模型展开成真实表 + JOIN + 计算字段 + 安全过滤；CTE Rewriter 把展开结果包成 WITH 子句注入原查询；sqlglot 再转译成目标方言。

**第⑤步**：输出端 Policy 校验。为什么展开之后还要再查一次？因为模型可能用 `ref_sql` 模式（SQL 定义模型），视图也可能是原生 SQL，展开后可能引入了输入 SQL 里没有的变异语句。输出端复查只读性。

**第⑥步**：目标方言 SQL 交给连接器执行。

源码位置：`engine.py:203` 调 `validate_sql_policy`，`:247` 调 `CTERewriter.rewrite`（内部调 wren-core），`:250` 调 `validate_planned_sql`。两层 Policy 夹着展开步骤——这就是"双层校验"。

> 切换到：wren-core 代码示例（左右对比）

看这个具体例子。用户写 `SELECT pr_id, COUNT(*) AS comments FROM pr_review_comments GROUP BY pr_id`。`pr_review_comments` 不是真实表，是个模型。引擎展开后变成：先 `WITH pr_review_comments AS (SELECT pr_id FROM raw_pr_comments WHERE author NOT IN ('ci-bot','openeuler-ci-bot'))`，再在外面包聚合。

这里的设计要点：ci-bot 等门禁机器人的评论业务不需要，但 Agent 不会知道要排除谁。wren-core 在展开时自动注入名单——**业务规则定义一次，引擎每次查询都强制**。

wren-core 做三件事：模型展开（模型名→真表+JOIN+计算字段）、关系解析（按 MDL 声明的关系自动生成 JOIN）、安全强制（行级/列级访问控制自动注入过滤）。

> 从引擎内部看

[准备阶段]
  加载全量 MDL → extract（按查询裁剪出子 Manifest）→ 加载 WrenTypePlanner
        ↓
[Analyze 阶段] ModelAnalyzeRule
  作用域分析 → 将引用节点转为 ModelPlanNode，携带元数据，收集 RLAC 信息 → 移除引用节点的前缀信息
        ↓
[Generate 阶段] ModelGenerationRule
  模型展开（JOIN + 计算字段）→ RLAC Filter 注入 → 类型映射转换，使用 WrenTypePlanner 将方言SQL类型转为 DataFusion 的类型
  
**设计取舍**：第三步刻意没做某些优化（比如过滤下推），因为 unparser 处理不了——牺牲一点最优性，换不出错。

---

## §06 执行层：连接器

> 投影：连接器列表 + 接口定义 + 典型连接器表

执行层比较直接。22+ 数据源，工厂模式动态加载。所有连接器统一接口：`query(sql, limit)` 返回 pyarrow 表，`dry_run(sql)` 校验，`close()` 关连接。按需安装，比如 `pip install "wrenai[postgres,memory]"`。

三个典型实现：Postgres 用 psycopg3，手写了近 60 种 OID 到 Arrow 类型的映射；DuckDB 驱动原生支持 `fetch_arrow_table()`，还能读 S3/GCS；BigQuery 调 `.result().to_arrow()` 原生返回。

共用安全习惯：所有连接器在执行时把 SQL 包成 `SELECT * FROM (...) LIMIT n`，防"尾注释吞噬"和"多语句批"攻击。

---

## §07 GenBI 看板：从查询到部署

> 投影：wren genbi 命令流程

GenBI 是 WrenAI 的一个完整闭环：从查询到部署看板。流程是 `build` → Agent 编写应用 → `register` → `verify` → `open` 预览 → `deploy`。

`wren genbi build` 打印构建指令，包含 wasm 版本号、模型/列清单、验收标准。Agent 按指令编写 `apps/sales/`，包含 `mdl.json` 和 `data/*.parquet`。`verify` 做预检：文件完整性、MDL 可解析、数据快照、密钥扫描。`deploy` 部署到 Vercel 或 Cloudflare Pages。

底层是 wren-core-wasm，约 57MB raw、14MB gzip，在浏览器内做语义 SQL 展开。两种数据模式：`snapshot` 是快照 parquet，`live` 是实时查询。密钥从环境变量读取，不经 CLI 参数。

对应的 Skill 是 `wren skills get genbi`。

---

## §08 端到端示例：一次 Agent 驱动的查询

> 投影：六步 callout + 11 步蛇形管线图

把前面讲的所有模块串起来。用 openEuler 的例子走一遍。

用户问"24.03 版本合并的 PR 有多少"。

**① recall**：Memory 召回相似历史问答——如果以前查过类似问题，直接复用。
**② fetch**：Memory 取回 prs 模型定义和"24.03↔OLK-6.6 分支 + 时间窗口"的业务规则。
**③ Agent 写 SQL**：只能用模型名——`SELECT COUNT(*) FROM prs WHERE version='24.03'`。注意这里写的是 `version='24.03'`，是模型字段，不是底层列名。
**④ dry-plan**：展开为真实分支 + 时间窗口。
**⑤ 执行**：连接器 → pyarrow 表 → 自然语言答案。
**⑥ store**：确认的问答存回 `knowledge/sql/*.md` + LanceDB，下次相似问题自动复用。

下面的 11 步图和 §05 的规划管线顺序一致：⑥ 是输入端 Policy，⑦ 是 wren-core 展开 + CTE 注入，⑧ 是输出端 Policy。**注意 Policy 夹着展开步骤——不是展开之后才校验**。

最后一句话总结：Agent 写 `version='24.03'`（模型字段），引擎展开成 `branch='OLK-6.6'`（底层列名）。模型字段名不等于底层列名，这正是语义层的价值。

---

## §09 落地实践：3 命令上手

> 投影：3 命令 quickstart + 项目初始化流程

落地很简单，三步：

第一步，`pip install wrenai`。DuckDB 内置，零配置就能起步。

第二步，`npx skills add Canner/WrenAI`。这安装一个约 50 行的发现 stub，Agent 读了它就知道怎么从 CLI 拉取完整指引。

第三步，在项目目录里对 Agent 说"Use Wren to set up my Postgres database"。Agent 会检查环境、创建连接 profile、初始化项目、跑第一个查询。

如果要手动初始化：`wren context init` 生成 `wren_project.yml` + `models/` + `views/`；`wren profile add my-db --ui` 开浏览器表单配连接；`wren context build` 编译 MDL；`pip install "wrenai[postgres,memory]"` 按需装连接器；`wren --sql 'SELECT order_id FROM "orders" LIMIT 10'` 跑第一个查询。

没数据库的话可以用内置的 `jaffle_shop` 样本跑通全流程。

---

## §10 对比与局限

> 投影：对比表 + 局限列表

快速过一下对比。WrenAI 的差异化在"四合一"：语义层 + 执行引擎 + 记忆层 + Agent 接入，在一个开源项目里全有。传统 BI 手动建看板，业务定义锁在工具里；纯语义层（dbt/Cube）只定义不执行；裸 LLM 写 SQL 常错且无治理。

局限也要讲清楚：

第一，关联子查询（where条件子查询引用外层表的列）引擎暂不支持，。

第二，WASM 版无方言转译，只适合浏览器内本地数据。

第三，WASM 约 57MB raw、14MB gzip，是 DataFusion 全家桶的代价。

第四，Grep 兜底召回质量有限——没装 LanceDB 时用词法匹配。

第五，行级/列级安全的"用户组+审计"属商业版，引擎在 OSS 里，但多租户管理是付费功能。

---

## §11 设计模式与总结

> 投影：五个设计模式卡片 + 总结论断

最后，五个可以从 WrenAI 带走的设计模式，不只对 BI 有用：

**1. 双引擎分工**：Rust 管正确性（wren-core 做语义展开），Python 管广度（连接器、CTE、Policy）。各取所长。

**2. 正确性做成原语系统**：dry-plan、dry-run、双层校验都是可编排步骤，不是黑盒。Agent 决定什么时候做。

**3. 事实源与派生索引分离**：knowledge/ 是可评审的 Git 文件，LanceDB 是可重建的派生索引。失败不丢数据。

**4. MDL 即唯一查询面**：未建模的对象对 Agent 不可见。缩小攻击面，也缩小犯错面。

**5. 能力暴露做成可治理接口**：MCP 工具/资源/prompt + 开关门控 + 路径穿越防护。写工具默认关，纯转译模式禁用所有数据库访问。

> 切换到：总结页

总结：WrenAI 把散落的业务含义变成开放、可评审、可版本化的上下文层，让 Agent 在受治理的面上写正确的 SQL、生成看板。

**Agent 在业务数据上的瓶颈是上下文，不是智力。**

可深入的方向：wren-core 的 scope 管理细节、RLAC/CLAC 怎么处理子查询、Memory 嵌入模型选型、GenBI 的 WASM 客户端执行。

以上就是全部内容，谢谢大家。有什么问题？

---

## 时间分配参考

| 章节 | 预计时长 | 累计 |
|------|---------|------|
| §01 问题背景 | 3 min | 3 min |
| §02 整体架构 | 5 min | 8 min |
| §03 Agent 交互层 | 5 min | 13 min |
| §04 上下文层（含 Memory） | 8 min | 21 min |
| §05 规划引擎 | 6 min | 27 min |
| §06 执行层 | 2 min | 29 min |
| §07 GenBI 看板 | 2 min | 31 min |
| §08 端到端示例 | 4 min | 35 min |
| §09 落地实践 | 2 min | 37 min |
| §10 对比与局限 | 2 min | 39 min |
| §11 总结 | 1 min | 40 min |
| Q&A | 5 min | 45 min |

## 讲演提示

- **§04 是全场重点**，三者关系表（MDL / knowledge / Memory）建议停留足够时间，确保听众理解"事实源 vs 派生索引"的区分
- **§05 流程顺序**是技术核心，务必强调"输入端 Policy 在展开之前"——这是最容易讲错的点，源码行号（`:203` / `:247` / `:250`）是佐证
- **§08 端到端示例**用 openEuler 贯穿全场，§01 提出的问题在这里得到完整解答，形成闭环
- 如果时间紧张，§06 执行层和 §07 GenBI 可以各压缩到 1 分钟快速带过
- 如果听众对 Memory 特别感兴趣，§04 的 SVG 图可以作为讨论起点，五阶段生命周期值得展开讲
