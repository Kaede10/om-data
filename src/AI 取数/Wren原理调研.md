### 🧭 调研目标
- 数据从哪里来，如何建模
- 自然语言如何转成SQL
- AI如何检索上下文
- 整个系统如何集成与调用

---

### 👥 调研分工

| 角色 | 负责人 | 调研核心问题 | 主要探索的模块 |
| :--- | :--- | :--- | :--- |
| **链路与集成调研** | zhongjun | **“从零到查询”的完整链路是什么？**<br>CLI如何管理项目、配置、dbt集成？MCP如何让外部AI调用？ | `wren context *`<br>`wren profile *`<br>`wren context import dbt`<br>`wren serve mcp`<br>Skill: `onboarding` |
| **语义层与建模调研** | zhanyan | **数据库表如何变成Wren的语义模型？**<br>MDL是什么结构？业务规则如何注入和生效？ | `wren context build`<br>`wren memory describe`<br>`knowledge/rules/`<br>Skill: `generate-mdl`<br>Skill: `enrich-context` |
| **查询与AI交互调研** | maxueling | **用户问题如何变成SQL？**<br>`ask`的两种模式区别？Cube查询如何简化SQL？GenBI如何生成看板？ | `wren query`<br>`wren cube *`<br>`wren ask`<br>`wren genbi *`<br>Skill: `usage`<br>Skill: `genbi` |
| **记忆与检索调研** | wucaiping | **Memory到底怎么工作的？**<br>LanceDB索引构建原理？向量检索和文本检索的区别？阈值如何影响效果？ | `wren memory *`（含 `[memory]`扩展）<br>`knowledge/sql/*.md`<br>`wren dry-plan`<br>`wren dry-run` |

---

### 🔍 各角色具体调研清单（工作原理层面）

#### zhongjun：链路与集成调研
**核心问题**：Wren AI 的项目、配置和外部集成是如何组织的？
- **项目生命周期**：`wren context init` 创建了哪些文件？`wren context build` 读取什么、产出什么？`target/mdl.json` 在整个系统中扮演什么角色？
- **配置管理**：`wren profile add` 的三种方式（`--ui`, `--interactive`, `--from-file`）背后存储机制是什么？`wren context set-profile` 如何关联项目与配置？
- **外部集成**：`wren context import dbt` 要求 `manifest.json` 和 `catalog.json`，它如何映射dbt的模型到Wren的MDL？`wren serve mcp` 启动后，暴露了哪些tools/resources给Claude/Cursor？调用流程是什么？
- **输出成果**：绘制一张**“从 `wren context init` 到 `wren serve mcp`”的完整文件流转图**，标注每个命令读/写了哪些文件。

#### zhanyan：语义层与建模调研
**核心问题**：Wren 如何理解数据库结构？业务知识如何融合进去？
- **MDL生成原理**：`generate-mdl` Skill 指导AI做了什么？它使用了什么工具（SQLAlchemy?）探查数据库？`wren memory describe` 输出的纯文本结构对应MDL的哪些部分？
- **业务规则注入**：`knowledge/rules/` 下的 `.md` 文件如何被系统读取？`enrich-context` Skill 的“Grill”和“Auto-pilot”两种模式分别适合什么场景？规则文件（如 `revenue.md`）的格式和二级标题（`##`）如何影响检索？
- **模型验证**：`wren context validate` 检查了YAML的哪些方面？`wren context upgrade` 的版本演进逻辑（v4→v5创建`knowledge/`骨架）说明了什么设计思想？
- **输出成果**：编写一份 **“MDL 文件结构解析”** 和 **“业务规则编写最佳实践”**。

#### maxueling：查询与AI交互调研
**核心问题**：自然语言或结构化请求如何被翻译成最终SQL？
- **SQL执行路径**：`wren --sql` 和 `wren query` 有何异同？`wren dry-plan` 转译SQL的内部机制是什么（它是如何将MDL映射到目标数据源方言的）？
- **Cube查询简化**：`wren cube query` 如何从结构化参数（`--measures`, `--dimensions`, `--time-dimension`, `--filter`）生成带 `GROUP BY` 的复杂SQL？与手写SQL相比，它的优势在哪里？
- **AI提示工程**：`wren ask --guided` 和 `--direct` 生成的提示词模板分别包含哪些指令？`usage` Skill中推荐的“检索上下文 → 回忆历史 → 写SQL”SOP如何影响AI的行为？
- **看板生成**：`wren genbi build` 生成的“构建指令”是什么格式？`wren-core-wasm` 在其中扮演什么角色？`--data-mode snapshot/live` 分别对应什么数据加载策略？
- **输出成果**：创建一个 **“问题 → 提示词 → SQL”的转换示例集**，展示不同输入下CLI的输出差异。

#### wucaiping：记忆与检索调研
**核心问题**：Memory系统的数据和索引是如何构建与查询的？
- **数据来源**：`knowledge/sql/*.md` 中的NL-SQL对是如何被 `wren memory store` 写入的？文件命名规则和内部格式要求是什么？
- **索引构建**：安装 `[memory]` 扩展前后，`wren memory index` 的行为有何不同？LanceDB索引中存储了哪些信息（schema items + query_history）？`wren memory watch` 如何检测文件变化并触发重建？
- **检索策略**：`wren memory fetch` 的“混合策略”具体如何工作？**30,000字符阈值**是如何确定的？对于中文/日文等CJK语言，为什么阈值会“更保守”（更早切换到向量检索）？
- **检索对比**：`wren memory recall`（查NL-SQL对）和 `wren memory fetch`（查schema上下文）在检索机制（embedding vs grep）和用途上有何本质区别？
- **输出成果**：制作一个 **“Memory 数据流与检索决策图”**，清晰标注源文件、索引、查询类型和返回值之间的关系。


