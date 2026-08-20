# Prometheus 历史数据迁移方案

## 一、背景与目标

**现状**：
- 旧Prometheus已停止写入，本地保留30天热数据，标签体系不完整
- 新Prometheus持续写入，具备完整标签体系

**目标**：
- 将旧Prometheus历史数据迁移至VictoriaMetrics/openSearch长期存储
- 迁移过程中完成标签重写，统一新旧数据标签体系
- 迁移后前端查询无需感知数据来源差异

---

## 二、迁移工具选型

采用 **`vmctl`** ——VictoriaMetrics官方命令行迁移工具，支持两种模式：

| 模式 | 适用场景 | 特点 |
|------|---------|------|
| **snapshot模式** | 有Prometheus数据快照 | 直接读取磁盘文件，性能高，适合大规模迁移 |
| **remote-read模式** | 源端支持remote-read API | 通过HTTP拉取数据，无需停止Prometheus，但资源消耗较大 |

**推荐方式**：snapshot模式（旧Prometheus已停写，可直接做快照）

---

## 三、迁移步骤

### Step 1：创建Prometheus数据快照

```bash
curl -XPOST http://<old-prometheus>:9090/api/v1/admin/tsdb/snapshot
```

返回快照路径（如 `/data/snapshots/20260820T120000Z-xxx`），将快照目录拷贝至迁移机器备用。

### Step 2：编写标签重写配置

创建 `relabel.yaml`，在迁移时统一标签：

```yaml
# 映射 project 标签值
- action: replace
  source_labels: [project]
  regex: "旧项目名-C"
  replacement: "新项目名-C"
  target_label: project

# 映射 project 标签值
- action: replace
  source_labels: [project]
  regex: Ascend统一资源池-乌兰察布-A2(910B3)
  replacement: Ascend统一资源池-乌兰察布
  target_label: project

# 补齐缺失标签
- action: replace
  replacement: unknown
  target_label: env

- action: replace
  replacement: unknown
  target_label: region

- action: replace
  replacement: unknown
  target_label: type
```

> vmctl本身不直接支持relabel，需通过`vmagent`作为中间层，或用`vmctl`的`--vm-extra-label`添加标签。若需复杂的值映射，可采用如下两步方案：

### Step 3：执行迁移

**方式一：直接迁移（简单场景）**

```bash
vmctl prometheus \
  --prom-snapshot=/path/to/snapshot \
  --vm-addr=http://<vminsert>:8480/insert/0/prometheus \
  --vm-extra-label account=ascend_infra \
  --vm-extra-label env=legacy \
  --vm-extra-label region=unknown \
  --vm-concurrency=4
```

> `--vm-extra-label`会为所有导入指标添加固定标签，若原指标已有同名标签，将被覆盖。

**方式二：通过vmagent中转（复杂重写场景）**

若需要对特定标签值做条件映射（如 `model_infra` → `ascend_infra`），可部署一个`vmagent`作为中转，在`vmagent`中配置`metric_relabel_configs`执行复杂重写，然后将数据转发至`vminsert`。

### Step 4：验证迁移结果

查询VictoriaMetrics，确认：
- 指标数量是否匹配
- 标签是否已按预期重写
- 时间范围覆盖是否完整

---

## 四、关键参数说明

| 参数 | 说明 | 建议值 |
|------|------|--------|
| `--vm-concurrency` | 并发worker数 | 等于CPU核心数 |
| `--vm-extra-label` | 为所有指标添加固定标签 | 按需设置 |
| `--vm-batch-size` | 批次大小 | 50k-500k，越大性能越好 |
| `-s` | 静默模式，跳过确认 | 自动化脚本使用 |

---

## 五、回退方案

若迁移后需回退，使用 `prom-migrator` 从VictoriaMetrics回迁至Prometheus（或直接保留VictoriaMetrics作为长期存储，新Prometheus继续写入30天热数据，两者共存）。

---

## 六、迁移后的数据流向

```
旧Prometheus (历史数据)  ──vmctl──▶ VictoriaMetrics (冷存储, 1年)
                                              ▲
新Prometheus (30天热数据) ──remote_write─────┘
                                              │
                                         Vue看板统一查询
                                    (≤30d查新Prometheus，>30d查VM)
```

迁移完成后，旧Prometheus可安全下线。
