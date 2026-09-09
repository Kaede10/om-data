### 🔧 实现路径与对比

| 实现方式 | 适用场景 | 实现难度 | 关键动作 |
| :--- | :--- | :--- | :--- |
| **方式一：在 Pod 模板的 YAML 中预置（推荐）** | 使用预定义的 K8s YAML 文件通过 `kubectl` 启动任务 | 低 | 在 YAML 模板中使用变量占位符，部署前用 `envsubst` 等工具替换为 GitHub Actions 的 `run_id` |
| **方式二：使用 `kubectl` 命令动态打标** | 通过脚本直接调用 `kubectl` 创建或修改 Pod | 中 | 使用 `kubectl label pod <pod-name> task-id=<value>` 命令为运行中的 Pod 动态添加标签 |
| **方式三：借助 Actions Runner Controller (ARC) 的自定义钩子** | 使用 ARC 管理自托管 Runner | 高 | 利用 Runner Pod 的扩展机制，在创建任务 Pod 时自动注入自定义标签 |
| **方式四：由任务调度器（如 Volcano）自动注入** | 使用 Volcano 等调度器管理 NPU 任务 | 视调度器而定 | 由调度器根据任务配置自动将特定 ID 注入到 Pod 标签中（例如注入 `inferserviceid`） |

### 💡 核心逻辑：打通 GitHub Actions 与 Kubernetes

不论选择哪种方式，核心逻辑都是**将 GitHub Actions 中唯一的 `run_id` 或自定义的任务 ID，作为环境变量传递出来，并写入到 Pod 的标签中**。

以下是一个简化的流程示例：

1.  **在 GitHub Actions Workflow 中获取 ID**：
    ```yaml
    - name: 获取任务ID
      run: echo "TASK_ID=workflow-${{ github.run_id }}" >> $GITHUB_ENV
    ```

2.  **在 Kubernetes Pod 模板中使用该变量**：
    最直接的方法是使用 `envsubst` 这类工具。比如，你的 `pod-template.yaml` 文件内容如下：
    ```yaml
    apiVersion: v1
    kind: Pod
    metadata:
      name: my-npu-task
      labels:
        task-id: ${TASK_ID}  # 这里是一个占位符
    spec:
      containers:
      - name: main
        image: my-npu-image
    ```

3.  **部署时替换变量并应用**：
    在你的 Workflow 脚本中，用 `envsubst` 替换变量后，再通过 `kubectl` 应用：
    ```bash
    # 利用 envsubst 命令替换文件中的环境变量，然后通过管道传递给 kubectl 创建
    envsubst < pod-template.yaml | kubectl apply -f -
    ```

---

### 🔗 将 Pod 标签写入指标：Prometheus Relabel 配置

这是将 `task-id` 从 Pod 元数据转移到监控指标的关键步骤。你需要修改 Prometheus 的采集配置，在 `relabel_configs` 中添加规则。

**配置示例 (`prometheus.yml` 片段)**

```yaml
scrape_configs:
  - job_name: 'npu-exporter'
    kubernetes_sd_configs:
      - role: pod  # 关键：让 Prometheus 从 Kubernetes API 发现 Pod
    relabel_configs:
      # 1. (可选) 筛选：只采集携带了 task-id 标签的 Pod
      - source_labels: [__meta_kubernetes_pod_label_task_id]
        regex: '.+'
        action: keep

      # 2. 核心：将 Pod 标签 task-id 的值，写入到指标的 task_id 标签中
      - source_labels: [__meta_kubernetes_pod_label_task_id]
        target_label: task_id
        action: replace

      # 3. (可选) 保留其他重要元数据作为标签，便于后续查询
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod_name
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_node_name]
        target_label: node
```

**配置解读**

| 配置项 | 说明 |
| :--- | :--- |
| `kubernetes_sd_configs` | 告诉 Prometheus 使用 Kubernetes 的服务发现机制，发现集群中的 Pod。 |
| `role: pod` | 指定发现的角色是 Pod，这样 Prometheus 就能获取到 Pod 的所有元数据。 |
| `__meta_kubernetes_pod_label_task_id` | Prometheus 发现 Pod 后自动生成的内部变量，存放着 Pod 标签 `task-id` 的值。 |
| `action: keep` | 只保留那些 `__meta_kubernetes_pod_label_task_id` 有值的 Pod，过滤掉没有此标签的 Pod。 |
| `target_label: task_id` | 指定生成的新标签名为 `task_id`。 |

### ✅ 验证与使用

配置完成后，当 Prometheus 重新加载配置后，所有来自该 Pod 的 `npu-exporter` 指标（如 `npu_chip_info_utilization`）都会自动带上 `task_id` 标签。

你可以通过 Prometheus 的 Graph 界面查询验证：
```promql
npu_chip_info_utilization{task_id="workflow-1234567890"}
```
