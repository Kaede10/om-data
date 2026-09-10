### 基本格式

**纯 Markdown**，不需要 YAML frontmatter（与 `knowledge/sql/*.md` 不同）。

```markdown
## Default filters
- `orders` 查询排除 `deleted_at IS NOT NULL` 的行，除非用户明确要求。
- `users` 查询默认 `is_active = true AND is_internal = false`。

## Naming conventions
- "revenue" 始终指订单 `amount`，不是 `credit_card_amount` 等分渠道列。
- "active customers" = 最近 90 天有订单的客户。
```

### 核心规则

| 规范 | 说明 |
|------|------|
| **文件位置** | `knowledge/rules/*.md` |
| **文件命名** | kebab-case，一个文件一个主题（如 `revenue.md`、`units.md`） |
| **排序** | 按文件名字母序拼接，前缀字母控制顺序（`a_filters.md` 在 `b_units.md` 前） |
| **分块** | 每个 `##` 标题成为一个可检索的 memory chunk |
| **无大小限制** | 全文加载，无截断 |

### 5 个标准 `##` 标题

由 enrich-context agent 定义的规范标题：

| 标题 | 用途 |
|------|------|
| `## Default filters` | 软删除、活跃行过滤 |
| `## Naming conventions` | 业务术语 → 模型/列同义词 |
| `## External identifiers` | 跨系统 ID 映射 |
| `## Currency` | 多币种和汇率规则 |
| `## Canonical tables` | 同名表时该用哪个 |

> 不要发明新标题，使用这 5 个。

### 注入方式

规则通过 3 个渠道注入 LLM：

1. **MCP 工具** `get_instructions` — Agent 主动调用
2. **MCP 资源** `wren://instructions` — Client 订阅
3. **Memory 索引** — `wren memory index --instructions` 时注入为 `_instructions`

### 文件拼接逻辑

```python
# knowledge/rules/*.md (按文件名排序) + instructions.md (已废弃)
content = "\n\n".join([
    load_knowledge_rules(project_path),   # knowledge/rules/*.md
    load_instructions(project_path),       # instructions.md (legacy)
])
```

### 与 `instructions.md` 的区别

| | `instructions.md`（已废弃） | `knowledge/rules/`（当前） |
|---|---|---|
| 位置 | 项目根目录 | `knowledge/rules/*.md` |
| 结构 | 单一大文件 | 多个主题文件 |
| 分块 | 不分块 | 每个 `##` 标题一个 chunk |
| 迁移 | `mv instructions.md knowledge/rules/general.md` | — |

### 示例

**最小示例**（`knowledge/rules/business-rules.md`）：
```markdown
# Business rules

- An order's `amount` is recorded in USD.
- `customers.name` may be NULL for guest checkouts.
```

**完整示例**：
```markdown
## Default filters
- 所有查询排除 `is_deleted = true` 的行。
- `orders` 默认筛选 `status != 'draft'`。

## Naming conventions
- "revenue" = `orders.net_amount`（不是 `gross_amount`）。
- "活跃用户" = 最近 30 天有登录的用户。

## Canonical tables
- 用 `customers` 做分析，不用 `customers_legacy`。
- 用 `orders` 做订单分析，不用 `order_items`。

## Currency
- 所有金额单位为 USD。
- 显示时使用千分位分隔符和 2 位小数。
```

---
