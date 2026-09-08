# Wren Memory 模块指南

## 概述

Wren AI 的 Memory 模块是一个本地语义记忆层，让 AI 代理能够检索相关 schema 上下文和历史示例，从而生成更准确的 SQL 查询。

核心特点：
- **双表分离设计**：schema 表和 examples 表独立索引、独立检索
- **三源数据融合**：MDL manifest、Knowledge SQL、Seed queries
- **双路检索**：向量检索 + 文本检索（grep）互补
- **嵌入式存储**：使用 LanceDB，零外部依赖

## 架构

### 存储结构

```
storage/
├── wren_memory_schema     # 表名+DDL+描述（结构化信息）
├── wren_memory_examples   # 问题+SQL对（语义示例）
└── wren_memory_usage      # 使用统计（可选）
```

### 数据来源

| 来源 | 类型 | 写入目标 | 说明 |
|------|------|----------|------|
| MDL manifest (`target/mdl.json`) | 自动生成 | schema 表 | 提取 7 种 record 类型 |
| Knowledge SQL (`knowledge/sql/*.md`) | 用户编写 | examples 表 | NL-SQL 对，唯一事实来源 |
| Seed queries | 模板生成 | examples 表 | 基于 manifest 自动生成的 NL-SQL 对 |

## 核心组件

### 1. Schema Indexer (`schema_indexer.py`)

从 MDL manifest 提取 7 种 record 类型：

```python
SCHEMA_RECORD_TYPES = [
    "model",           # 模型定义
    "model_column",    # 模型列
    "relationship",    # 关系定义
    "view",           # 视图定义
    "view_column",    # 视图列
    "cube",           # 聚合定义
    "cube_measure",   # 聚合度量
]
```

提取流程：
1. 遍历 manifest 中的所有 models
2. 为每个 model 提取：表名、描述、DDL、列信息
3. 提取 relationships、views、cubes
4. 生成文本描述，用于嵌入

### 2. Seed Generator (`seed_queries.py`)

基于 5 种模板自动生成 NL-SQL 对：

| 模板 | 生成内容 |
|------|----------|
| `table_count` | "How many records are in {table}?" |
| `column_list` | "What columns does {table} have?" |
| `column_select` | "Show me {column} from {table}" |
| `column_where` | "Show me {column} from {table} where {condition}" |
| `join` | "Show me {columns} from {table1} join {table2}" |

生成规则：
- 排除 raw 层表
- 排除标识符列（如 `id`、`_key`）
- 每个表最多生成 5 个查询
- 已存在的相同查询会被跳过（幂等）

### 3. Embeddings Engine (`embeddings.py`)

双后端嵌入引擎：

```python
# 后端选择优先级
1. ONNX Runtime（优先）
2. sentence-transformers（降级）
3. 异常
```

配置方式：
```bash
# 自动选择（推荐）
WREN_MEMORY_EMBEDDING_BACKEND=auto

# 强制指定
WREN_MEMORY_EMBEDDING_BACKEND=onnx
WREN_MEMORY_EMBEDDING_BACKEND=sentence-transformers
```

模型信息：
- 模型：`sentence-transformers/all-MiniLM-L6-v2`
- 维度：384
- 大小：~80MB（ONNX）

### 4. Memory Store (`store.py`)

LanceDB 核心存储：

```python
class MemoryStore:
    def __init__(self, path: str | Path | None = None):
        # 默认路径：~/.wren/memory/
        self._db = lancedb.connect(str(resolved))
```

主要方法：
- `index_schema()` — 索引 schema 数据
- `sync_markdown_queries()` — 同步 NL-SQL 对
- `search_schema()` — schema 检索
- `search_examples()` — 示例检索
- `fetch()` — 组合检索（schema + examples）

### 5. Watch Loop (`watch.py`)

基于轮询的文件监控：

```python
def watch_loop(store, project_path, reindex_fn, poll_interval_secs):
    fingerprint = _snapshot(project_path)  # → {path: (mtime, size)}
    
    while True:
        time.sleep(poll_interval_secs)
        new_fp = _snapshot(project_path)
        
        if _files_changed(fingerprint, new_fp):
            if not _already_hashed(new_fp):
                reindex_fn()
                _remember_hash(new_fp)
        
        fingerprint = new_fp
```

监控范围：
- `target/mdl.json` — manifest
- `knowledge/sql/*.md` — NL-SQL 对

特点：
- 不读文件内容，只 `stat()` 对比元数据
- 失败不丢弃，下次轮询重试
- 幂等：hash 相同就跳过

### 6. Markdown Sync (`markdown.py`)

Knowledge SQL 同步：

```python
def sync_markdown_queries(self, pairs: list[dict]) -> dict[str, int]:
    # 加载现有记录
    existing = self.search_examples(text_query, limit=9999)
    
    # 对比并更新
    for pair in pairs:
        if existing_record:
            # 更新
            self.update_examples([updated_record])
        else:
            # 插入
            self.insert_examples([new_record])
```

标记系统：
- `origin: knowledge` — 用户手写
- `origin: markdown-sync` — markdown 同步
- `origin: seed` — 自动生成

## 检索策略

### Schema 检索

```python
def search_schema(self, text_query, max_items=10, schema_strategy="auto"):
    # 1. 全文检索
    full_results = self.search_full_schema(text_query, max_items)
    
    # 2. 向量检索
    vec_results = self.search_vec_schema(text_query, max_items)
    
    # 3. 合并去重
    combined = self._deduplicate(full_results, vec_results)
    
    return combined[:max_items]
```

策略选择：
- `auto` — 根据 schema 大小自动选择
- `full_text` — 仅全文检索
- `vector` — 仅向量检索
- `both` — 两种都用

### 示例检索

```python
def search_examples(self, text_query, max_examples=5):
    # 1. 向量检索
    vec_results = self.search_vec_examples(text_query, max_examples)
    
    # 2. 降级到 grep
    if not vec_results:
        grep_results = self.search_grep_examples(text_query, max_examples)
        return sorted(grep_results, key=lambda r: r.get("score", 0), reverse=True)
    
    return vec_results
```

### 组合检索

```python
def fetch(self, query, max_schema_items=10, max_examples=5):
    # Schema 检索
    schema_results = self.search_schema(query, max_schema_items)
    
    # 示例检索
    example_results = self.search_examples(query, max_examples)
    
    return {
        "schema": schema_results,
        "examples": example_results,
        "schema_tokens": self._count_tokens(schema_results),
        "example_tokens": self._count_tokens(example_results),
    }
```

## 关键决策点

### 1. Embedding 后端选择

```python
def resolve_embedding_backend() -> str:
    # 1. 环境变量覆盖
    env_backend = os.getenv("WREN_MEMORY_EMBEDDING_BACKEND")
    if env_backend:
        return env_backend
    
    # 2. 自动检测
    try:
        import onnxruntime
        return "onnx"
    except ImportError:
        pass
    
    try:
        import sentence_transformers
        return "sentence-transformers"
    except ImportError:
        pass
    
    raise ImportError("No embedding backend available")
```

### 2. Schema 检索策略

```python
def _resolve_schema_strategy(self, max_items: int) -> str:
    # 获取 schema 统计
    stats = self._get_schema_stats()
    
    # 根据大小选择策略
    if stats["total_tokens"] < 10000:
        return "both"  # 小 schema，两种都用
    elif stats["total_tokens"] < 50000:
        return "vector"  # 中等 schema，用向量
    else:
        return "full_text"  # 大 schema，用全文
```

### 3. 示例数量控制

```python
def _resolve_max_examples(self, query: str) -> int:
    # 基础数量
    base = 5
    
    # 根据查询复杂度调整
    if self._is_complex_query(query):
        return min(base * 2, 10)
    
    return base
```

## CLI 命令

### 索引命令

```bash
# 索引 schema
wren memory index

# 索引 schema（强制重建）
wren memory index --force

# 索引 NL-SQL 对
wren memory sync

# 完整索引（schema + NL-SQL）
wren memory index --all
```

### 检索命令

```bash
# schema 检索
wren memory fetch -q "用户表有哪些列？"

# 示例检索
wren memory recall -q "如何查询月度收入？"

# 组合检索
wren memory search -q "用户订单统计"
```

### 监控命令

```bash
# 启动文件监控
wren memory watch

# 指定轮询间隔
wren memory watch --interval 10

# 启动时先执行一次重索引
wren memory watch --reindex-on-start

# 限制轮询次数（测试用）
wren memory watch --max-polls 100
```

### 管理命令

```bash
# 查看使用统计
wren memory usage

# 查看过期记录
wren memory stale

# 清理过期记录
wren memory cleanup

# 健康检查
wren memory health
```

## 部署指南

### 单机部署

```bash
# 1. 安装依赖
pip install "wrenai[memory]"

# 2. 初始化项目
wren init --source-type bigquery --dataset your_dataset

# 3. 启动索引
wren memory index

# 4. 启动监控（可选）
wren memory watch &

# 5. 启动服务
wren serve
```

### Docker 部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 复制项目
COPY . .

# 启动命令
CMD ["wren", "serve"]
```

### 分离部署（推荐生产环境）

```yaml
# docker-compose.yml
services:
  query:
    image: wren-ai
    command: wren serve
    volumes:
      - wren-memory:/root/.wren/memory
      - ./target:/app/target
      - ./knowledge:/app/knowledge
    ports:
      - "8080:8080"

  watch:
    image: wren-ai
    command: wren memory watch --reindex-on-start --interval 30
    volumes:
      - wren-memory:/root/.wren/memory
      - ./target:/app/target
      - ./knowledge:/app/knowledge

volumes:
  wren-memory:
```

关键点：
- 两个容器挂载同一个 `wren-memory` volume
- LanceDB 使用 MVCC，支持并发读写
- 先启动 watch 完成首次索引，再启动 query

## 性能优化

### 索引优化

```bash
# 批量索引
wren memory index --batch-size 100

# 并行嵌入
WREN_MEMORY_EMBEDDING_WORKERS=4 wren memory index
```

### 检索优化

```python
# 调整检索参数
store = MemoryStore(
    path="~/.wren/memory/",
    embedding_model="all-MiniLM-L6-v2",  # 使用更小的模型
)

# 缓存结果
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_search(query: str):
    return store.fetch(query)
```

### 监控优化

```bash
# 增大轮询间隔
wren memory watch --interval 60

# 使用 inotify（如果支持）
WREN_MEMORY_WATCH_BACKEND=inotify wren memory watch
```

## 常见问题

### Q: 为什么选择 ONNX 而不是 sentence-transformers？

A: ONNX 优先因为：
- 无需 torch 依赖，部署包更小
- 推理速度更快
- 两者输出相同维度（384-dim），可互换

### Q: 如何查看索引状态？

A: 使用以下命令：
```bash
wren memory health      # 健康检查
wren memory usage       # 使用统计
wren memory stale       # 过期记录
```

### Q: 索引失败怎么办？

A: 检查以下几点：
1. 确保 `target/mdl.json` 存在
2. 确保 `knowledge/sql/` 目录存在
3. 检查 LanceDB 存储空间
4. 查看日志：`wren memory health`

### Q: 如何迁移旧版本的索引？

A: 使用导出命令：
```bash
wren memory export      # 导出到 markdown
wren memory index       # 重新索引
```

### Q: 多人协作时如何同步？

A: 提交 `knowledge/` 目录：
```bash
git add knowledge/
git commit -m "更新 NL-SQL 对"
git push

# 其他成员拉取后重新索引
git pull
wren memory index
```

## 最佳实践

1. **定期索引**：修改 schema 或 NL-SQL 后及时执行 `wren memory index`
2. **使用版本控制**：将 `knowledge/` 纳入 git 管理
3. **监控健康状态**：定期执行 `wren memory health`
4. **分离部署**：生产环境将 watch 和 query 分开部署
5. **清理过期记录**：定期执行 `wren memory cleanup`

## 相关文档

- [Memory System](/oss/concepts/memory_system) — 概念介绍
- [CLI Reference](/oss/reference/cli#wren-memory--schema--query-memory) — 命令参考
- [Refine Answer Quality](/oss/guides/refine) — 优化指南
- [Agent Learning](/oss/concepts/agent_learning) — 学习循环
