# Wren AI Memory 模块 CLI 完整参考

> 本文档详细记录每个 CLI 命令的作用、正确/错误示例、关键决策点和其他注意事项。

---

## 目录

1. [架构概览](#架构概览)
2. [环境变量](#环境变量)
3. [命令详解](#命令详解)
   - [index — 索引构建](#1-index--索引构建)
   - [store — 存储 NL→SQL 对](#2-store--存储-nlsql-对)
   - [recall — 语义召回](#3-recall--语义召回)
   - [fetch — Schema 上下文检索](#4-fetch--schema-上下文检索)
   - [watch — 文件监控](#5-watch--文件监控)
   - [list — 列出查询历史](#6-list--列出查询历史)
   - [dump — 导出查询历史](#7-dump--导出查询历史)
   - [forget — 删除记录](#8-forget--删除记录)
   - [load — 批量导入](#9-load--批量导入)
   - [reset — 重置索引](#10-reset--重置索引)
   - [check — 同步检查](#11-check--同步检查)
   - [describe — Schema 描述](#12-describe--schema-描述)
   - [export — 导出到 Markdown](#13-export--导出到-markdown)
4. [子系统详解](#子系统详解)
   - [Schema 索引管线](#schema-索引管线)
   - [查询上下文策略](#查询上下文策略)
   - [Markdown 同步协议](#markdown-同步协议)
   - [Watch 监控循环](#watch-监控循环)
   - [Embeddings 后端](#embeddings-后端)

---

## 架构概览

```
knowledge/sql/*.md  ──── markdown 源文件（唯一真相源）
       │
       ├─→ GrepIndex (无额外依赖) ──── token/substring 搜索
       │
       └─→ LanceDBIndex (memory extra) ──── 语义搜索
              │
              ├─→ schema_items 表 (嵌入式 schema 片段)
              └─→ query_history 表 (嵌入式 NL→SQL 对)
```

**关键设计原则：**
- markdown 文件是唯一真相源（source of truth）
- LanceDB 索引是衍生数据（可重建）
- `--force` 跳过确认提示
- 所有命令支持 `--path/-p` 指定 LanceDB 路径

---

## 环境变量

| 变量 | 可选值 | 默认值 | 作用 |
|------|--------|--------|------|
| `WREN_MEMORY_BACKEND` | `grep`, `lancedb` | 自动检测 | 强制选择后端 |
| `WREN_EMBEDDING_BACKEND` | `onnx`, `sentence-transformers` | 自动检测 | 强制选择嵌入后端 |
| `WREN_EMBEDDING_MODEL` | 模型名称 | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformers 模型 |
| `WREN_ONNX_MODEL_FILE` | HF repo 中的路径 | `onnx/model.onnx` | ONNX 模型位置 |
| `WREN_HOME` | 目录 | `~/.wren` | 全局 wren 主目录 |

---

## 命令详解

### 1. `index` — 索引构建

**作用：** 完整重建内存索引，包括 schema 提取、向量化、种子查询生成和 markdown 同步。

**命令签名：**
```bash
wren memory index [--mdl/-m MDL_PATH] [--path/-p LANCEDB_PATH] \
                  [--instructions/--no-instructions] \
                  [--no-seed] [--no-queries]
```

**内部流程：**
1. 检测后端：如果是 `grep`，报告对数后退出（无需构建索引）
2. 加载 MDL manifest（`_load_manifest(mdl)`）
3. 如果 `--instructions` 且未指定 `--mdl`：加载项目规则并注入 manifest 为 `_instructions`
4. 构造 `MemoryStore(path=resolved_path)`
5. 调用 `mem_store.index_schema(manifest, seed_queries=not no_seed)`：
   - `extract_schema_items(manifest)` → 提取 schema 片段
   - `_embed_fn.compute_source_embeddings(texts)` → 向量化
   - **drop 并 recreate `schema_items` 表**（`replace=True`，全量替换）
   - 如果 `seed_queries=True`：生成种子对，删除旧种子，插入新种子
6. 如果 `--no-queries` 为 false：
   - `load_query_pairs(project_path)` → 加载 markdown 对
   - `mem_store.sync_markdown_queries(md_pairs)` → upsert + 删除过期
   - 加载遗留 `queries.yml`（标记 `source:legacy`）

**关键决策点：**
- **全量替换 vs 增量更新：** schema 索引每次都是全量重建（`replace=True`），不支持增量
- **种子查询替换：** `source:seed` 标签的行会被完全替换，用户对不受影响
- **遗留迁移：** `queries.yml` 中的对会被标记为 `source:legacy`，与 markdown 对区分

**正确示例：**
```bash
# 基本用法：从项目根目录
wren memory index

# 指定 MDL 路径
wren memory index --mdl ./my_project/target/mdl.json

# 只索引 schema，不生成种子和加载 markdown
wren memory index --no-seed --no-queries

# 自定义 LanceDB 路径
wren memory index --path /custom/lancedb/path

# 包含项目规则
wren memory index --instructions
```

**错误示例：**
```bash
# ❌ MDL 文件不存在
wren memory index --mdl /nonexistent/path.json
# 错误: MDL file not found: /nonexistent/path.json

# ❌ MDL 文件格式错误
wren memory index --mdl broken.json
# 错误: invalid JSON in broken.json: ...

# ❌ 在非项目目录执行（无 wren_context.yml）
cd /tmp && wren memory index
# 错误: no wren project found
```

**边界情况：**
- 空 manifest（无模型/关系）：`schema_items = 0`，`seeds = 0`
- `knowledge/sql/` 目录不存在：静默跳过，加载 0 对
- `queries.yml` 损坏：打印警告，命令继续执行

**性能：**
- 嵌入是瓶颈；ONNX 后端批大小 32
- 首次运行下载模型到 HF 缓存；后续使用本地缓存
- 大 schema：嵌入所有片段可能需要数秒

**与其他命令的关系：**
- 输出供 `wren memory recall` 使用（填充 `query_history`）
- `wren memory fetch` 使用此处构建的 `schema_items` 表

---

### 2. `store` — 存储 NL→SQL 对

**作用：** 存储单条自然语言→SQL 对到 markdown 文件和 LanceDB 索引。

**命令签名：**
```bash
wren memory store --nl "natural language" --sql "SELECT ..." \
                  [--datasource/-d DS] [--tags TAGS] [--path/-p PATH]
```

**内部流程：**
1. 发现项目路径
2. 写入 markdown 文件到 `knowledge/sql/<slug>.md`（通过 `write_query_markdown()`）
3. 尽力索引到 LanceDB（如果 memory extra 可用）：
   - 构造 `MemoryStore`
   - 调用 `store_query(nl, sql, datasource, tags)`
   - 嵌入 NL 查询，插入 `query_history` 表

**关键决策点：**
- **markdown 文件始终写入：** 不依赖 memory extra
- **LanceDB 索引是尽力而为：** `ModuleNotFoundError` 被捕获并忽略
- **slug 是确定性的：** 相同 NL → 相同文件名；冲突 → 数字后缀
- **Tags 是逗号分隔字符串：** 转换为列表存储

**正确示例：**
```bash
# 基本存储
wren memory store --nl "Total revenue" --sql "SELECT SUM(amount) FROM orders"

# 带数据源和标签
wren memory store --nl "Active users" \
                  --sql "SELECT * FROM users WHERE status='active'" \
                  --datasource postgres --tags "users,revenue"

# 带复杂 SQL
wren memory store --nl "Monthly revenue by region" \
                  --sql "SELECT DATE_TRUNC('month', created_at) as month, region, SUM(amount) FROM orders GROUP BY 1, 2"
```

**错误示例：**
```bash
# ❌ 空 NL
wren memory store --nl "" --sql "SELECT 1"
# 创建文件，slug 为空字符串回退到 "query.md"

# ❌ 无项目上下文
wren memory store --nl "test" --sql "SELECT 1"
# 错误: no wren project found

# ❌ 缺少 --nl 或 --sql
wren memory store --nl "test"
# 错误: Missing option '--sql'
```

**边界情况：**
- 相同 NL 存储两次：更新现有文件（按 slug 去重）
- NL 中的特殊字符：slugify 为小写字母数字 + 连字符
- SQL 中的单引号：通过 YAML frontmatter 转义

**性能：**
- 写入快速（文件 I/O + 可选单次嵌入）
- 非批量操作；一次一对

---

### 3. `recall` — 语义召回

**作用：** 语义搜索历史 NL→SQL 对，用于 few-shot 示例召回。

**命令签名：**
```bash
wren memory recall --query/-q "search query" [--limit/-l N] \
                   [--datasource/-d DS] [--path/-p PATH] \
                   [--output/-o json|table]
```

**内部流程：**
1. 发现项目路径
2. 通过 `get_index(project, path)` 获取索引：
   - LanceDB：`LanceDBIndex` → 通过 `store.recall_queries()` 语义搜索
   - Grep：`GrepIndex` → token 重叠 + 子串匹配
3. 通过 markdown 文件路径注解结果
4. 打印结果

**关键决策点：**
- **后端决定搜索策略：**
  - Grep：`_tokens()` 提取 2+ 字符的小写 token，按重叠数评分，整个查询子串匹配 +5 分
  - LanceDB：嵌入相似度搜索
- **`_annotate_markdown_paths()`：** 匹配 NL 到 markdown 文件用于显示

**正确示例：**
```bash
# 基本搜索
wren memory recall --query "revenue by region"

# 限制结果数，JSON 输出
wren memory recall --query "customer orders" --limit 10 --output json

# 按数据源过滤
wren memory recall --query "users" --datasource postgres

# 表格输出（默认）
wren memory recall --query "top products"
```

**错误示例：**
```bash
# ❌ 缺少 --query
wren memory recall
# 错误: Missing option '--query' / '-q'

# ❌ 无索引数据
wren memory recall --query "anything"
# "No results found."（如果 query_history 表为空）
```

**边界情况：**
- `query_history` 表不存在：返回空列表
- 空查询：Grep 后端对所有结果返回 0 分；LanceDB 返回嵌入最近的
- 无匹配对："No results found."

**性能：**
- LanceDB：快速 ANN 搜索（毫秒级）
- Grep：线性扫描所有对（<1000 对时很快）
- 嵌入查询是 LanceDB 的瓶颈

---

### 4. `fetch` — Schema 上下文检索

**作用：** 检索 schema 上下文，自动选择全文或语义搜索策略。

**命令签名：**
```bash
wren memory fetch --query/-q "search query" [--mdl/-m MDL_PATH] \
                  [--limit/-l N] [--type/-t model|column|relationship|view] \
                  [--model MODEL_NAME] [--threshold N] [--path/-p PATH] \
                  [--output/-o json|table]
```

**内部流程：**
1. 加载 MDL manifest
2. 构造 `MemoryStore`
3. 调用 `store.get_context(manifest, query, **kwargs)`：
   - 通过 `describe_schema(manifest)` 生成纯文本 schema 描述
   - **如果 `len(text) <= threshold`（默认 30000 字符）：** 返回全文（`strategy="full"`）
   - **否则：** 对 `schema_items` 表进行嵌入搜索（`strategy="search"`）
4. 搜索时：按 `mdl_hash`、`item_type`、`model_name` 过滤（如指定）
5. 打印策略和结果

**关键决策点：**
- **全文 vs 搜索策略：** schema 描述长度 vs 阈值（默认 30K 字符 ≈ 8K token）
  - 小 schema：完整结构（LLM 看到 model→column 关系）
  - 大 schema：语义搜索（LLM 获取相关片段）
- **`mdl_hash` 过滤：** 确保只搜索当前 schema 版本
- **阈值可调：** `--threshold 0` 强制搜索，`--threshold 999999` 强制全文

**正确示例：**
```bash
# 基本检索
wren memory fetch --query "customer revenue"

# 按类型过滤
wren memory fetch --query "orders" --type model --limit 3

# 按模型名过滤
wren memory fetch --query "amount" --type column --model orders

# 强制搜索策略（即使 schema 很小）
wren memory fetch --query "test" --threshold 5000

# JSON 输出
wren memory fetch --query "users" --output json
```

**错误示例：**
```bash
# ❌ 缺少 --query
wren memory fetch
# 错误: Missing option '--query' / '-q'

# ❌ 无效类型过滤（不会报错，只是不过滤）
wren memory fetch --query "test" --type invalid
# 仍然工作，只是不应用类型过滤
```

**边界情况：**
- Schema 未索引：搜索返回空结果（`strategy="search"` 但无表）
- `threshold=0`：始终使用搜索策略
- `threshold` 很高：始终返回全文

**性能：**
- 全文策略：瞬间完成（仅字符串生成）
- 搜索策略：需要嵌入查询 + ANN 搜索

---

### 5. `watch` — 文件监控

**作用：** 监控 MDL 和 markdown 文件变化，自动触发重索引。

**命令签名：**
```bash
wren memory watch [--mdl/-m MDL_PATH] [--path/-p PATH] \
                  [--interval/-i SECONDS] \
                  [--reindex-on-start/--no-reindex-on-start] \
                  [--max-polls N]
```

**内部流程：**
1. 如果是 grep 后端：拒绝（无衍生索引可监控）
2. 发现项目路径
3. 验证 `--mdl` 在项目根目录内（跨项目保护）
4. 定义 `_reindex()` 回调：
   - 加载 manifest，构造 store，`index_schema()`，`sync_markdown_queries()`
5. 定义 `_on_event()` 用于日志
6. 进入 `watch_loop()`：
   - 计算初始指纹（`target/mdl.json` + `knowledge/sql/*.md` 的内容哈希）
   - 轮询间隔：重新计算指纹，与基线比较
   - 变化时：调用 `_reindex()`，更新基线
   - 重索引错误时：递增错误计数，保持变化待定以重试
   - KeyboardInterrupt：干净退出

**关键决策点：**
- **指纹 = SHA-256：** 每个监控文件的 `(path + size + mtime_ns)`
- **无文件内容读取：** 仅 stat 调用检测变化（廉价）
- **失败重索引保持变化待定：** 下次轮询时重试
- **`--reindex-on-start`：** 设置基线为空字符串，强制立即重索引
- **最小间隔 1.0 秒：** `MIN_INTERVAL_SECONDS` 强制

**正确示例：**
```bash
# 基本监控
wren memory watch

# 自定义轮询间隔，启动时重索引
wren memory watch --interval 2.0 --reindex-on-start

# 限制轮询次数（用于脚本/测试）
wren memory watch --max-polls 10

# 指定 MDL 路径
wren memory watch --mdl /path/to/mdl.json
```

**错误示例：**
```bash
# ❌ 跨项目 MDL
wren memory watch --mdl /other/project/target/mdl.json
# 错误: --mdl is outside the watched project root

# ❌ Grep 后端
WREN_MEMORY_BACKEND=grep wren memory watch
# 错误: grep backend: knowledge/sql/ IS the index — nothing to watch
```

**边界情况：**
- `target/mdl.json` 启动时不存在：下次轮询创建后拾取
- `knowledge/sql/` 目录被删除：空文件列表，不触发重索引
- `interval < 1.0s`：钳制到 1.0s
- 轮询期间并发文件写入：stat 竞态优雅处理

**性能：**
- 每次轮询：O(监控文件数) 次 stat 调用 + SHA-256
- 重索引：与 `wren memory index` 相同（嵌入瓶颈）
- 轮询间无 CPU 使用（sleep）

---

### 6. `list` — 列出查询历史

**作用：** 列出 `query_history` 表中的 NL→SQL 对。

**命令签名：**
```bash
wren memory list [--source/-s seed|user|view] [--limit/-n N] \
                 [--offset N] [--output/-o json|table] [--path/-p PATH]
```

**内部流程：**
1. 构造 `MemoryStore`
2. 调用 `list_queries(source, limit, offset)`：
   - 加载完整 `query_history` 表到 pandas
   - 重置索引为 0-based 位置索引
   - 如果指定：按 `_tag_source(tags) == source` 过滤
   - 按 `created_at` 降序排序
   - 切片 `[offset:offset+limit]`
   - 附加 `_row_id`（未过滤表中的原始位置索引）
3. 打印结果和分页信息

**关键决策点：**
- **`_tag_source()`：** 从 tags 字符串提取 `source:XXX` token
- **`_row_id`：** 未过滤表中的位置索引（用于 `forget` 命令）
- **分页显示：** `Showing X-Y of Z pairs.`

**正确示例：**
```bash
# 列出所有
wren memory list

# 按来源过滤
wren memory list --source seed --limit 5

# 分页
wren memory list --offset 10 --output json

# 表格输出（默认）
wren memory list --source user
```

**错误示例：**
```bash
# ❌ 无效来源（不报错，返回空）
wren memory list --source invalid
# 返回空列表（无行匹配）
```

**边界情况：**
- `query_history` 表不存在："No pairs found."
- 过滤后为空："No pairs found."
- offset 超过总数：空结果

---

### 7. `dump` — 导出查询历史

**作用：** 将 `query_history` 表导出为 YAML 文件。

**命令签名：**
```bash
wren memory dump [--source/-s seed|user|view] \
                 [--output/-o FILE|-] [--path/-p PATH]
```

**内部流程：**
1. 构造 `MemoryStore`
2. 调用 `dump_queries(source)`：
   - 加载完整表，按 source 过滤，按 `created_at` 升序排序
   - 返回除 `vector` 外的所有列
3. 通过 `_pairs_to_yaml()` 转换为 YAML：
   - 格式：`{version: 1, exported_at: ISO, pairs: [{nl, sql, source, datasource?, created_at?}]}`
4. 输出目标：
   - `--output -`：stdout
   - `--output FILE`：写入文件
   - 默认：`<project>/queries.yml`（如果在项目中），否则 stdout

**关键决策点：**
- **`_parse_source()` vs `_tag_source()`：** 显示默认未标记行为 "user"，过滤 `--source user` 跳过未标记行
- **这是有意设计：** 显示显示 "user"，但过滤逻辑使用不同的函数

**正确示例：**
```bash
# 导出到默认位置
wren memory dump

# 导出用户对到文件
wren memory dump --source user --output backup.yml

# 导出到 stdout
wren memory dump --output - | head -50

# 导出所有对
wren memory dump --output all_pairs.yml
```

**错误示例：**
```bash
# ❌ 无数据时导出
wren memory dump
# "No pairs to dump." 并退出
```

---

### 8. `forget` — 删除记录

**作用：** 从 `query_history` 表中删除 NL→SQL 对。

**命令签名：**
```bash
wren memory forget [--id ID ...] [--source/-s seed|user|view] \
                    [--force/-f] [--limit/-n N] [--path/-p PATH]
```

**三种模式：**

**模式 1：非交互式 + `--id`**
1. 验证：`--id` 和 `--source` 不能共存
2. 如果非 `--force`：确认提示
3. 调用 `forget_queries_by_ids(ids)`：
   - 加载表，删除给定位置索引的行
   - 如果所有行被删除：删除整个表
   - 否则：用剩余行重建表

**模式 2：批量 + `--source` + `--force`**
1. 通过 `count_queries_by_source(source)` 计算匹配行
2. 如果为 0："Nothing to forget."
3. 调用 `forget_queries_by_source(source)`：
   - 找到所有 `_tag_source(tags) == source` 的行
   - 通过 `forget_queries_by_ids()` 删除

**模式 3：交互式（默认）**
1. 尝试导入 `InquirerPy`；如果缺失：错误并提示安装
2. 通过 `list_queries(source, limit)` 加载行
3. 呈现 checkbox UI，带格式化标签
4. 选择后：确认，然后 `forget_queries_by_ids()`

**关键决策点：**
- **位置索引 vs 绝对 ID：** `_row_id` 是未过滤表中的位置索引，每次列表操作可能变化
- **表重建：** 删除后用 `mode="overwrite"` 重建表
- **`--id` 和 `--source` 互斥：** 不能同时使用

**正确示例：**
```bash
# 按 ID 删除
wren memory forget --id 0 --id 3 --id 5

# 按来源批量删除
wren memory forget --source seed --force

# 交互式删除
wren memory forget

# 限制交互式显示数量
wren memory forget --limit 20
```

**错误示例：**
```bash
# ❌ 同时使用 --id 和 --source
wren memory forget --id 1 --source seed
# 错误: --id and --source cannot be used together

# ❌ ID 超出范围
wren memory forget --id 99999
# "Forgot 0 pair(s)."（静默忽略）
```

**边界情况：**
- ID 超出范围：静默跳过
- 所有行被删除：删除整个表
- InquirerPy 未安装：错误消息带安装命令
- 无行匹配 source 过滤："Nothing to forget."

---

### 9. `load` — 批量导入

**作用：** 从 YAML 文件批量导入 NL→SQL 对。

**命令签名：**
```bash
wren memory load FILE [--upsert] [--overwrite] [--dry-run] [--path/-p PATH]
```

**内部流程：**
1. 验证标志：`--upsert` 和 `--overwrite` 不能共存
2. 读取并解析 YAML 文件
3. 验证结构：必须有 `pairs` 键，版本 1，每对有 `nl` 和 `sql`
4. 计算来源，打印摘要
5. 如果 `--dry-run`：摘要后退出
6. 调用 `mem_store.load_queries(pairs, overwrite, upsert)`：
   - **overwrite：** 删除相同来源的所有对，然后写入所有
   - **upsert：** 按 nl_query 去重输入（后者胜出），删除现有匹配 nl_query，插入所有
   - **默认（skip）：** 对每对，如果精确（nl, sql）匹配则跳过

**关键决策点：**
- **overwrite 模式：** 先按 source 标签删除，再写入
- **upsert 模式：** 按 nl_query 去重（不是 sql），最后出现的胜出
- **默认模式：** 精确（nl, sql）匹配用于去重

**正确示例：**
```bash
# 基本导入
wren memory load queries.yml

# Upsert 模式（更新现有，插入新的）
wren memory load backup.yml --upsert

# Overwrite 模式（替换所有）
wren memory load export.yml --overwrite

# 预览模式
wren memory load export.yml --dry-run
```

**错误示例：**
```bash
# ❌ 文件不存在
wren memory load nonexistent.yml
# 错误: file not found: nonexistent.yml

# ❌ 无效 YAML
wren memory load broken.yml
# 错误: unable to read YAML from broken.yml: ...

# ❌ 同时使用 --upsert 和 --overwrite
wren memory load data.yml --upsert --overwrite
# 错误: --upsert and --overwrite are mutually exclusive
```

**边界情况：**
- 空 pairs 列表："No pairs to load."
- pair 缺少 `nl` 或 `sql`：验证错误，退出
- pair 有非字符串字段：验证错误，退出

---

### 10. `reset` — 重置索引

**作用：** 删除所有 LanceDB 索引表（schema_items 和 query_history）。

**命令签名：**
```bash
wren memory reset [--path/-p PATH] [--force/-f]
```

**内部流程：**
1. 获取索引
2. 如果 grep 后端："grep backend has no derived index" 并退出
3. 如果非 `--force`：确认提示
4. 调用 `idx.reset()` → `store.reset()`：
   - 删除 `schema_items` 表（如果存在）
   - 删除 `query_history` 表（如果存在）

**关键决策点：**
- **只有 LanceDB 有衍生表可删除**
- **`knowledge/sql/*.md` 永远不被触碰**（真相源）
- **`--force` 跳过确认**

**正确示例：**
```bash
# 强制重置
wren memory reset --force

# 交互式确认
wren memory reset
# Are you sure you want to reset the memory index? [y/N]: y
```

**错误示例：**
```bash
# ❌ Grep 后端
wren memory reset
# "grep backend has no derived index" 并退出
```

**边界情况：**
- 表不存在：`drop_table` 是空操作
- 重置后需要重新运行 `wren memory index`

---

### 11. `check` — 同步检查

**作用：** 检查 markdown 文件和 LanceDB 索引之间的同步状态。

**命令签名：**
```bash
wren memory check [--path/-p PATH]
```

**内部流程：**
1. 发现项目路径，获取索引
2. 如果 grep 后端：报告对数，"always in sync"
3. 加载 markdown NLS：`{p["nl"] for p in load_query_pairs(project)}`
4. 加载已索引 NLS：`{r["nl_query"] for r in mem_store.list_queries(limit=1M)}`
5. 加载已索引的 markdown 支持 NLS：按 `_has_tag(tags, _MARKDOWN_SYNC_TAG)` 过滤
6. 计算：
   - `missing = md_nls - indexed_md`（在 markdown 中但未索引为同步）
   - `stale = indexed_md - md_nls`（已同步但不再在 markdown 中）
7. 报告同步状态

**关键决策点：**
- **使用 `_MARKDOWN_SYNC_TAG`：** 识别由 `sync_markdown_queries` 写入的行
- **不使用 `source` 标签：** 会错误分类 `wren memory load` 的对
- **`missing` 表示需要运行 `wren memory index`**
- **`stale` 表示 markdown 已删除但索引未更新**

**正确示例：**
```bash
wren memory check
# knowledge/sql: 5 pair(s); index: 5 pair(s)
# In sync.

wren memory check
# knowledge/sql: 3 pair(s); index: 5 pair(s)
#   2 indexed pair(s) without markdown, stale index, run `wren memory index`.
```

**边界情况：**
- 无 markdown 文件：`missing = 0`，可能有 `stale`
- 索引为空：`stale = 0`，可能有 `missing`
- 两者都为空："In sync."

---

### 12. `describe` — Schema 描述

**作用：** 生成人类可读的 schema 描述文本（无索引、无嵌入）。

**命令签名：**
```bash
wren memory describe [--mdl/-m MDL_PATH]
```

**内部流程：**
1. 加载 MDL manifest
2. 调用 `describe_schema(manifest)`：
   - 生成结构化纯文本：Catalog/Schema 头部，模型及列、关系、视图、立方体
3. 打印文本

**关键决策点：**
- **无嵌入或索引：** 纯文本生成
- **用于调试和理解将被索引的内容**

**正确示例：**
```bash
wren memory describe
wren memory describe --mdl ./target/mdl.json
```

---

### 13. `export` — 导出到 Markdown

**作用：** 将 LanceDB 中的 NL→SQL 对导出为 markdown 文件（迁移命令）。

**命令签名：**
```bash
wren memory export [--path/-p PATH] [--include-seed]
```

**内部流程：**
1. 发现项目路径，构造 store（需要 memory extra）
2. 调用 `mem_store.dump_queries()`（所有行）
3. 对每行：
   - 从 tags 解析 source
   - 如果是 seed 且未 `--include-seed`：跳过
   - 通过 `write_query_markdown()` 写入 markdown
4. 报告导出/跳过计数

**关键决策点：**
- **一次性迁移命令：** 从 LanceDB 到 markdown
- **LanceDB 保持不变：** 用户运行 `index` 重建，然后 `reset`
- **默认排除 seed 对：** 会在 index 时重新生成

**正确示例：**
```bash
# 导出用户对
wren memory export

# 包括 seed 对
wren memory export --include-seed
```

---

## 子系统详解

### Schema 索引管线

```
manifest dict
    │
    ├─→ extract_schema_items(manifest)
    │       │
    │       ├─→ _model_record()      → item_type="model"
    │       ├─→ _column_record()     → item_type="column"
    │       ├─→ _relationship_record() → item_type="relationship"
    │       ├─→ _view_record()       → item_type="view"
    │       ├─→ _cube_record()       → item_type="cube"
    │       ├─→ _measure_record()    → item_type="measure"
    │       ├─→ _cube_dimension_record() → item_type="cube_dimension"
    │       └─→ _time_dimension_record() → item_type="time_dimension"
    │
    ├─→ _embed_fn.compute_source_embeddings(texts) → vectors
    │
    └─→ MemoryStore.index_schema()
            ├─→ drop schema_items table (replace=True)
            ├─→ create schema_items table with items + vectors
            └─→ _upsert_seed_queries() (if seed_queries=True)
                    ├─→ generate_seed_queries(manifest)
                    ├─→ delete old seed rows
                    └─→ insert new seed rows
```

**种子查询模板：**
- `List all {model}` → `SELECT * FROM {model} LIMIT 100`
- `Total {numeric_col} in {model}` → `SELECT SUM({numeric_col}) FROM {model}`
- `{numeric_col} by {group_col} in {model}` → 分组聚合
- `Show {model} where {col} is {value}` → 过滤查询（来自 acceptedValues）
- `{left} with {right} details` → JOIN 查询（来自 relationships）

**排除规则：**
- `dbtLayer: raw` 的模型被跳过
- 计算列排除在聚合种子之外
- 标识符列（`*_id`、主键、关系键）排除在数字聚合之外

---

### 查询上下文策略

```
get_context(manifest, query)
    │
    ├─→ describe_schema(manifest) → text
    │
    ├─→ if len(text) <= threshold (default 30000):
    │       return {"strategy": "full", "schema": text}
    │
    └─→ else:
            ├─→ manifest_hash(manifest) → mdl_hash
            └─→ _search_schema(query, mdl_hash, item_type, model_name)
                    └─→ LanceDB ANN search with WHERE filters
```

**关键决策：**
- **阈值 = 30,000 字符 ≈ 8,000 token**
- CJK 语言更早切换（相同字符数更多 token）
- 全文策略提供完整上下文但可能超出 LLM 窗口
- 搜索策略提供相关片段但可能丢失全局结构

---

### Markdown 同步协议

```
sync_markdown_queries(pairs)
    │
    ├─→ load_queries(pairs, upsert=True, mark_markdown_synced=True)
    │       │
    │       ├─→ 去重输入按 nl_query（后者胜出）
    │       ├─→ 准备记录带 _MARKDOWN_SYNC_TAG
    │       ├─→ 删除匹配 nl_query 的现有行
    │       └─→ 插入新记录
    │
    └─→ Forget pass:
            ├─→ 列出所有带 _MARKDOWN_SYNC_TAG 的行
            ├─→ 找到 nl_query 不在当前 pairs 中的行
            └─→ 删除过期行
```

**溯源追踪：**
- `_MARKDOWN_SYNC_TAG = "origin:markdown-sync"` 追加到 tags
- 只有由 `sync_markdown_queries` 写入的行有资格被 forget
- `source:user` 行来自 `wren memory load`，不会被 sync 遗忘

---

### Watch 监控循环

```
watch_loop(project_path, reindex, interval, max_polls, reindex_on_start)
    │
    ├─→ baseline = "" if reindex_on_start else compute_fingerprint()
    │
    └─→ while not max_polls or polls < max_polls:
            ├─→ poll_once():
            │       ├─→ current = compute_fingerprint()
            │       ├─→ if current == state.fingerprint: return False
            │       ├─→ reindex()
            │       ├─→ state.fingerprint = current  (only on success)
            │       └─→ return True
            │
            ├─→ on Exception: log, keep old fingerprint (retry next poll)
            └─→ sleep(interval)
```

**指纹计算：**
```
SHA-256 of:
    for each file in sorted(target/mdl.json, knowledge/sql/*.md):
        relative_path \0 size \0 mtime_ns \0
```

**关键特性：**
- 无文件内容读取（仅 stat）
- 失败重试（保持旧指纹）
- 干净退出（KeyboardInterrupt）
- 最小间隔 1.0 秒

---

### Embeddings 后端

**解析逻辑：**
```
WREN_EMBEDDING_BACKEND env var
    │
    ├─→ "onnx" 且 onnxruntime 可用: OnnxEmbeddings
    ├─→ "sentence-transformers" 且 torch 可用: SentenceTransformerEmbeddings
    ├─→ 自动检测: 优先 onnx，回退到 sentence-transformers
    └─→ 请求但不可用: 日志警告，使用可用后端
```

**OnnxEmbeddings 管线：**
1. 从 HF 缓存加载 tokenizer（或在线）
2. 通过 `1_Pooling/config.json` 验证 mean pooling
3. 从 `onnx/model.onnx` 加载 ONNX 模型
4. 编码：tokenize → session.run → attention-masked mean pooling → L2 normalize
5. 批大小：32（匹配 SentenceTransformer 默认）

**本地优先加载：**
- 首先尝试 `local_files_only=True`（HF 缓存）
- 回退到在线下载
- 模型实例按进程缓存（线程安全）
