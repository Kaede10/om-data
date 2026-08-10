# NPU资源使用统计快照查询脚本计算逻辑文档

## 1. 功能概述
查询**当前时刻**的NPU资源使用统计快照，返回以下关键指标：
- 总卡数、已用卡数、当前利用率
- 历史（默认7天）的P50/P90/平均值（用量和利用率）

## 2. 核心参数
| 参数 | 说明 |
|------|------|
| `dimension` | 过滤维度，默认`project`（仅用于筛选，**不分组**） |
| `value` | 过滤值，"All"表示全部，支持逗号多选 |
| `start`/`end` | 用于确定历史统计的时间窗口（最小7天） |

## 3. 安全过滤器（固定）
所有查询强制排除以下项目（不可绕过）：
```
project!="unknown",
project!~".*(test|测试|昇思|coder|argo).*"
```

## 4. 输出字段说明
| 字段 | 说明 |
|------|------|
| `totalCards` | 总卡数（历史最大节点数×8） |
| `totalUsed` | 当前已用卡数 |
| `utilization` | 当前利用率（已用/总数） |
| `usedP50`/`usedP90`/`usedAvg` | 历史用量分位数/平均值 |
| `utilP50`/`utilP90`/`utilAvg` | 历史利用率分位数/平均值 |

## 5. 核心计算逻辑

### 5.1 时间窗口确定
```javascript
var diff = e - s;
if (diff < 604800) { diff = 604800; }  // 最小7天
var span = diff + "s";  // 如 "604800s"
```

### 5.2 已用卡数（即时查询）
```promql
sum(custom_npu_total_used_count{选择器})
```
- 使用 `queryInstant` 查询当前时刻数据

### 5.3 总卡数（历史最大节点数×8）
```promql
max_over_time(count(count by(node)(custom_npu_total_used_count{选择器}))[604800s:1d]) * 8
```
- `count by(node)`：统计各节点是否活跃
- `count(...)`：统计节点总数
- `max_over_time(...[7d:1d])`：取7天内最大节点数
- `* 8`：每节点8卡

### 5.4 历史统计量（用量）
```promql
quantile_over_time(0.5, sum(custom_npu_total_used_count{选择器})[604800s:3600s])  // P50
quantile_over_time(0.9, 相同子查询)  // P90
avg_over_time(相同子查询)            // 平均值
```
- 时间窗口：与总卡数计算窗口一致（最小7天）
- 步长：1小时（3600s），均衡精度与性能

### 5.5 历史统计量（利用率）
```
utilP50 = usedP50 / totalCards
utilP90 = usedP90 / totalCards
utilAvg = usedAvg / totalCards
```
- 基于已算出的用量分位数和总卡数计算

## 6. 与系列查询的差异对比
| 对比项 | 时间序列查询 | 快照查询（本脚本） |
|--------|-------------|-------------------|
| 输出形态 | 时间序列曲线 | 单点数值快照 |
| 查询方法 | `queryRange` | `queryInstant` |
| 历史统计 | 无 | 输出P50/P90/Avg |
| 分组支持 | 支持按维度拆分 | **不分组**，仅汇总 |
| 总卡数计算 | 动态按维度计算 | 全局计算一次 |

## 7. 使用示例
**输入**：`dimension=type`，`value=910,910P`  
**输出示例**：
```json
{
  "totalCards": 256,
  "totalUsed": 112,
  "utilization": 0.4375,
  "usedP50": 98.5,
  "usedP90": 156.2,
  "usedAvg": 105.3,
  "utilP50": 0.3848,
  "utilP90": 0.6102,
  "utilAvg": 0.4113
}
```
