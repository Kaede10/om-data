# NPU资源利用率查询脚本计算逻辑文档

## 1. 功能概述
计算并返回**NPU资源利用率**（已用卡数/总卡数），支持按维度分组展示。**引入了历史最大节点数计算总卡数,此数据不是真实值，后续通过上报的 total npu node 进行计算**。

## 2. 核心参数
| 参数 | 说明 |
|------|------|
| `dimension` | 分组维度，默认`project` |
| `value` | 过滤值，"All"表示全部，支持逗号多选 |
| `start`/`end` | 时间范围，自动归一化并限制最大31天 |
| `step` | 采样步长，自适应调整（最小15秒） |

## 3. 安全过滤器（固定）
所有查询强制排除以下项目（不可绕过）：
```
project!="unknown",
project!~".*(test|测试|昇思|coder|argo).*"
```

## 4. 总卡数计算逻辑（关键差异点）

### 4.1 计算原理
**总卡数 = 历史最大节点数 × 8卡/节点**

通过`max_over_time`获取时间窗口内**同时存在的最大节点数**，乘以固定系数`CARDS_PER_NODE=8`。

### 4.2 时间窗口计算
```javascript
var span = e - s;
if (span < 604800) { span = 604800; }  // 最小7天
```
确保计算总卡数时至少回溯7天数据，避免因短时间窗口导致节点数低估。

### 4.3 分组/汇总查询语句

| 场景 | 已用卡数（分子） | 总卡数（分母） | 利用率计算 |
|------|----------------|---------------|------------|
| **有分组**<br/>`value`有具体值 | `sum by(dim)(custom_npu_total_used_count{sel})` | `max_over_time(count by(dim)(count by(dim, node)(custom_npu_total_used_count{sel}))[span:1d]) * 8` | `已用 / 总卡数`<br/>按`dim`对齐 |
| **无分组**<br/>`value`为"All" | `sum(custom_npu_total_used_count{sel})` | `max_over_time(count(count by(node)(custom_npu_total_used_count{sel}))[span:1d]) * 8` | `已用 / 总卡数` |

**关键操作说明**：
- `count by(dim, node)`：统计每个维度下存在的节点
- `count by(dim)`：统计每个维度下的节点数量
- `max_over_time(...[span:1d])`：取时间窗口内最大值（步长1天）
- `on(dim)`：确保分子分母按同一维度对齐

## 5. 输出格式
```json
{
  "series": [
    {"name": "总利用率", "points": [[t1, v1], [t2, v2], ...]},
    {"name": "projectA", "points": [[t1, v1], ...]},
    {"name": "projectB", "points": [[t1, v1], ...]}
  ]
}
```
- **无分组**：返回1条"总利用率"
- **有分组**：返回N条，以维度值为名称

## 6. 与用量查询的差异对比
| 对比项 | 用量查询 | 利用率查询（本脚本） |
|--------|----------|---------------------|
| 计算目标 | 绝对卡数 | 百分比（已用/总数） |
| 分母处理 | 不需要 | 需计算历史最大节点数×8 |
| 时间窗口 | 仅限制查询范围 | 额外要求最小7天窗口 |
| 复杂度 | 简单聚合 | 嵌套聚合 + `max_over_time` |

## 7. 使用示例
| 场景 | `dimension` | `value` | 输出内容 |
|------|-------------|---------|----------|
| 整体利用率 | （默认） | `"All"` | 1条"总利用率"曲线 |
| 各项目利用率 | `"project"` | `"pytorch,vision"` | pytorch/vision各1条曲线 |
| 各集群利用率 | `"cluster"` | `"prod,staging"` | prod/staging各1条曲线 |
