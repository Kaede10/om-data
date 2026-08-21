# Prometheus 长周期监控方案选型与落地文档

---

## 一、业务背景与约束

### 1. 核心诉求

- 现有自建 Vue 看板 + 统一账号权限体系，**仅维护一套权限**，不新增 Grafana 账号管理
- Prometheus 本地仅保留 **30 天热数据**，需支持 **1 年历史指标查询**
- 面向 NPU 集群监控，兼容 PromQL，复用现有查询逻辑
- 用户体验，一个看板同时支持**实时**和**历史**查询
- 部署环境：华为云，优先云原生、低运维、高性价比方案

### 2. 关键约束

| 约束项 | 说明 |
|--------|------|
| 前端统一 | 自研 Vue 看板，不对外暴露 Grafana |
| 权限统一 | 复用现有账号体系，无多平台权限同步 |
| 数据分层 | 30 天热数据 + 1 年冷数据，长周期查询不卡顿 |
| 华为云环境 | 无官方托管 VictoriaMetrics/Thanos，需基于云服务自建或托管替代 |

### 3. 看板展示粒度

| 时间范围 | 数据粒度 |
|--------|------|
| 近 2 天 | 1 分钟 |
| 近 7 天 | 5 分钟 |
| 近 15 天 | 15 分钟 |
| 近 30 天 | 30 分 |
| 近 90 天 | 2 小时 |
| 近 180 天 | 8 小时 |
| 近 365 天 | 1 天 |


---

## 二、案例参考

| 方案/项目 | 所属/场景 | 硬件支持 | 核心监控架构 | **历史数据存储方案** | 关键特点与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **vLLM CI 看板** | vLLM项目CI | NVIDIA GPU | 自定义数据管道 (Buildkite + 定时任务) | **Databricks SQL Warehouse** (数据仓库) | 将CI和性能数据存储于数据仓库，支持SQL查询，用于长期趋势分析。 |
| **阿里云官方方案** | 阿里云百炼/PAI | NVIDIA GPU / 昇腾NPU | 托管Prometheus + 日志服务SLS | **可观测监控Prometheus版 + SLS** (内置归档存储) | 默认90天存储，超期数据自动转入成本更低的归档存储介质。 |
| **滴滴 HUATUO** | 滴滴出行 | NVIDIA GPU / 昇腾NPU | eBPF + 统一指标框架 | **用户自主选择** (如Thanos, VictoriaMetrics等) | 方案专注于数据采集，存储方案开放，由用户根据需求选择。 |
| **昇腾官方 (MindCluster)** | 华为昇腾 | 昇腾NPU | NPU-Exporter + Prometheus + Grafana | **用户自主选择** (官方推荐VictoriaMetrics等) | 官方提供基础监控方案，长期存储需自行集成Prometheus生态。 |
| **HAMi** | CNCF沙箱项目 | NVIDIA GPU / 昇腾NPU | vGPUmonitor + Prometheus | **用户自主选择** (如Thanos, Cortex等) | 项目自身不提供存储，通过ServiceMonitor无缝融入Prometheus生态。 |
| **SwanLab** | 训练追踪平台 | NVIDIA GPU / 昇腾NPU | Python SDK (gRPC + Protobuf) | **云端自研存储** (关系型DB + 对象存储 + 时序DB) | 自研全链路存储方案，非基于Prometheus生态。 |
| **Databricks** | Databricks平台 | NVIDIA GPU | 托管Prometheus + 数据湖 | **M3/Pantheon (自研) + Unity Catalog (数据湖表)** | 大规模内部使用自研M3/Pantheon；客户指标可存储于数据湖表中。 |

---

## 三、方案总览

### 1. 方案分类

| 类型 | 方案 | 说明 |
|------|------|------|
| 开源长时序方案 | VictoriaMetrics 集群、Thanos + 对象存储 | 自建，灵活可控 |
| 华为云托管方案 | AOM 托管 Prometheus、GeminiDB、CSS | 免运维，但成本较高或有兼容性问题 |
| 混合方案 | Prometheus 热数据 + 远端存储冷数据 | 前端统一查询，存储分层 |

### 2. 核心设计原则

| 原则 | 说明 |
|------|------|
| 存储分层 | 热数据（Prometheus 30d）+ 冷数据（长时序存储 12 个月） |
| 查询兼容 | 100% 兼容 Prometheus API/PromQL，前端无改造 |
| 权限收敛 | 仅自研 Vue 对外提供服务，后端屏蔽存储细节 |
| 长周期优化 | 预聚合 10m/1h 等指标，避免大时间范围查询超时 |

---

## 四、全方案对比表（华为云适配）

| 方案 | 托管属性 | PromQL兼容 | 长周期性能 | 运维量 | 成本 | 华为云适配 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **VM集群 (CCE自建)** | 自建 | 100% | 最优 | **中**：Helm一键部署，组件少，日常维护简单 | **低**：云硬盘+CCE节点费，压缩率高达1/7-1/10 | CCE+云硬盘，Helm一键部署 |
| **Thanos+OBS (CCE自建)** | 自建 | 100% | 优 | **中高**：组件多，配置复杂，需关注上传间隔和Compactor策略 | **低**：OBS存储费+CCE节点费，降采样额外占用30%-50%存储，有API请求费用 | CCE+OBS(兼容S3) |
| **AOM托管Prometheus** | 华为云托管 | 100% | 良 | **极低**：全托管，零运维，无需关心扩缩容/备份/升级 | **较高**：按上报数据量+存储时长计费，长期存储费用较高 | 支持远程写入与API查询 |
| **GeminiDB(for Influx)** | 华为云托管 | **不兼容** | 中 | **极低**：全托管，运维简单 | **较高**：按实例规格+存储空间计费，另有适配层开发改造成本 | 需适配器，改造量大 |
| **CSS OpenSearch** | 华为云托管 | **不兼容** | 差 | **极低**：全托管，运维简单 | **中**：按节点规格+存储空间计费，时序场景性价比低 | 日志为主，时序不推荐 |
---

## 五、推荐方案

### 方案一：Prometheus + VictoriaMetrics 集群（首选）

#### 1. 架构

```
采集层：dcgm-exporter / ascend-exporter
    ↓
Prometheus（30d 热数据）
    ↓ remote_write
vminsert（写入网关）
    ↓
vmstorage × 3（SSD 云硬盘，retention=12 个月）
    ↑
vmselect × 2（查询网关，兼容 Prometheus API）
    ↑
Vue 看板（按时间路由：≤30d → Prometheus；＞30d → vmselect）
```

#### 2. 华为云部署

| 组件 | 规格 | 存储 |
|------|------|------|
| vminsert × 2 | 2C 4G | - |
| vmstorage × 3 | 4C 16G | SSD 云硬盘 500Gi+ |
| vmselect × 2 | 2C 8G | - |
| 平台 | 华为云 CCE 集群 | - |
| 部署方式 | 官方 Helm Chart 一键安装 | - |

#### 3. 核心配置

```yaml
# Prometheus remote_write
remote_write:
  - url: "http://vm-cluster-vminsert.monitoring.svc.cluster.local:8480/api/v1/write"

# vmstorage 保留 12 个月
-retentionPeriod=12
```

---

### 方案二：Prometheus + Thanos + OBS（备选）

#### 1. 架构

```
Prometheus（30d）
    ↓ remote_write
thanos-receiver
    ↓
华为云 OBS（1 年冷数据）
    ↑
thanos-query（自动合并冷热数据，单查询入口）
    ↑
Vue 看板（无需时间路由）
```

#### 2. 华为云适配

| 组件 | 说明 |
|------|------|
| 对象存储 | 华为云 OBS（兼容 S3 协议，需开启 S3 兼容模式并支持 v4 签名） |
| 组件清单 | thanos-receiver、store-gateway、query、compactor |
| 优势 | 单查询入口，后端无改造 |

---

### 方案三：AOM 托管 Prometheus（零运维备选）

#### 1. 架构

```
自建 Prometheus
    ↓ remote_write
AOM 托管实例（保留 1 年）
    ↑
Vue 看板调用 AOM 查询 API（兼容 PromQL）
```

#### 2. 适用场景

- 无运维人力，完全托管
- 指标量中等，成本可接受
- **需提前评估指标量**（如 100 张卡 × 约 50 个指标/卡 × 活跃时间序列），AOM 按指标条数 × 时长计费

---

好的，我将修正后的方案整合到你提供的文档中，替换原有"六、历史数据迁移方案"部分，保持文档格式风格一致：

---

## 六、历史数据迁移方案

### 1. 背景与目标

**现状**：

- 旧 Prometheus 已停止写入，本地保留 30 天热数据，标签体系不完整
- 新 Prometheus 持续写入，具备完整标签体系

**目标**：

- 将旧 Prometheus 历史数据迁移至 VictoriaMetrics 长期存储
- 迁移过程中完成标签重写，统一新旧数据标签体系
- 迁移后前端查询无需感知数据来源差异

---

### 2. 迁移工具选型与架构

采用 **`vmctl`** 导出历史数据 + **VictoriaMetrics 导入接口** 完成标签重写，**不使用 `vmagent` 处理历史数据**。

| 工具/组件 | 作用 | 说明 |
|-----------|------|------|
| **`vmctl vm-native`** | 数据导出 | 读取 Prometheus 快照或 Remote Read 数据，导出为 Native 格式文件 |
| **VictoriaMetrics `/api/v1/import/native`** | 数据导入 + 标签重写 | 在写入时通过 `relabel_config` 参数完成标签转换 |
| **`vmagent`** | 新数据实时采集 | 仅用于未来持续采集，不参与历史数据迁移 |

**数据流向**：

```
旧 Prometheus 快照
    ↓
vmctl 导出为 Native 格式文件（按 project 分批）
    ↓
curl 调用 VM 导入接口 + relabel_config 参数
    ↓
VictoriaMetrics（历史数据 + 转换后数据）
```

**架构对比说明**：

| 方案 | 是否可行 | 原因 |
|------|----------|------|
| ❌ vmagent 处理历史数据 | **不可行** | vmagent 会强制替换时间戳为当前时间，历史数据时间错乱；且 vmagent 是拉取模型，不设计为处理本地文件 |
| ✅ vmctl + VM 导入接口 | **可行** | 导入接口支持 `relabel_config` 参数，且完整保留原始时间戳 |

---

### 3. 分批迁移策略

由于不同 `project` 的标签值不同，逐批迁移更安全可控。

**推荐方式**：按 `project` 分批次迁移，每次迁移一个 project。

| 批次 | project | region | type | 说明 |
|------|---------|--------|------|------|
| 第 1 批 | `Ascend统一资源池-乌兰察布-A2(910B3)` | 乌兰察布 | 910B3 | 先迁移一个 project 验证流程 |
| 第 2 批 | `Ascend统一资源池-北京-A2(910B1)` | 北京 | 910B1 | 验证通过后再迁移后续 |
| 第 N 批 | ... | ... | ... | 逐批迁移直至全部完成 |

**分批迁移优势**：

| 优势 | 说明 |
|------|------|
| **风险可控** | 一次只迁移一个 project，出问题影响范围小 |
| **易于验证** | 可逐一验证每个 project 的迁移结果 |
| **支持回退** | 单个 project 迁移异常可快速重试，不影响其他数据 |
| **资源友好** | 每次处理的数据量可控，避免内存溢出 |

---

### 4. 迁移步骤

#### Step 1：创建 Prometheus 数据快照

```bash
curl -XPOST http://<old-prometheus>:9090/api/v1/admin/tsdb/snapshot
```

返回快照路径（如 `/data/snapshots/20260820T120000Z-xxx`），将快照目录拷贝至迁移机器备用。

#### Step 2：使用 `vmctl` 按 project 导出历史数据

```bash
./vmctl vm-native \
  --vm-native-src-addr=http://<old-prometheus>:9090 \
  --vm-native-filter-match='{project="Ascend统一资源池-乌兰察布-A2(910B3)"}' \
  --vm-native-filter-time-start='2024-01-01T00:00:00Z' \
  --vm-native-filter-time-end='2024-12-31T23:59:59Z' \
  --vm-native-step-interval=day \
  --vm-native-dst-file=/data/ulanqab_910B3.native
```

> **注意**：每次只导出一个 project 的数据，`--vm-native-dst-file` 指定为本地文件，便于后续导入时进行标签转换。

#### Step 3：通过 VictoriaMetrics 导入接口写入并完成标签重写

将导出的 Native 格式文件，通过 `curl` 调用 VM 导入接口，在请求中附加 `relabel_config` 参数完成标签转换。

```bash
curl -X POST http://<vminsert-addr>:8480/insert/0/prometheus/api/v1/import/native \
  -H "Content-Type: application/x-protobuf" \
  --data-binary @/data/ulanqab_910B3.native \
  -d 'relabel_config=
  # 只保留指定 project 的数据
  - source_labels: [project]
    regex: "Ascend统一资源池-乌兰察布-A2\\(910B3\\)"
    action: keep

  # 从 project 提取 region（$1=乌兰察布）
  - action: replace
    replacement: "乌兰察布"
    target_label: region

  # 从 project 提取 type（$2=910B3）
  - action: replace
    replacement: "A2"
    target_label: type

  # 添加固定标签
  - action: replace
    replacement: "cloud"
    target_label: env

  - action: replace
    replacement: "ascend_infra"
    target_label: account

  # 生成总卡数指标：复制原指标生成 custom_npu_total
  - source_labels: [__name__]
    regex: "custom_npu_total_used_count"
    target_label: __name__
    replacement: "custom_npu_total"
    action: copy

  # 修改新指标的值 = node_total_npu 标签的值
  - if: "{__name__=\"custom_npu_total\"}"
    source_labels: [node_total_npu]
    target_label: __value__
    replacement: "{{node_total_npu}}"
    action: replace
  '
```

> **关键说明**：
> - `action: keep` 确保只处理当前批次 project 的数据
> - `action: copy` 复制原指标，保留原指标的同时生成新指标
> - `if` 条件过滤确保只修改新生成的指标
> - `{{node_total_npu}}` 是 VictoriaMetrics 扩展语法，在 relabel 中引用标签值
> - `__value__` 是特殊标签，代表指标样本值

#### Step 4：验证迁移结果

**验证项**：

| 验证点 | 查询语句 | 预期结果 |
|--------|----------|----------|
| 原指标是否存在 | `count(custom_npu_total_used_count{project="Ascend统一资源池-乌兰察布-A2(910B3)"})` | > 0 |
| 新指标是否存在 | `count(custom_npu_total{project="Ascend统一资源池-乌兰察布-A2(910B3)"})` | > 0 |
| 新指标值是否正确 | `custom_npu_total == node_total_npu` | 恒等式成立 |
| region 标签是否正确 | `custom_npu_total_used_count{region="乌兰察布"}` | 有数据返回 |
| type 标签是否正确 | `custom_npu_total_used_count{type="910B3"}` | 有数据返回 |
| 固定标签是否正确 | `env="cloud"` 且 `account="ascend_infra"` | 所有指标包含 |
| 时间范围是否完整 | `min(custom_npu_total_used_count)` 和 `max()` | 覆盖预期时间区间 |

#### Step 5：逐批迁移所有 project

重复 Step 2-4，逐批迁移所有 project。建议按以下流程操作：

```
第 1 批: 导出 project A → 导入 → 验证 → 确认
第 2 批: 导出 project B → 导入 → 验证 → 确认
第 N 批: ... 重复直至全部完成
```

---

### 5. 参数说明

| 参数 | 说明 | 建议值 |
|------|------|--------|
| `--vm-native-step-interval` | 数据采样间隔 | `day`（按天分片，避免内存溢出） |
| `--vm-concurrency` | 并发 worker 数 | 等于 CPU 核心数 |
| `--vm-native-filter-time-start/end` | 时间范围过滤 | 按需设置，建议按月分批 |
| `relabel_config` 中的 `replacement: "{{...}}"` | VictoriaMetrics 扩展语法 | 用于在 relabel 中引用标签值 |
| `action: keep` | 只保留匹配的指标 | 确保每次只处理一个 project |

---

### 6. 新旧数据写入路径总结

| 数据类型 | 写入路径 | 转换方式 |
|----------|----------|----------|
| **历史数据** | `vmctl` 导出 → `curl` 导入 VM（携带 `relabel_config`） | 导入接口的 `relabel_config` 参数 |
| **新数据** | `vmagent` 实时采集 → `vminsert` | `metric_relabel_configs` |

两条路径使用**相同的 relabel 规则**，确保新旧数据在 VM 中的标签和指标定义完全一致。

---

### 7. 回退方案

若迁移后需回退，使用 **`prom-migrator`** 工具从 VictoriaMetrics 回迁至 Prometheus，该工具支持：

- 进度断点续传（通过 `prom_migrator_progress` 指标记录迁移进度）
- 异常中断后自动恢复

**回退操作**：

```bash
./prom-migrator \
  --source=vm:http://<vmselect-addr>:8481 \
  --dest=prometheus:http://<new-prometheus>:9090 \
  --time-start=2024-01-01T00:00:00Z \
  --time-end=2024-12-31T23:59:59Z
```

---

### 8. 迁移前后标签对比示例

| 迁移前（旧 Prometheus） | 迁移后（VictoriaMetrics） |
|------------------------|--------------------------|
| `custom_npu_total_used_count{project="Ascend统一资源池-乌兰察布-A2(910B3)", node_total_npu="8"}` | `custom_npu_total_used_count{project="Ascend统一资源池-乌兰察布-A2(910B3)", region="乌兰察布", type="910B3", env="cloud", account="ascend_infra", node_total_npu="8"}` |
| 值: 85.5 | 值: 85.5（原指标保留） |
| — | `custom_npu_total{project="Ascend统一资源池-乌兰察布-A2(910B3)", region="乌兰察布", type="910B3", env="cloud", account="ascend_infra", node_total_npu="8"}` |
| — | 值: 8（新指标值 = 卡数） |

---

已将修正后的方案整合进你的文档，核心改动点：

1. **移除 vmagent 处理历史数据的方式**，改用 vmctl 导出 + VM 导入接口
2. **明确分批迁移策略**，按 project 逐批迁移
3. **完整的 relabel 配置**，包含 from project 解析 region/type、固定标签、生成总卡数指标
4. **区分新旧数据写入路径**，历史数据用导入接口，新数据用 vmagent
5. **补充迁移前后标签对比示例**，便于理解转换效果

---

## 七、新旧数据标签不一致处理方案

### 1. 数据差异说明

基于真实数据样例：

| 维度 | 旧数据（已停写） | 新数据（持续写入） | 处理策略 |
|------|------------------|-------------------|----------|
| **指标名** | `custom_npu_total_used_count` | `custom_npu_total_used_count` + `custom_npu_total` | ✅ 一致，使用卡数直接合并 |
| **总卡数** | ❌ 无独立指标，从标签 `node_total_npu="8"` 提取 | ✅ 独立指标 `custom_npu_total=8` | 旧数据从标签提取，新数据查独立指标 |
| **标签差异** | 缺少 `env`、`region`、`type` | 完整标签 | 旧数据填充默认值 |
| **标签值差异** | `"Ascend统一资源池-乌兰察布-A2(910B3)"` | `"Ascend统一资源池-A2"` | 迁移时映射 |

### 2. 处理方案

#### 方案 A：迁移时重写（推荐）

在迁移过程中，通过 vmagent 的 `metric_relabel_configs` 完成：
1. **标签统一映射**：如 `model_infra` → `ascend_infra`，多 `project` 值逐条映射
2. **补齐缺失标签**：为所有旧数据添加 `env=legacy`、`region=unknown`、`type=unknown`
3. **生成总卡数指标**：通过 Recording Rule 或自定义脚本生成 `custom_npu_total`

#### 方案 B：查询层适配（备选）

若迁移时未做重写，在 Vue 后端查询时适配

---

## 八、前端与权限设计

### 1. 统一前端

- 仅开放自研 Vue 看板，Grafana 仅运维内部使用
- 时间范围自动路由：≤30d 查本地 Prometheus，＞30d 查 VictoriaMetrics
- 历史数据提示：＞30d 为聚合粒度曲线，无秒级细节
- 跨边界查询自动合并，前端无感知

### 2. 统一权限

- 权限控制在 Vue 后端，后端代理查询请求
- 长时序存储仅内网暴露，不对外提供入口
- 无多平台权限同步，一套体系管控全链路

---

## 九、方案选型决策树

1. **VictoriaMetrics 集群（首选）**
2. 希望单查询入口、无后端改造 → **Thanos + OBS**
3. 零运维 → **AOM 托管 Prometheus**
4. 需指标日志统一检索 → **OpenSearch**

---

## 十、总结

| 维度 | 说明 |
|------|------|
| **推荐** | 华为云 CCE 自建 VictoriaMetrics 集群 |
| **核心优势** | PromQL 100% 兼容、存储分层、长周期不卡顿、权限收敛、云原生易运维 |
| **落地标准** | Prometheus 30d 热数据 + VM 1 年冷数据 + Vue 前端统一入口 + 预聚合优化 |
| **迁移策略** | 通过 vmctl + vmagent 完成历史数据迁移，迁移时同步完成标签重写 |
| **数据统一** | 迁移时统一新旧数据标签体系，前端查询无需感知数据来源差异 |

---
