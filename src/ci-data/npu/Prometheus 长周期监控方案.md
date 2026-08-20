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

> **大规模生产环境均采用双存储/双看板分离架构**
>  **长周期查询必须使用预聚合指标**（5m/1h），禁止原始指标直接查 30 天以上数据
> **VictoriaMetrics 与 Thanos 是两大主流方案**

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
| 双看板分离 | 实时看板仅查 3~7 天内数据，长周期看板仅用预聚合指标 |

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

## 六、历史数据迁移方案

### 1. 背景与目标

**现状**：

- 旧 Prometheus 已停止写入，本地保留 30 天热数据，标签体系不完整
- 新 Prometheus 持续写入，具备完整标签体系

**目标**：

- 将旧 Prometheus 历史数据迁移至 VictoriaMetrics 长期存储
- 迁移过程中完成标签重写，统一新旧数据标签体系
- 迁移后前端查询无需感知数据来源差异

### 2. 迁移工具选型

采用 **`vmctl`** ——VictoriaMetrics 官方命令行迁移工具：

| 模式 | 适用场景 | 特点 |
|------|----------|------|
| **snapshot 模式** | 有 Prometheus 数据快照 | 直接读取磁盘文件，性能高，适合大规模迁移 |
| **remote-read 模式** | 源端支持 remote-read API | 通过 HTTP 拉取数据，无需停止 Prometheus |

**推荐方式**：snapshot 模式（旧 Prometheus 已停写，可直接做快照）

### 3. 迁移步骤

#### Step 1：创建 Prometheus 数据快照

```bash
curl -XPOST http://<old-prometheus>:9090/api/v1/admin/tsdb/snapshot
```

返回快照路径（如 `/data/snapshots/20260820T120000Z-xxx`），将快照目录拷贝至迁移机器备用。

#### Step 2：编写标签重写配置

创建 `vmagent` 的 `metric_relabel_configs` 配置，在迁移时统一标签：

```yaml
metric_relabel_configs:
  # 统一 project 标签值（多值映射）
  - source_labels: [project]
    regex: "vLLM-贵阳-A3"
    replacement: "Ascend统一资源池-乌兰察布-A2(910B3)"
    target_label: project

  - source_labels: [project]
    regex: "旧项目名-B"
    replacement: "新项目名-B"
    target_label: project

  # 补齐缺失标签
  - action: replace
    replacement: legacy
    target_label: env

  - action: replace
    replacement: unknown
    target_label: region

  - action: replace
    replacement: unknown
    target_label: type

  # 若需生成总卡数指标，复制指标并修改名称
  # 注意：需结合 vmagent 的 relabel 特性或使用外部脚本实现
  - source_labels: [__name__, node_total_npu]
    regex: "custom_npu_total_used_count;(.+)"
    action: replace
    target_label: __name__
    replacement: "custom_npu_total"
```

> **注意**：将标签值（`node_total_npu`）赋值给指标值的操作在标准 relabel 中较复杂，推荐方案为：
> 1. **优先方案**：迁移完成后，在 VictoriaMetrics 中通过 **Recording Rule** 生成 `custom_npu_total` 指标
> 2. **备选方案**：编写自定义数据处理脚本，在写入 vmagent 前完成数据重构

#### Step 3：执行迁移

**推荐方式：通过 vmagent 中转（支持复杂重写）**

```
旧 Prometheus 快照
    ↓
vmagent（执行 metric_relabel_configs 重写）
    ↓
vminsert
    ↓
VictoriaMetrics（冷存储）
```

**vmagent 启动命令示例**：

```bash
vmagent -remoteWrite.url=http://<vminsert>:8480/insert/0/prometheus \
        -promscrape.config=/path/to/scrape_config.yaml \
        -remoteWrite.relabelConfig=/path/to/relabel.yaml
```

**直接迁移方式（简单场景）**：

```bash
vmctl prometheus \
  --prom-snapshot=/path/to/snapshot \
  --vm-addr=http://<vminsert>:8480/insert/0/prometheus \
  --vm-extra-label account=ascend_infra \
  --vm-extra-label env=legacy \
  --vm-concurrency=4
```

#### Step 4：验证迁移结果

- 指标数量是否匹配
- 标签是否已按预期重写
- 时间范围覆盖是否完整
- 总卡数指标是否已正确生成

### 4. 关键参数说明

| 参数 | 说明 | 建议值 |
|------|------|--------|
| `--vm-concurrency` | 并发 worker 数 | 等于 CPU 核心数 |
| `--vm-extra-label` | 为所有指标添加固定标签 | 按需设置 |
| `--vm-batch-size` | 批次大小 | 50k-500k |
| `--remote-read-step-interval` | remote-read 模式分片间隔 | day（按天分片） |

### 5. 回退方案

若迁移后需回退，使用 **`prom-migrator`** 工具从 VictoriaMetrics 回迁至 Prometheus，该工具支持：
- 进度断点续传（通过 `prom_migrator_progress` 指标记录迁移进度）
- 异常中断后自动恢复

### 6. 迁移后的数据流向

```
旧 Prometheus（历史数据）──vmctl/vmagent──▶ VictoriaMetrics（冷存储, 1年）
                                               ▲
新 Prometheus（30d 热数据）──remote_write─────┘
                                               │
                                          Vue 看板统一查询
                                   (≤30d 查新 Prometheus，>30d 查 VM)
```

迁移完成后，旧 Prometheus 可安全下线。

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
