# Data Prepper 部署（K8s：Prometheus → OpenSearch HTTPS）

## 1. 总体拓扑

```
Prometheus(k8s) ───(push: remote_write)───> data-prepper(k8s Deployment) ────https(CA证书) + 密钥───> OpenSearch
```

- Prometheus 与 data-prepper 同在 Kubernetes。
- OpenSearch 为 HTTPS 端点，提供 CA 证书（`.cer`），data-prepper 通过 `ca_cert` 校验而非 `insecure`。

## 2. 版本选型（重要）

| 方案 | 版本 | 说明 |
| --- | --- | --- |
| **Push（推荐）** | **2.15.1** | Prometheus 已部署，只加 `remote_write`；自带 relabel 过滤，能拿到 `up`；生产环境需要多个实例 |
| Pull（备选） | 2.16.0 | data-prepper 直接抓 exporter，自行过滤、无 `up` |

> ⚠️ **不要用 2.16.0 的 push 路径**：存在 bug，remote_write 返回 HTTP 500
> `NoSuchMethodError: Remote$WriteRequest.makeExtensionsImmutable()`。push 方案固定 2.15.1。

## 3. 证书准备

将 OpenSearch 的 CA 证书转成 PEM 并放入 ConfigMap：
```bash
# .cer 若是 DER 编码需先转换（PEM 编码可直接用）
openssl x509 -inform der -in ca.cer -out ca.pem
cat ca.pem   # 应为 -----BEGIN CERTIFICATE----- 开头
```
> ⚠️ **不使用证书**：证书中只有内网IP，没有公网IP，hostname 验证不通过

## 4. 清单与 YAML（以命名空间 monitoring 为例）

```
monitoring/
├── data-prepper-cm.yaml          # ConfigMap：pipelines.yaml + data-prepper-config.yaml + ca.pem
├── data-prepper-secret.yaml      # Secret：OpenSearch 用户名密码
├── data-prepper-deploy.yaml      # Deployment + Service
└── prometheus-remote-write.yaml  # Prometheus 侧 remote_write 配置
```

### 4.1 ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: data-prepper
  namespace: monitoring
data:
  data-prepper-config.yaml: |
    ssl: false
    experimental:
      enabled_plugins:
        source:
          - prometheus

  # ---- 方案 A（推荐）：Push，image 用 2.15.1 ----
  pipelines.yaml: |
    node-metrics-pipeline:
      source:
        prometheus:
          # 2.15.1 默认监听 :9090，路径 /api/v1/write
      sink:
        - opensearch:
            hosts: ["https://opensearch.monitoring.svc.cluster.local:9200"]  # 或 https://公网域名:9200
            username: "${OPENSEARCH_USERNAME}"
            password: "${OPENSEARCH_PASSWORD}"
            ca_cert: "/usr/share/data-prepper/tls/ca.pem"
            index: "custom_node_npu_log"
            index_type: custom

  # ---- 方案 B（备选）：Pull，image 用 2.16.0，替换上方 pipelines.yaml ----
  # pipelines.yaml: |
  #   node-metrics-pipeline:
  #     source:
  #       prometheus:
  #         scrape:
  #           targets:
  #             - url: "http://node-exporter.monitoring.svc.cluster.local:9100/metrics"
  #           scrape_interval: 15s
  #           scrape_timeout: 10s
  #           insecure: true
  #     processor:
  #       - drop_events:
  #           drop_when: '/name != "node_lite_load1" and /name != "node_lite_cpu_usage_ratio"'
  #           handle_failed_events: drop
  #     sink:
  #       - opensearch:
  #           hosts: ["https://opensearch.monitoring.svc.cluster.local:9200"]
  #           username: "${OPENSEARCH_USERNAME}"
  #           password: "${OPENSEARCH_PASSWORD}"
  #           ca_cert: "/usr/share/data-prepper/tls/ca.pem"
  #           index: "custom_node_npu_log"
  #           index_type: custom

  # ca.pem: |
  #   -----BEGIN CERTIFICATE-----
  #   <在这里粘贴 OpenSearch 的 CA 证书内容>
  #   -----END CERTIFICATE-----
```

> pull 的目标若是集群外 exporter，用 NodePort/LoadBalancer/Ingress 暴露后填对应地址。

### 4.2 Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: opensearch-credentials
  namespace: monitoring
type: Opaque
stringData:
  OPENSEARCH_USERNAME: admin
  OPENSEARCH_PASSWORD: <密码>
```

### 4.3 Deployment + Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: data-prepper
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels: { app: data-prepper }
  template:
    metadata:
      labels: { app: data-prepper }
    spec:
      containers:
        - name: data-prepper
          image: opensearchproject/data-prepper:2.15.1   # 方案B用 2.16.0
          ports:
            - { containerPort: 9090 }                     # prometheus remote_write 接收
          env:
            - name: OPENSEARCH_USERNAME
              valueFrom:
                secretKeyRef: { name: opensearch-credentials, key: OPENSEARCH_USERNAME }
            - name: OPENSEARCH_PASSWORD
              valueFrom:
                secretKeyRef: { name: opensearch-credentials, key: OPENSEARCH_PASSWORD }
          volumeMounts:
            - name: config
              mountPath: /usr/share/data-prepper/config
              readOnly: true
            - name: pipelines
              mountPath: /usr/share/data-prepper/pipelines
              readOnly: true
          resources: {}
      volumes:
        - name: config
          configMap: { name: data-prepper, items: [{ key: data-prepper-config.yaml, path: data-prepper-config.yaml }] }
        - name: pipelines
          configMap: { name: data-prepper, items: [{ key: pipelines.yaml, path: pipelines.yaml }] }
---
apiVersion: v1
kind: Service
metadata:
  name: data-prepper
  namespace: monitoring
spec:
  selector: { app: data-prepper }
  ports:
    - name: prometheus
      port: 9090
      targetPort: 9090
```

### 4.4 Prometheus 侧加 remote_write（方案 A）

K8s 内用 **prometheus-operator / kube-prometheus-stack** 时，在 Prometheus CR 加：

```yaml
apiVersion: monitoring.coreos.com/v1
kind: Prometheus
metadata:
  name: main
  namespace: monitoring
spec:
  ...
  remoteWrite:
    - url: http://data-prepper.monitoring.svc.cluster.local:9090/api/v1/write
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "custom_npu_total.*|npu_.*"   # 正则匹配的指标名称数据 push 到 opensearch
        action: keep
```

若是裸配置（ConfigMap 挂载 prometheus.yml），在 `prometheus.yml` 追加：

```yaml
remote_write:
  - url: "http://data-prepper.monitoring.svc.cluster.local:9090/api/v1/write"
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "custom_npu_total.*|npu_.*"   # 正则匹配的指标名称数据 push 到 opensearch
        action: keep
```
> `write_relabel_configs`根据实际情况配置，推荐只 push `NPU`使用相关数据。

## 5. 发布与验证

```bash
kubectl apply -f monitoring/data-prepper-cm.yaml
kubectl apply -f monitoring/data-prepper-secret.yaml
kubectl apply -f monitoring/data-prepper-deploy.yaml
# Prometheus CR 或 prometheus.yml configmap 变更后需 reload（operator 自动 / curl -XPOST /-/reload）

kubectl -n monitoring logs -f deploy/data-prepper   # 期望出现 "Initialized OpenSearch sink"
```

等 1~2 个抓取/推送周期后：

```bash
kubectl -n monitoring get svc data-prepper
# 文档数（示例为同集群内可达 OpenSearch 的 pod 内执行）
curl -u admin:<密码> \
  "https://opensearch.monitoring.svc.cluster.local:9200/node_lite_es/_count"
```

## 6. 常见问题

| 现象 | 排查 |
| --- | --- |
| push 500 `makeExtensionsImmutable` | 用了 2.16.0，改 2.15.1 |
| `PKIX path building failed` / 证书错误 | `ca.pem` 内容或路径错误；确认 PEM 格式且乘载正确 |
| 401/403 | Secret 里 username/password 是否正确、索引写权限 |
| count 为 0、日志无报错 | 检查数据-prepper 到 OpenSearch 的网络出口；remote_write 是否被 Prometheus 侧 reject（看 Prometheus 日志） |
| pull 抓不到 | 目标 URL 可达性、`insecure: true` 未开 |
| 401 | 证书中只有内网IP，没有公网IP，hostname 验证不通过、`insecure: true` 未开 |

## 7. 备注：`up` 指标

`up{job,instance}` 是 **Prometheus 抓取时合成**的。
- push 方案（A）：data-prepper 会收到 `up`；
- pull 方案（B）：直抓 exporter，**没有** `up`，等价信号用 data-prepper 的 `scrapeSuccess`/`scrapeFailure` 计数。
