# WrenAI 核心技术深度洞察报告

## 任务概述

本报告旨在深度剖析 WrenAI 项目的三大核心技术模块——**MDL 语义层、正确性原语集与混合检索记忆系统**——并结合本地 PostgreSQL 数据库给出详细的实现示例，为技术选型和内部方案设计提供决策依据。


## 一、MDL 语义层：将业务口径代码化

### 1.1 核心理念

MDL（Modeling Definition Language）是 WrenAI 的语义层契约，其核心思想是：**业务含义不应散落在提示词或代码注释中，而应作为可版本化、可审查的代码资产进行管理**。WrenAI 的定位是“可治理的语义层 + AI 上下文层”的组合。

### 1.2 项目结构

一个完整的 Wren 项目采用如下结构：

```
my_project/
├── wren_project.yml          # 项目清单（数据源、schema、绑定的 profile）
├── models/<name>/            # MDL — 每模型一个文件夹
│   ├── metadata.yml          # 列定义、主键、表引用
│   └── ref_sql.sql           # （可选）SQL 定义模型的查询体
├── views/<name>/             # MDL — 每视图一个文件夹
│   ├── metadata.yml          # 视图定义
│   └── sql.yml               # （可选）SQL 语句
├── relationships.yml         # MDL — 所有模型间关系
├── cubes/<name>/             # （可选）预聚合 Cube
│   └── metadata.yml          # base_object、measures、dimensions
├── knowledge/                # 知识库（纳入版本控制）
│   ├── rules/                # 业务规则（如“活跃客户”的筛选条件）
│   └── sql/                  # 已确认的 NL→SQL 对
├── target/
│   └── mdl.json              # 编译后的 MDL 清单（构建输出）
└── .wren/memory/             # LanceDB 本地向量索引（gitignore）
```

### 1.3 基于 PostgreSQL 的 MDL 定义示例

**场景**：电商订单分析系统，数据库包含 `orders`、`customers`、`products` 三张表。

**wren_project.yml**：
```yaml
schema_version: 5
name: ecommerce_analytics
version: "1.0"
catalog: wren
schema: public
data_source: postgres
profile: prod-pg
```

**models/orders/metadata.yml**：
```yaml
name: orders
table_reference:
  schema: public
  table: orders
columns:
  - name: order_id
    type: integer
    description: "订单唯一标识"
  - name: customer_id
    type: integer
    description: "关联到 customers 表"
  - name: total_amount
    type: double
    description: "订单总金额（已含税，不含退款）"
  - name: status
    type: varchar
    description: "订单状态：pending/shipped/completed/cancelled"
  - name: order_date
    type: timestamp
    description: "订单创建时间"
primary_key: [order_id]
```

**models/customers/metadata.yml**：
```yaml
name: customers
table_reference:
  schema: public
  table: customers
columns:
  - name: customer_id
    type: integer
  - name: first_name
    type: varchar
  - name: last_name
    type: varchar
  - name: email
    type: varchar
  - name: signup_date
    type: timestamp
primary_key: [customer_id]
```

**relationships.yml**（声明模型间关系，Agent 不再需要“猜测” JOIN 逻辑）：
```yaml
relationships:
  - name: orders_customers
    from_model: orders
    to_model: customers
    join_type: many_to_one
    from_column: customer_id
    to_column: customer_id
```

### 1.4 为什么 MDL 能有效防止 Agent 幻觉

| 问题类型 | 原始数据库的缺陷 | MDL 的解决方式 |
|----------|------------------|----------------|
| 列名歧义 | `id`, `created_at` 在多个表中含义不同 | 每列带 `description` 明确业务含义 |
| 表名混乱 | `customers`, `customers_v2`, `loyalty_customers` 并存 | 只暴露规范化的模型名称，不可见即不可用 |
| JOIN 路径不明确 | Agent 凭经验猜测关联方式 | `relationships.yml` 中声明一次，全局复用 |
| 指标口径不一致 | “收入”可能在不同团队有不同算法 | 通过 Cubes 预定义 `revenue` 的计算逻辑 |

MDL 的核心作用是**缩小 Agent 的“行动空间”**：Agent 只能使用 MDL 中声明的模型、列和关系，无法访问未声明的列或表。这意味着 Agent 在 SQL 中引用 `orders_v2.old_amount` 会直接失败，因为 `orders_v2` 在 MDL 中不存在。


## 二、正确性原语集：将校验暴露给 Agent 编排

### 2.1 核心理念

WrenAI 的设计哲学是：**正确性不是单一功能，而是一个由多个原语（Primitives）组成的系统，Agent 可以按需调用和编排**。这与“隐藏校验逻辑”的方案形成鲜明对比——WrenAI 把校验能力做成了一等 API。

### 2.2 六大正确性支柱

根据官方架构文档，WrenAI 将正确性拆解为六个相互协作的支柱：

| 支柱 | 含义 | 在 WrenAI 中的实现 |
|------|------|---------------------|
| **Schema linking** | 识别哪些模型、列、关系与当前问题相关 | MDL + `wren memory fetch` 混合检索 |
| **Value profiling** | 了解数据中实际出现的值（如 `status=4` 的含义） | 连接器行为 + knowledge/rules/ 索引 |
| **Ambiguity detection** | 识别问题是否信息不足，需要澄清 | Agent 通过 Skills 编排自主判断 |
| **Generation trace** | 展示答案的构建过程：模型、JOIN、CTEs、展开的 SQL | `wren dry-plan` 干跑计划 |
| **Retry and repair** | SQL 失败或指向错误对象时自动恢复 | 结构化错误 + `wren dry-run` + Agent 重试循环 |
| **Eval** | 检测 schema、定义或提示词变更导致的回归 | 金标准 NL-SQL 评测流程 |

### 2.3 核心原语命令

Wren CLI 提供了以下可直接由 Agent 调用的原语：

| 命令 | 作用 | 关键特性 |
|------|------|----------|
| `wren query --sql '...'` | 执行 SQL 并返回结果 | 通过 MDL 语义层规划后执行 |
| `wren dry-plan '...'` | 展示展开后的 SQL，**不执行** | 若列名错误或关系缺失，返回结构化错误和可用列列表 |
| `wren dry-run '...'` | 校验 SQL 语法，不返回数据行 | 发现错误时结构化返回修复提示 |
| `wren memory recall -q "..."` | 检索相似的历史查询对 | 语义检索（有 memory extra）或关键词匹配（无依赖） |
| `wren memory fetch -q "..."` | 检索相关的模型、列、业务规则 | 基于 MDL + knowledge/rules/ 的语义检索 |
| `wren memory store --nl "..." --sql "..."` | 存储确认后的查询对 | 写入 `knowledge/sql/*.md` 并更新索引 |

### 2.4 基于 PostgreSQL 的 Agent 编排示例

**场景**：Agent 收到用户提问“上个月新签客户的合同总额是多少？”

**Agent 的工作流**（由 Skills 引导，不可跳过步骤）：

```bash
# Step 1: 检索相似的历史查询
wren memory recall -q "新签客户合同总额" 
# → 返回 2 个相似的过去 NL→SQL 对

# Step 2: 检索相关的模型和列
wren memory fetch -q "新签客户 合同 总额"
# → 返回 orders 模型 + customer_id 列 + total_amount 列 + 
#    knowledge/rules/ 中“新签客户”的定义（如 signup_date > 上个月1日）

# Step 3: Agent 基于检索到的上下文编写 SQL（针对 MDL 对象）
# SELECT SUM(total_amount) FROM orders 
# WHERE customer_id IN (SELECT customer_id FROM customers WHERE signup_date >= '2026-08-01')
# AND status IN ('completed', 'shipped')

# Step 4: 干跑计划验证
wren dry-plan "SELECT SUM(total_amount) FROM orders ..."
# → 如果成功，显示展开后的可执行 SQL
# → 如果失败，返回结构化的错误信息和可用列列表

# Step 5: 干跑验证（可选，确认无语法错误）
wren dry-run "SELECT SUM(total_amount) FROM orders ..."

# Step 6: 执行查询
wren query --sql "SELECT SUM(total_amount) FROM orders ..."
# → 返回 PyArrow Table

# Step 7: 存储确认的查询对
wren memory store --nl "上个月新签客户的合同总额" --sql "SELECT SUM(total_amount)..."
# → 写入 knowledge/sql/ 目录，后续查询可复用
```

### 2.5 为什么“原语暴露给 Agent”比“黑盒校验”更优

传统方案将校验逻辑内置在系统中，Agent 只能“看到最终结果”。WrenAI 的方案允许 Agent：
1. **在写 SQL 之前就知道哪些模型/列可用**（`fetch` 原语）
2. **在真实执行之前就发现并修复错误**（`dry-plan`/`dry-run` 原语）
3. **从历史成功案例中学习**（`recall` 原语）
4. **将经验沉淀为可复用的资产**（`store` 原语）

每个原语的调用轨迹都保留在 Agent 的推理过程中，**可审查、可追溯**，没有“信任黑盒”。


## 三、混合检索记忆系统：让 Agent 越用越准

### 3.1 核心理念

WrenAI 的记忆系统是**检索层**，而非语义定义层。MDL 定义“数据是什么意思”，记忆系统帮助 Agent **找到和复用**已经证明有效的内容。

关键设计原则：**知识源（knowledge/）是事实来源，索引（.wren/memory/）是可重建的派生品**。`knowledge/` 下的 markdown 文件纳入 Git 版本控制，索引可以随时重建。

### 3.2 记忆系统存储的内容

| 内容类型 | 来源 | 为何重要 |
|----------|------|----------|
| **Schema items** — 模型、列、关系、视图、Cube、业务规则 | MDL + `knowledge/rules/` | Agent 只检索与问题相关的切片，而非把整张 schema 塞进提示词 |
| **NL→SQL 对** | `knowledge/sql/*.md` | 提供来自真实业务的少样本示例，而非通用的示例 |

### 3.3 两种检索后端

WrenAI 提供了两种检索后端，切换时 `knowledge/` 内容不变，只改变检索引擎：

| 维度 | **LanceDB 后端（需安装 memory extra）** | **Grep 后端（默认，无额外依赖）** |
|------|------------------------------------------|-----------------------------------|
| NL→SQL 召回方式 | **语义** — 基于 embedding 相似度，“按月的收入”能匹配“每月的销售额” | **关键词** — 基于 token 重叠和子串匹配，用词不同则无法匹配 |
| Schema 搜索（fetch） | ✅ 可用（embedding 检索 schema items） | ❌ 不可用（需要 embeddings） |
| 持久化索引 | LanceDB 存储于 `.wren/memory/`（`index`/`store` 构建） | 无 — markdown 本身即索引，`index` 命令为空操作 |
| 索引与源同步检查 | `wren memory check` 可检查 | 同左 |

```bash
# 安装 memory 后端
pip install "wrenai[memory,postgres]"

# 索引 schema + knowledge/
wren memory index

# 语义检索：获取与问题相关的模型、列、规则
wren memory fetch -q "客户生命周期价值"

# 语义召回：获取相似的历史查询
wren memory recall -q "上个月收入最高的客户"

# 存储确认的查询
wren memory store --nl "上个月收入最高的客户" --sql "SELECT ..."
```

### 3.4 基于 PostgreSQL 的记忆系统演进示例

**场景**：电商分析团队首次部署 WrenAI，从零开始构建记忆库。

**第1周**：没有历史查询，Agent 只能依赖 MDL + knowledge/rules/ 生成 SQL。用户验证后将正确的查询对通过 `wren memory store` 存入 `knowledge/sql/`。

```
# 用户提问："今年每个月的订单数"
# 验证后存入
wren memory store --nl "今年每个月的订单数" \
  --sql "SELECT DATE_TRUNC('month', order_date) AS month, COUNT(*) FROM orders WHERE order_date >= '2026-01-01' GROUP BY month ORDER BY month"
```

**第2周**：类似问题“今年每个月的订单金额”出现，`wren memory recall` 返回上周的查询，Agent 参考其 JOIN 和过滤模式，仅修改聚合列即可生成正确 SQL。

**第3周**：团队将“活跃客户”的定义写入 `knowledge/rules/active_customer.md`，执行 `wren memory index` 重建索引，后续查询自动感知该规则。

**第6个月**：记忆库包含数百条经过验证的 NL→SQL 对和业务规则。新 Agent 实例加载同一项目时，无需重新学习，直接 `wren memory index` 恢复所有记忆状态。

### 3.5 记忆系统与 MDL 的关系

官方文档强调了一个关键原则：**记忆不能替代 MDL。MDL 定义语义，记忆帮助 Agent 发现和复用语义**。

- MDL 定义 `total_amount` 是“含税订单总额”
- `knowledge/rules/` 定义“已完成订单”的筛选条件为 `status IN ('completed','shipped')`
- 记忆系统让 Agent 在回答“收入”问题时，**自动召回**之前成功的查询，复用上述定义
- 如果某个定义足够重要，应在 MDL 或 `knowledge/rules/` 中声明，然后重建索引

### 3.6 记忆系统的先进性与借鉴价值

WrenAI 记忆系统的先进性体现在三点：

1. **源-索引分离**：`knowledge/` 是可审查的源代码，`.wren/memory/` 是可重建的派生物。这确保了口径变更走 Git 评审，而非“偷偷改了数据库里某个向量”。

2. **渐进式学习**：每个成功查询都成为后续 Agent 的“养料”，“每个被接受的答案都可能让下一个答案更容易被校准”。

3. **混合检索策略**：无依赖的 grep 后端确保最低可用性，LanceDB 后端提供语义检索的高上限。两者使用相同的 `knowledge/` 源，切换成本极低。


## 四、总结：三大模块的协同关系

| 模块 | 角色 | 核心问题 |
|------|------|----------|
| **MDL 语义层** | “什么是对的” | 业务口径的定义和版本化契约 |
| **正确性原语集** | “怎么验证对错” | 将校验能力暴露给 Agent 自主编排 |
| **混合检索记忆** | “怎么复用对的” | 让历史正确的经验被检索和复用 |

三者协同形成“**定义 → 验证 → 沉淀 → 复用**”的闭环：MDL 声明口径，原语验证正确性，记忆沉淀经验，后续查询通过检索复用经验。WrenAI 之所以能实现“治理级”的 Text-to-SQL，根源在于这套闭环设计，而非依赖某一项“更聪明的算法”。
