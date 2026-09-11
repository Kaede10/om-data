# Rules 与 Model 机制详解

> 本文档详细记录 `knowledge/rules/*.md` 业务规则和 MDL 模型系统的加载机制、关键约束、性能影响和最佳实践。

---

## 目录

1. [Rules 加载机制](#rules-加载机制)
2. [Rules 使用链路](#rules-使用链路)
3. [Model (MDL) 加载机制](#model-mdl-加载机制)
4. [Model 规模影响分析](#model-规模影响分析)
5. [Schema 上下文策略](#schema-上下文策略)
6. [Rules 最佳实践](#rules-最佳实践)
7. [Model 最佳实践](#model-最佳实践)
8. [常见问题与排查](#常见问题与排查)

---

## Rules 加载机制

### 文件格式

- **格式**：纯 Markdown (`.md`)，无 YAML frontmatter
- **位置**：`knowledge/rules/*.md`
- **命名**：kebab-case，一个文件一个主题
- **排序**：按文件名字母序拼接（前缀字母控制顺序）

### 加载代码

```python
# context.py:825-835
def load_knowledge_rules(project_path: Path) -> str | None:
    """Concatenate knowledge/rules/*.md (sorted). None if there are none."""
    rules_dir = project_path / "knowledge" / "rules"
    if not rules_dir.is_dir():
        return None
    parts = [
        text
        for f in sorted(rules_dir.glob("*.md"))  # 所有 *.md，无数量限制
        if (text := f.read_text(encoding="utf-8").strip())  # 全文读取，无行数限制
    ]
    return "\n\n".join(parts) if parts else None
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **文件数量** | 无限制，`glob("*.md")` 自动发现 |
| **文件大小** | 无限制，全文读取无截断 |
| **分块粒度** | 每个 `##` 标题成为一个可检索的 memory chunk |
| **空文件处理** | 自动跳过（walrus operator 过滤） |
| **Legacy 兼容** | `instructions.md` 内容追加在 `knowledge/rules/` 之后 |

### Legacy 迁移

```python
# context.py:838-855
def load_rules(project_path: Path) -> tuple[str | None, bool]:
    parts: list[str] = []
    rules = load_knowledge_rules(project_path)  # knowledge/rules/*.md
    if rules:
        parts.append(rules)
    legacy = load_instructions(project_path)    # instructions.md (已废弃)
    if legacy:
        parts.append(legacy)
    content = "\n\n".join(parts) if parts else None
    used_legacy = (project_path / "instructions.md").exists()
    return content, used_legacy
```

**迁移命令**：
```bash
mv instructions.md knowledge/rules/general.md
```

---

## Rules 使用链路

### 三个注入渠道

```
knowledge/rules/*.md
       │
       ▼  sorted + "\n\n" 拼接
   load_knowledge_rules()
       │
       ├──→ MCP Tool: get_instructions()
       │         └─ LLM 主动调用，返回全部文本
       │
       ├──→ MCP Resource: wren://instructions
       │         └─ Client 订阅
       │
       └──→ CLI: wren context instructions
                 └─ 终端打印
```

**注意**：`manifest["_instructions"]` 虽然被加入 manifest，但 `extract_schema_items()` 只提取 models/columns/relationships/views/cubes，**不提取 `_instructions`**。所以 rules 不参与向量检索，只能通过上述三个渠道全量获取。

### MCP Tool 调用

```python
# mcp_server.py:362-367
@mcp.tool(
    annotations=ToolAnnotations(title="Get Instructions", readOnlyHint=True),
)
def get_instructions() -> dict:
    """Return business rules and instructions from knowledge/rules/*.md."""
    from wren.context import load_rules
    content, used_legacy = load_rules(ctx.project)
    return {"instructions": content or "", "used_legacy": used_legacy}
```

### Workflow Prompt 触发

```python
# mcp_server.py:647-648
steps = [
    ...
    "Call `get_instructions` for business rules that affect how to "
    "interpret the data.",
    ...
]
```

### 全量加载的影响

| 场景 | 行为 | 影响 |
|------|------|------|
| LLM 调用 `get_instructions` | 返回全部 rules 文本 | 规则越多 → token 消耗越大 |
| Memory 索引 | `_instructions` 加入 manifest 但未被提取 | **不存入向量库，不可检索** |
| LLM 自行判断 | 在完整上下文中筛选相关规则 | 无相关性过滤机制 |

**结论**：Rules 只能全量加载，无法按需检索。这是与 Schema（可通过 `get_context()` 向量检索）的关键区别。

---

## Model (MDL) 加载机制

### MDL JSON 结构

```json
{
  "catalog": "...",
  "schema": "...",
  "models": [...],      // 模型定义
  "relationships": [...], // 关系定义
  "views": [...],       // 视图定义
  "cubes": [...]        // Cube 定义
}
```

### 加载代码

```python
# mcp_server.py:547-552
@mdl.resource("wren://mdl", mime_type="application/json")
def mdl_resource() -> str:
    """The compiled MDL (models, relationships, cubes) as JSON."""
    from wren.context import build_json
    return json.dumps(build_json(ctx.project))  # 全量 JSON，无截断
```

### Schema 描述生成

```python
# schema_indexer.py:94-124
def describe_schema(manifest: dict) -> str:
    """Generate a structured plain-text description of the full MDL schema."""
    lines: list[str] = []
    # ... 生成每个 model/relationship/view/cube 的文本描述
    for model in _iter_section(manifest, "models"):
        _describe_model(model, lines)
    for rel in _iter_section(manifest, "relationships"):
        _describe_relationship(rel, lines)
    # ...
    return "\n".join(lines)
```

---

## Model 规模影响分析

### 4000+ 模型的估算

| 指标 | 估算值 |
|------|--------|
| 模型数量 | 4000+ |
| 平均列数/模型 | 10-20 列 |
| 总列数 | 40,000-80,000 |
| JSON 大小 | 5-10 MB |
| 纯文本描述 | 200,000+ chars |
| Token 估算 | 50,000-100,000 tokens |

### 影响链路

```
mdl.json (5-10MB)
    │
    ├── wren://mdl 资源 ──→ LLM 读取时一次性加载进上下文
    │                        └─ 5MB JSON ≈ 1.5M tokens → 远超上下文窗口
    │
    ├── describe_schema() ──→ 生成纯文本描述
    │                         └─ 4000 模型 × 15 列 = 60,000 行文本
    │                            ≈ 200K+ chars → 远超 30K 阈值
    │
    └── get_context() ──→ 自动选择策略
                           └─ < 30K chars: "full" 策略（全量返回）
                           └─ > 30K chars: "search" 策略（向量检索）
```

### 关键阈值

```python
# schema_indexer.py:70
SCHEMA_DESCRIBE_THRESHOLD = 30_000  # 约 8K tokens

# 低于阈值：全量返回
# 高于阈值：向量检索
```

---

## Schema 上下文策略

### Rules vs Schema 的关键区别

| 方面 | Rules (`knowledge/rules/*.md`) | Schema (MDL models) |
|------|-------------------------------|---------------------|
| 加载方式 | 全量拼接，无截断 | 按策略选择（full/search） |
| 向量检索 | **不支持** | 支持（`get_context()`） |
| 存储位置 | 不存入 LanceDB | 存入 `schema_items` 表 |
| 规模影响 | 2000-3000 行 ≈ 8K-12K tokens | 4000+ 模型需 search 策略 |
| 优化空间 | 有限（只能控制文件数量） | 大（向量检索按需返回） |

### 自动策略选择

```python
# store.py:315-344
def get_context(
    manifest: dict,
    query: str,
    *,
    limit: int = 5,
    threshold: int = SCHEMA_DESCRIBE_THRESHOLD,
) -> dict:
    """Return schema context using the best strategy for the schema size."""
    text = describe_schema(manifest)
    if len(text) <= threshold:
        return {"strategy": "full", "schema": text}      # 小模型：全量
    # 大模型：向量检索
    results = self._search_schema(query, limit=limit, ...)
    return {"strategy": "search", "results": results}
```

### 两种策略对比

| 策略 | 条件 | 行为 | 适用场景 |
|------|------|------|----------|
| `full` | `describe_schema()` ≤ 30K chars | 返回完整文本 | 模型 < 500 个 |
| `search` | `describe_schema()` > 30K chars | 向量检索相关片段 | 模型 > 500 个 |

### MCP Tool 调用

```python
# mcp_server.py:389-429
def get_context(
    question: str,
    limit: int = 5,
    item_type: str | None = None,
    model_name: str | None = None,
) -> dict:
    """Semantic retrieval of the schema fragments relevant to a question."""
    manifest = build_json(ctx.project)
    try:
        from wren.memory.store import MemoryStore
        store = MemoryStore(path=_memory_path(ctx))
        return store.get_context(
            manifest, question, limit=limit,
            item_type=item_type, model_name=model_name,
        )
    except ImportError:
        # 无 memory 扩展：回退到全量文本
        return {
            "strategy": "full",
            "schema": schema_indexer.describe_schema(manifest),
            "note": "Install wrenai[memory] for embedding-based schema search.",
        }
```

### 前置条件

| 条件 | 说明 |
|------|------|
| 安装 `wren[memory]` | 提供 LanceDB + embeddings 支持 |
| 运行 `wren memory index` | 建立向量索引 |
| 索引与 MDL 同步 | MDL 变更后需重新索引 |

---

## Rules 最佳实践

### 文件组织

```
knowledge/rules/
├── user-identity.md            # 用户定义、跨平台归一、企业归属
├── user-tiering.md             # D0/D1/D2 分级
├── contribution-metrics.md     # PR/Issue/Comment 指标 + 清洗链 + 平台差异
├── repo-metrics.md             # 仓库维度指标
├── download-metrics.md         # 下载量统计
├── company-distribution.md     # 企业维度分布
├── forum-metrics.md            # 论坛指标
├── ci-cd-metrics.md            # CI/CD + NPU
└── naming.md                   # 业务术语映射
```

### 编写规范

1. **每个 `##` 标题 = 一个检索 chunk**
   ```markdown
   ## Cross-platform identity merging
   - 同一用户在 GitHub/GitCode/Gitee 通过 ONEID 归一。
   - `platform_user_id` 格式为 `{platform}:{user_id}`。
   ```

2. **规则写事实，不写代码**
   ```markdown
   ✅ "star 总量 = 三平台去重合计"
   ❌ "SELECT SUM(stars) FROM ..."
   ```

3. **先定义再引用**
   - `health-models.md` 定义阈值
   - `naming.md` 映射术语
   - 其他文件引用它们

4. **控制总量**
   - 建议合并后总文本 ≤ 3000 行
   - 每个文件 200-500 行为宜

### 命名约定

| 规范 | 说明 |
|------|------|
| 文件名 | kebab-case（如 `user-tiering.md`） |
| 排序 | 字母序，前缀控制顺序（`a_filters.md` 在 `b_units.md` 前） |
| 标题 | `##` 级别，清晰描述内容 |

---

## Model 最佳实践

### 模型数量控制

| 规模 | 建议 |
|------|------|
| < 500 模型 | 无特殊处理，`full` 策略足够 |
| 500-2000 模型 | 必须安装 `wren[memory]`，运行 `wren memory index` |
| > 2000 模型 | 强烈建议使用 `get_context()` 而非 `describe_schema()` |

### 模型设计原则

1. **按主题分组模型**
   ```
   fact_{community}_pr        # PR 相关
   fact_{community}_issue     # Issue 相关
   dws_{community}_contribute # 聚合层
   ```

2. **使用视图简化复杂查询**
   ```json
   {
     "views": [{
       "name": "active_contributors",
       "statement": "SELECT ... FROM dws_contribute WHERE ..."
     }]
   }
   ```

3. **利用 Cube 预定义指标**
   ```json
   {
     "cubes": [{
       "name": "contribution_metrics",
       "measures": [...],
       "dimensions": [...]
     }]
   }
   ```

### 性能优化

1. **避免过度规范化**
   - 合理使用宽表（如 `dws_{community}_contribute`）
   - 减少 JOIN 复杂度

2. **使用 `get_context()` 而非 `describe_schema()`**
   ```python
   # ❌ 全量加载
   schema = describe_schema(manifest)  # 200K+ chars
   
   # ✅ 按需检索
   context = get_context(question="D1 贡献者的 PR 合入率")
   ```

3. **索引同步**
   ```bash
   # MDL 变更后重新索引
   wren memory index --force
   ```

---

## Models 变更与 Memory 索引

### MDL 构建流程

```python
# context.py:891-923
def build_manifest(project_path: Path) -> dict:
    models = load_models(project_path)      # 读取 YAML 文件
    views = load_views(project_path)
    relationships = load_relationships(project_path)
    cubes = load_cubes(project_path)
    manifest = {"models": models, ...}
    return manifest

# context.py:549-559
def load_models(project_path: Path) -> list[dict]:
    sv = get_schema_version(project_path)
    if sv == 1:
        return _load_models_v1(project_path)  # models/*.yml
    return _load_models_v2(project_path)       # models/<name>/metadata.yml
```

**关键点**：`load_models()` 只读取存在的文件。删除 YAML 文件后重新 build，mdl.json 中对应模型消失。

### 删除 YAML 文件的影响

```
删除 models/orders.yml
    │
    ▼
wren build（重新生成 mdl.json）
    │
    ├──→ mdl.json：orders 模型消失 ✅
    │
    └──→ Memory 索引：orders 仍存在 ❌（快照，不自动更新）
```

### Memory 索引重建机制

```python
# store.py:210-258
def index_schema(self, manifest, *, replace=True):
    items = extract_schema_items(manifest)  # 从当前 manifest 提取
    if replace:
        self._db.drop_table(_SCHEMA_TABLE)  # 整表删除
        self._db.create_table(_SCHEMA_TABLE, items)  # 重建
```

| 命令 | `replace` 参数 | 行为 |
|------|---------------|------|
| `wren memory index` | `True`（默认） | 整表删除重建 |
| `wren memory index --force` | `True` | 整表删除重建（跳过确认） |
| `wren memory watch` | `True`（默认） | 整表删除重建 |

**注意**：`--force` 只是跳过确认提示，不影响 `replace` 行为。

### 自动同步方案

```bash
# 方案 1：手动重建
wren memory index

# 方案 2：用 watch 自动重建
wren memory watch --reindex-on-start
```

```python
# watch.py 会监控文件变化，自动触发 reindex
def poll_once(project_path, state, reindex, on_event):
    new_fp = compute_fingerprint(project_path)
    if new_fp != state.baseline:
        reindex()  # 自动重建
```

### 完整变更流程

```
1. 修改 YAML 文件（增删改模型）
       │
       ▼
2. wren build
       │
       ├──→ mdl.json 更新
       │
       └──→ Memory 索引不更新（快照）
               │
               ▼
3. wren memory index（或 watch 自动触发）
       │
       ├──→ 删除旧 schema_items 表
       ├──→ 从新 manifest 提取 items
       ├──→ 向量化并存储
       └──→ 重建 seed queries
```

### 验证索引状态

```bash
# 检查索引是否与当前 MDL 一致
wren memory check

# 查看索引的 schema items 数量
wren memory describe
```

---

## 常见问题与排查

### Q: Rules 和 Schema 有什么区别？

**A**:

| 方面 | Rules (`knowledge/rules/*.md`) | Schema (MDL models) |
|------|-------------------------------|---------------------|
| 内容 | 业务规则、术语映射、计算逻辑 | 表/列/关系定义 |
| 加载 | 全量拼接，无截断 | 按策略选择（full/search） |
| 向量检索 | **不支持** | 支持（`get_context()`） |
| 存储 | 不存入 LanceDB | 存入 `schema_items` 表 |
| 优化 | 控制文件数量和行数 | 向量检索按需返回 |

### Q: Rules 文件太多会导致 LLM 上下文溢出吗？

**A**: 会。建议：
- 合并后总文本 ≤ 3000 行
- 使用 `##` 标题分 chunk，提高检索精度
- 监控 `get_instructions` 返回的文本长度

### Q: 4000+ 模型时 `describe_schema()` 返回空内容？

**A**: 不会返回空，但会返回 200K+ chars 文本，远超 LLM 上下文窗口。解决方案：
- 使用 `get_context(question)` 自动切到 `search` 策略
- 安装 `wren[memory]` 并运行 `wren memory index`

### Q: Rules 和 Instructions 有什么区别？

**A**:

| 方面 | `instructions.md`（已废弃） | `knowledge/rules/`（当前） |
|------|---|---|
| 位置 | 项目根目录 | `knowledge/rules/*.md` |
| 结构 | 单一大文件 | 多个主题文件 |
| 分块 | 不分块 | 每个 `##` 标题一个 chunk |
| 迁移 | `mv instructions.md knowledge/rules/general.md` | — |

### Q: 如何验证 Rules 加载是否正确？

**A**:
```bash
# 查看加载的 rules 内容
wren context instructions

# 查看 memory 中的 _instructions
wren memory fetch --include-instructions
```

### Q: MDL 变更后需要做什么？

**A**:
```bash
# 1. 重新 build
wren build

# 2. 重新索引 memory（必须）
wren memory index

# 3. 验证索引
wren memory check
```

**或使用 watch 自动同步**：
```bash
wren memory watch --reindex-on-start
```

---

## 性能优化与资源需求

### 资源消耗估算（4000+ 模型）

| 组件 | 内存 | CPU | 说明 |
|------|------|-----|------|
| Python dict (manifest) | ~30-50MB | 低 | 模型/列/关系/视图/Cube 结构 |
| JSON 字符串 | ~5-10MB | 低 | `json.dumps()` 输出 |
| 文本描述 | ~200KB | 低 | `describe_schema()` 输出 |
| LanceDB 索引 | ~30-50MB | 首次高 | 向量嵌入 (128维 × 4000 模型 × 15 列) |
| **总计** | **~70-110MB** | — | |

### 推荐配置

| 场景 | CPU | 内存 | 说明 |
|------|-----|------|------|
| 开发/测试 | 2 核 | 2GB | 够用 |
| 生产/频繁查询 | 4 核 | 4GB | 推荐 |
| 大规模索引 | 4 核 + GPU | 8GB | 向量嵌入加速 |

### 优化方向

#### 1. `get_context()` 的冗余文本生成

**问题**：`get_context()` 每次都先调用 `describe_schema()` 生成全量文本，再判断长度决定策略。对于大模型，生成 200K+ chars 文本后丢弃，浪费 CPU 和内存。

```python
# 当前实现（store.py:332-344）
def get_context(manifest, query, ...):
    text = describe_schema(manifest)  # 每次都生成全量文本
    if len(text) <= threshold:
        return {"strategy": "full", "schema": text}
    # 大模型：丢弃 text，用向量检索
    results = self._search_schema(query, ...)
    return {"strategy": "search", "results": results}
```

**优化方案**：先检查 manifest 大小，跳过 `describe_schema()`：

```python
# 优化方案（未实现）
def get_context(manifest, query, ...):
    model_count = len(manifest.get("models", []))
    if model_count < 500:  # 快速判断
        return {"strategy": "full", "schema": describe_schema(manifest)}
    # 大模型：直接向量检索
    results = self._search_schema(query, ...)
    return {"strategy": "search", "results": results}
```

**收益**：避免生成 200K+ chars 文本，节省 ~100ms CPU 时间和 ~200KB 内存。

#### 2. `wren://mdl` 资源无截断

**问题**：`wren://mdl` 资源返回全量 JSON（5-10MB），LLM 直接读取会爆上下文。

```python
# 当前实现（mcp_server.py:547-552）
@mdl.resource("wren://mdl")
def mdl_resource() -> str:
    return json.dumps(build_json(ctx.project))  # 全量 JSON，无截断
```

**优化方案**：
- 方案 A：workflow prompt 明确指示 LLM 不要直接读 `wren://mdl`，而是用 `get_context()` 或 `describe_schema()`
- 方案 B：`wren://mdl` 返回摘要版本（只包含模型名称和列名，不包含完整定义）

**收益**：避免 LLM 上下文溢出。

#### 3. Rules 全量加载

**问题**：`get_instructions()` 返回全部 rules 文本（可能 2000-3000 行），无法按需检索。

```python
# 当前实现（mcp_server.py:362-367）
def get_instructions() -> dict:
    content, used_legacy = load_rules(ctx.project)  # 全量拼接
    return {"instructions": content or ""}  # 全量返回
```

**优化方案**：
- 方案 A：MCP 层加参数，按 topic 筛选文件
- 方案 B：将 rules 按 `##` 标题分 chunk，存入向量库，按查询检索相关 chunk

**收益**：减少 token 消耗，提高检索精度。

#### 4. Memory 索引全量重建

**问题**：`wren memory index` 每次都整表删除重建，即使只修改了一个模型。

```python
# 当前实现（store.py:240-258）
if replace:
    self._db.drop_table(_SCHEMA_TABLE)  # 整表删除
    self._db.create_table(_SCHEMA_TABLE, items)  # 重建
```

**优化方案**：
- 方案 A：增量更新（比较 manifest hash，只更新变化的 items）
- 方案 B：并行向量化（使用多线程/GPU 加速嵌入计算）

**收益**：减少索引时间（从 ~30s 降到 ~5s）。

### 性能瓶颈分析

| 瓶颈 | 影响 | 优先级 |
|------|------|--------|
| `describe_schema()` 冗余生成 | 每次查询浪费 ~100ms | 中 |
| `wren://mdl` 全量返回 | LLM 上下文溢出 | 高 |
| Rules 全量加载 | token 消耗大 | 中 |
| Memory 全量重建 | 索引时间长 | 低 |

---

## 总结

| 机制 | 加载方式 | 规模影响 | 应对策略 |
|------|----------|----------|----------|
| **Rules** | 全量拼接，**不存入向量库** | 2000-3000 行 ≈ 8K-12K tokens | 控制总量，`##` 分 chunk |
| **MDL JSON** | 全量加载 | 4000+ 模型 ≈ 5-10MB | 使用 `get_context()` 检索 |
| **Schema 描述** | 按策略选择 | > 30K chars 切 search | 安装 memory 扩展 |
| **Instructions** | 全量返回 | 同 Rules | 控制总量 |

**核心原则**：
1. Rules 控制在 3000 行以内（无法向量检索，只能全量加载）
2. 模型 > 500 个时必须用 memory 扩展
3. 使用 `get_context()` 而非 `describe_schema()` 处理大模型
4. MDL 变更后必须重新索引 memory（`wren memory index`）
5. 删除 YAML 文件后，mdl.json 会更新，但 Memory 索引需要手动重建
6. 4000+ 模型推荐 4 核 CPU + 4GB 内存
