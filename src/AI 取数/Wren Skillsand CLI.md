### 📋 第一部分：CLI 命令完整清单

#### 1. 项目与上下文管理
| 命令 | 说明 |
| :--- | :--- |
| `wren context import dbt` | 从 dbt 的 `manifest.json` 和 `catalog.json` 生成 Wren 项目。 |
| `wren context upgrade` | 将项目升级到最新的布局结构（如 v4→v5）。支持 `--dry-run` 预览。 |
| `wren context show` | 显示当前项目详情。 |
| `wren context validate` | 验证项目 YAML 文件结构。 |
| `wren context build` |编译项目生成 `target/mdl.json`。 |
| `wren profile import dbt` | 从 dbt 的 `profiles.yml` 中导入目标连接配置。 |

#### 2. 连接与配置
| 命令 | 说明 |
| :--- | :--- |
| `wren docs connection-info <datasource>` | 打印特定数据源（如 postgres, bigquery）所需的连接字段信息。 |

#### 3. 查询与执行
| 命令 | 说明 |
| :--- | :--- |
| `wren --sql '<query>'` | **默认命令**。执行 SQL 查询并返回结果。支持 `--output` (table/csv/json) 和 `--limit`。 |
| `wren query --sql '<query>'` | 与默认命令相同，执行 SQL 并返回结果。 |
| `wren dry-plan --sql '<query>'` | **转译 SQL**：将 MDL SQL 转换为数据源的原生 SQL 方言，无需连接数据库。支持 `-d` 指定数据源。 |
| `wren dry-run --sql '<query>'` | **预检查**：对数据库执行 SQL，但不返回数据行，仅输出 `OK` 或错误信息。 |

#### 4. 数据立方体 (Cube) 查询
| 命令 | 说明 |
| :--- | :--- |
| `wren cube list` | 列出 MDL 中定义的所有数据立方体。 |
| `wren cube describe <name>` | 查看指定立方体的详细结构（指标、维度、时间维度等）。 |
| `wren cube query` | 通过结构化参数查询立方体，自动生成分组和聚合 SQL。 |

#### 5. 语义记忆 (Memory)
> 基础功能依赖 `knowledge/sql/*.md`；高级语义索引需安装 `[memory]` 扩展。

| 命令 | 说明 |
| :--- | :--- |
| `wren memory index` | 构建语义索引（模式项 + `knowledge/sql/*.md` 中的 NL-SQL 对）。 |
| `wren memory watch` | 监视项目源文件变化，自动重新索引（需 `[memory]`）。 |
| `wren memory describe` | 将 MDL 模式以结构化纯文本形式打印（无需 LanceDB）。 |
| `wren memory fetch` | **获取模式上下文**：根据查询自动选择返回完整模式文本或语义搜索结果。 |
| `wren memory store` | 存储自然语言-SQL 对（写入 `knowledge/sql/<slug>.md`）。 |
| `wren memory recall` | 搜索已存储的 NL-SQL 对（支持语义或文本匹配）。 |
| `wren memory export` | 一次性迁移：将 LanceDB 中的查询历史导出到 `knowledge/sql/*.md`。 |
| `wren memory check` | 报告 `knowledge/sql/*.md` 与派生索引之间的差异。 |
| `wren memory status` | 显示索引统计信息（存储路径、表名、行数等）。 |
| `wren memory reset` | **删除** LanceDB 派生索引（源文件保留）。 |

#### 6. 技能与 AI 辅助 (Skills & Ask)
| 命令 | 说明 |
| :--- | :--- |
| `wren skills list` | 列出所有可用的 Agent 工作流指南。 |
| `wren skills get <name>` | 打印指定技能指南。支持 `--full`（包含参考文档）和 `--script`（获取捆绑脚本）。 |
| `wren ask "<question>" --guided` | 为较弱 LLM 生成包含严格任务流程的提示词。 |
| `wren ask "<question>" --direct` | 为较强 LLM 生成最小化包装的提示词。 |

#### 7. GenBI 仪表盘
| 命令 | 说明 |
| :--- | :--- |
| `wren genbi build <name>` | 为应用生成构建指令（不写入文件），支持 `--prompt` / `--data-mode`。 |
| `wren genbi register <name>` | 记录已创建的应用到项目索引 (`.wren/apps.yml`)。 |
| `wren genbi list` | 列出所有应用及其状态。 |
| `wren genbi remove <name>` | 从索引中移除应用条目（文件保留）。 |
| `wren genbi verify <name>` | 部署前预检查（文件完整性、MDL 解析、资产存在等）。 |
| `wren genbi open <name>` | 在本地预览应用（提供 URL）。 |
| `wren genbi deploy <name>` | 部署到 Vercel 或 Cloudflare Pages，返回可分享 URL。支持 `--prod`。 |

#### 8. MCP 服务器
| 命令 | 说明 |
| :--- | :--- |
| `wren serve mcp` | 以 MCP 模式启动服务器，供 Claude Desktop、Cursor 等客户端使用。支持 `--transport stdio/http`、`--allow-write`、`--no-connect` 等。 |

#### 9. 通用覆盖选项
许多命令支持以下通用参数，用于覆盖默认配置：
*   `--mdl <path>`：指定 MDL JSON 文件路径
*   `--connection-file <path>` 或 `--connection-info '<json>'`：指定连接配置
*   `--project <path>`：指定项目根目录
*   `--profile <name>`：指定连接配置名称

---

### 📚 第二部分：Skills 完整清单

| Skill 名称 | 核心定位 |
| :--- | :--- |
| **`onboarding`** | **全流程入门向导**。引导完成环境检查、安装依赖、创建数据源连接、初始化项目并执行第一次查询。 |
| **`generate-mdl`** | **数据库逆向建模**。探索数据库结构，基于元数据生成 MDL（建模定义语言）项目文件。 |
| **`enrich-context`** | **丰富业务语境**。将业务文档、数据字典、术语表等**非结构化知识**注入项目（如解释枚举值含义、单位等）。有“逐个确认”和“批量处理”两种模式。 |
| **`usage`** | **日常使用指南**。指导如何检索上下文、回忆相似历史查询、编写符合语义层定义的 SQL。 |
| **`genbi`** | **生成 BI 看板**。指导将查询结果构建成可交互、可分享的 BI 仪表盘。 |
| **`dlt-connector`** | **连接 SaaS 数据源**。指导如何使用 `dlt` 从 HubSpot、Stripe、Salesforce 等平台导入数据。 |

---

### 🔗 两者的关系
*   **Skills 是内置于 CLI 中的工作流指南**，AI 助手通过 `wren skills get` 命令来获取。
*   所有 **Skills 内容都随 CLI 版本发布**，确保指南与 CLI 功能版本完全匹配。
*   **典型使用路径**：`onboarding` → `generate-mdl` → `enrich-context`（可选）→ `usage` → `genbi`。
