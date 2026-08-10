# NPU监控指标数据结构文档

---

## 核心概念说明

### 标签语义定义

| 标签 | 含义 | 聚合主键 | 说明 |
|------|------|----------|------|
| `cluster` | 集群名称（物理标识） | ❌ 否 | 集群的物理/基础设施标识，**不作为聚合维度** |
| `project` | 集群名称（逻辑标识） | ✅ **是** | **监控聚合查询时使用的集群标识**，代表一个逻辑集群 |
| `community` | 节点归属社区 | ✅ **是** | 表示NPU节点物理上属于哪个社区 |

### 聚合查询规则
- **所有监控面板、报表、告警的聚合查询，均使用 `project` 标签作为集群维度**
- `cluster` 仅作为辅助标签用于定位具体的物理集群，不参与业务聚合
- `community` 用于标识资源归属方

---

## 1. 现有指标：`custom_npu_total_used_count`

### 1.1 指标说明
- **类型**：Gauge（仪表盘类型）
- **含义**：当前正在使用的NPU卡数
- **上报频率**：常规采集间隔周期性上报，实时反映当前使用量

### 1.2 标签说明

| 标签名 | 说明 | 示例值 |
|--------|------|--------|
| `cluster` | 物理集群名称 | `ascend-hk-001-cluster` |
| `community` | **节点所属社区（固定归属）**<br/>表示该NPU节点物理上属于哪个社区，不随使用方改变 | `mindstudio` |
| `account` | 云账号（部分数据源有） | `ascend_infra` |
| `env` | 资源类型（部分数据源有） | `cloud` |
| `type` | NPU设备型号（部分数据源有） | `910B3` |
| `instance` | 采集实例地址 | `npu-exporter-hk-001.npu-exporter:9101` |
| `job` | 采集任务名 | `ascend-hk-001-cluster` |
| `node` | 节点名称 | `os-node-created-2dq9v` |
| `node_total_npu` | 节点总卡数 | `8` |
| `pod_name` | Pod名称（部分场景） | `linux-aarch64-a2b3-1-m8kx4-runner` |
| `pod_npu_used` | Pod使用卡数（部分场景） | `1` |
| `pr` | PR或工作流标识（部分场景） | `vllm-project/vllm-ascend/.github/workflows/_selected_tests_upstream.yaml@refs/pull/13069/merge` |
| `project` | **集群标识**<br/>监控聚合查询时使用的集群标识 | `参与开源统一资源池-香港-A2(910B3)` |
| `base_type` | NPU设备基础型号 | `910B` |
| `region` | 地域（部分数据源有） | `香港` |
| `domain` | 领域（部分数据源有） | `昇腾` |

**重要关系**：
- `node` 与 `community` 的绑定关系是**固定的**，一个节点始终属于一个 `community`
- 当某个社区（如MindStudio）的节点被其他社区（如vllm）的项目使用时，`community` 标签仍为 `mindstudio`

### 1.3 数据示例
```json
{
  "metric": {
    "__name__": "custom_npu_total_used_count",
    "cluster": "ascend-hk-001-cluster",
    "community": "mindstudio",
    "instance": "npu-exporter-hk-001.npu-exporter:9101",
    "job": "ascend-hk-001-cluster",
    "node": "os-node-created-2dq9v",
    "node_total_npu": "8",
    "pod_name": "linux-aarch64-a2b3-1-m8kx4-runner-jhxkx-workflow",
    "pod_npu_used": "1",
    "pr": "vllm-project/vllm-ascend/.github/workflows/_selected_tests_upstream.yaml@refs/pull/13069/merge",
    "project": "参与开源统一资源池-香港-A2(910B3)",
    "base_type": "910B",
    "region": "香港",
    "domain": "昇腾"
  },
  "value": [
    1786351551.389,
    "1"
  ]
}
```

---

## 2. 新增指标：`custom_npu_total_count`

### 2.1 指标说明
- **类型**：Gauge（仪表盘类型）
- **含义**：当前可用的NPU总卡数
- **上报频率**：和custom_npu_total_used_count同频上报，时间戳一致

### 2.2 标签说明

| 标签名 | 说明 | 示例值 |
|--------|------|--------|
| `cluster` | 物理集群名称 | `ascend-hk-001-cluster` |
| `community` | **节点所属社区/项目组（固定归属）** | `mindstudio` |
| `account` | 云账号 | `ascend_infra` |
| `env` | 资源类型 | `cloud` |
| `type` | NPU设备型号 | `910B3` |
| `instance` | 采集实例地址 | `123.60.161.138:9004` |
| `job` | 采集任务名 | `liteserver-for-mindstudio-4` |
| `node` | 节点名称 | `liteserver-for-mindstudio-4` |
| `node_total_npu` | 节点总卡数 | `8` |
| `project` | **集群标识**<br/>监控聚合查询时使用的集群标识 | `参与开源统一资源池-香港-A2(910B3)` |
| `base_type` | NPU设备基础型号 | `910B` |
| `region` | 地域（部分数据源有） | `香港` |
| `domain` | 领域（部分数据源有） | `昇腾` |

**与 `custom_npu_total_used_count` 的标签差异**：
- 该指标**不包含** `pod_name`、`pod_npu_used`、`pr` 等动态标签
- 保持与 `custom_npu_total_used_count` 一致的维度键：`cluster`、`community`、`account`、`env`、`type`、`instance`、`job`、`node`、`node_total_npu`、`project`

### 2.3 数据示例
```json
{
  "metric": {
    "__name__": "custom_npu_total_count",
    "cluster": "ascend-hk-001-cluster",
    "community": "mindstudio",
    "account": "ascend_infra",
    "env": "cloud",
    "type": "910B3",
    "instance": "123.60.161.138:9004",
    "job": "liteserver-for-mindstudio-4",
    "node": "liteserver-for-mindstudio-4",
    "node_total_npu": "8",
    "project": "参与开源统一资源池-香港-A2(910B3)",
    "base_type": "910B",
    "region": "香港",
    "domain": "昇腾"
  },
  "value": [
    1786351551.389,
    "8"
  ]
}
```

---

## 3. 指标使用

### 3.1 利用率计算

**⚠️ 重要**：由于 `custom_npu_total_used_count` 按 Pod 维度拆分（同一节点可能有多条时间序列），而 `custom_npu_total_count` 按节点维度只有一条时间序列，因此**计算利用率时必须先按维度聚合，再做除法**，否则会出现向量匹配错误。

**正确用法**：

```promql
# 按 community 聚合的实时利用率
sum by(community)(custom_npu_total_used_count) 
/ 
sum by(community)(custom_npu_total_count)
```

```promql
# 按 project 聚合的实时利用率
sum by(project)(custom_npu_total_used_count) 
/ 
sum by(project)(custom_npu_total_count)
```

```promql
# 按 node 聚合的实时利用率（节点级别）
sum by(node)(custom_npu_total_used_count) 
/ 
sum by(node)(custom_npu_total_count)
```

通过聚合后的当前值可直接计算出实时利用率，历史利用率可通过 `quantile_over_time` 和 `avg_over_time` 计算。

### 3.2 历史统计查询

**场景一：计算历史各时间点的利用率，再求 P50**

```promql
# 先算每个时间点的利用率，再对时间窗口求 P50
quantile_over_time(0.5, 
  (
    sum by(community)(custom_npu_total_used_count) 
    / 
    sum by(community)(custom_npu_total_count)
  )[7d:1h]
)
```

**场景二：计算历史使用量的 P50，除以当前总容量**

```promql
# 使用量的 P50 / 总容量（适用于容量规划场景）
quantile_over_time(0.5, sum by(community)(custom_npu_total_used_count)[7d:1h])
/
sum by(community)(custom_npu_total_count)
```

**场景三：按 project + community 双维度统计**

```promql
# 按 project 和 community 双维度聚合的实时利用率
sum by(project, community)(custom_npu_total_used_count) 
/ 
sum by(project, community)(custom_npu_total_count)
```

### 3.3 标签一致性注意事项

- `custom_npu_total_count` 应和 `custom_npu_total_used_count` 同频上报
- 查询时建议使用相同的筛选条件（如相同的 `project`、`cluster` 等）进行关联计算
- 由于 `community` 是固定标签，在节点归属不变的情况下，`custom_npu_total_count` 中的 `community` 值应与 `custom_npu_total_used_count` 保持一致
- **特别注意**：`custom_npu_total_used_count` 存在 `pod_name`、`pod_npu_used`、`pr` 等动态标签，这些标签不在 `custom_npu_total_count` 中。进行除法运算前，务必使用 `sum by(...)` 或 `sum without(...)` 去除这些不匹配的标签，确保两组时间序列的标签集一致
