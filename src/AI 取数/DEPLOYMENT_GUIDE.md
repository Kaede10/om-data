# om-nlquery wren 服务部署全记录

> **版本**：v1.0（基于 003 预览环境端到端验证固化）  
> **维护**：opensourceways/om-nlquery  
> **最后更新**：2026-09-03

---

## 目录

1. [架构概览](#1-架构概览)
2. [关键设计决策](#2-关键设计决策)
3. [部署前置条件](#3-部署前置条件)
4. [镜像构建](#4-镜像构建)
5. [K8s 部署（含持久化）](#5-k8s-部署含持久化)
6. [关键配置说明](#6-关键配置说明)
7. [已知坑位与规避](#7-已知坑位与规避)
8. [运维操作手册](#8-运维操作手册)
9. [故障排查清单](#9-故障排查清单)
10. [本地开发 vs 生产差异](#10-本地开发-vs-生产差异)
11. [扩缩容与高可用](#11-扩缩容与高可用)
12. [备份与灾难恢复](#12-备份与灾难恢复)

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        K8s Cluster                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Deployment: wren-nlquery (1 replica)                     │  │
│  │  ┌──────────────────┐  ┌──────────────────────────────┐  │  │
│  │  │ Init Container   │  │ Main Container (uid 1000)    │  │  │
│  │  │ hf-model-init    │  │ - wren_server.py (Flask)     │  │  │
│  │  │ - 下载 embedding │  │ - /wren/entrypoint.sh        │  │  │
│  │  │   模型到 PVC     │  │ - wren CLI + LanceDB         │  │  │
│  │  └────────┬─────────┘  └──────────────┬──────────────┘  │  │
│  │           │                           │                  │  │
│  │           ▼                           ▼                  │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │ Shared PVCs (ReadWriteOnce)                        │  │  │
│  │  │  - wren-state    → /wren/.wren       (LanceDB)     │  │  │
│  │  │  - wren-hf-cache → /home/ccdev/.cache/huggingface  │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                    │
│              ┌─────────────┴─────────────┐                      │
│              ▼                           ▼                      │
│      ┌──────────────┐            ┌──────────────┐               │
│      │ PostgreSQL   │            │ 智谱 GLM API  │               │
│      │ (只读账号)    │            │ (Coding Plan) │               │
│      └──────────────┘            └──────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

**核心组件**：

| 组件 | 角色 | 持久化 |
|------|------|--------|
| `wren_server.py` | HTTP API (SSE 流式) | 无状态 |
| `wren CLI` | MDL 语义层查询引擎 | 无状态 |
| `LanceDB` | 向量索引（schema_items + query_history） | **PVC: wren-state** |
| `sentence-transformers` | embedding 模型 | **PVC: wren-hf-cache** |
| `claude-code` | Agent 模式 MCP client | 无状态 |

---

## 2. 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| **镜像不含 embedding 模型** | ~458MB 模型放 PVC，init 容器首次下载 | 镜像小（~1.2GB vs ~1.6GB）、构建快、节点无外网可预置 |
| **LanceDB 用 PVC 持久化** | `wren-state` (5Gi) | 避免 pod 重建触发 15 分钟 `wren memory index` 重跑 |
| **embedding 模型用独立 PVC** | `wren-hf-cache` (2Gi) | 与 LanceDB 生命周期解耦，可单独备份/迁移 |
| **init 容器下载模型** | 同镜像、uid 1000、挂载 hf-cache | 复用主镜像依赖（wrenai[memory] 含 sentence-transformers） |
| **容器非 root (uid 1000)** | `runAsUser: 1000` | claude-code `--dangerously-skip-permissions` 拒绝 root |
| **数据库只读账号** | `wren_ro` + SELECT 白名单 | 双层防护：DB 层只读 + 应用层 SQL 白名单 |
| **零密钥进镜像** | 所有凭据 Secret 注入/文件挂载 | 镜像可公开、GitOps 友好、审计合规 |

---

## 3. 部署前置条件

### 3.1 PostgreSQL 只读账号（必须）

```sql
-- 由 DBA 执行，密码走 Secret 注入
CREATE ROLE wren_ro LOGIN PASSWORD '<强随机密码>';
GRANT USAGE ON SCHEMA public TO wren_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO wren_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO wren_ro;
```

> ⚠️ **强制要求**：服务**只允许**以此账号连库。任何写权限账号都是安全事故。

### 3.2 智谱 GLM API Key（Coding Plan）

- 必须使用 **Coding Plan（Max/Pro）**，走 `/api/coding/paas/v4` 端点
- 按量付费 key 需改 `/api/paas/v4`
- Agent 模式自动用 `/api/anthropic`（anthropic 兼容）

### 3.3 K8s 集群要求

| 资源 | 最小值 | 推荐值 | 说明 |
|------|--------|--------|------|
| CPU request | 250m | 500m | 启动期峰值较高 |
| CPU limit | 2核 | 4核 | LLM 推理 + 向量检索 |
| Memory request | 512Mi | 1Gi | |
| Memory limit | 4Gi | 8Gi | `wren memory index` 峰值 ~1.8GB |
| Storage (wren-state) | 5Gi | 10Gi | LanceDB 索引增长 |
| Storage (wren-hf-cache) | 2Gi | 2Gi | 固定 ~470MB |

### 3.4 StorageClass

- PVC 需配置 `storageClassName`（按集群实际填，如 `csi-disk`、`efs`、`local-path`）
- 若集群有默认 SC，可注释掉 `storageClassName` 行

---

## 4. 镜像构建

```bash
cd om-nlquery
docker build -t <registry>/om-nlquery-wren:<tag> .
docker push <registry>/om-nlquery-wren:<tag>

# 例（华为云 SWR）：
# docker build -t swr.cn-north-4.myhuaweicloud.com/opensourceway/om-nlquery-wren:v1 .
# docker push swr.cn-north-4.myhuaweicloud.com/opensourceway/om-nlquery-wren:v1
```

**构建特点**：
- 多阶段构建：`deps` (root 安装依赖) → `runtime` (uid 1000 运行)
- 构建耗时 ~15 分钟（Rust 引擎 wheel + node/claude 安装）
- **镜像不含 embedding 模型**，模型由 init 容器运行时下载到 PVC
- 镜像大小 ~1.2GB（压缩后 ~400MB）

**关键 Dockerfile 片段**：

```dockerfile
# deps 阶段：装 wrenai + node/claude
FROM python:3.11 AS deps
RUN pip install --no-cache-dir "wrenai[postgres]" "wrenai[memory]" flask pyyaml
RUN npm install -g @anthropic-ai/claude-code

# runtime 阶段：非 root、复制文件、ENTRYPOINT entrypoint.sh
FROM python:3.11-slim
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin/wren /usr/local/bin/wren
# ... 拷贝 models/ knowledge/ target/ wren_project.yml 等
USER 1000
ENTRYPOINT ["/entrypoint.sh"]
```

---

## 5. K8s 部署（含持久化）

### 5.1 完整资源清单

见 `deploy/k8s.yaml`，核心资源：

```yaml
# 1. Secret（运行时注入，不入镜像不入仓）
- wren-pg      (password)
- wren-glm     (GLM_API_KEY)
- wren-clone   (token，可选，用于采纳沉淀推 wren-memory 分支)

# 2. PVC
- wren-state       (5Gi, ReadWriteOnce)  → /wren/.wren
- wren-hf-cache    (2Gi, ReadWriteOnce)  → /home/ccdev/.cache/huggingface

# 3. Deployment
- initContainers: hf-model-init (下载 embedding 模型到 PVC)
- containers: wren (主服务)
- volumes: 两个 PVC + clone-token secret

# 4. Service + Ingress
```

### 5.2 部署步骤

```bash
# 1. 创建 Secret（先改密码/key）
kubectl -n om-datacenter create secret generic wren-pg  --from-literal=password='<wren_ro密码>'
kubectl -n om-datacenter create secret generic wren-glm --from-literal=GLM_API_KEY='<智谱key>'
# 可选
kubectl -n om-datacenter create secret generic wren-clone --from-literal=token='<github token>'

# 2. 修改 k8s.yaml 中的 <image> 为实际镜像地址
# 3. 若无默认 StorageClass，取消注释 storageClassName 并填正确值

# 4. 应用
kubectl apply -f deploy/k8s.yaml
```

### 5.3 首次启动时间线

| 阶段 | 耗时 | 说明 |
|------|------|------|
| Pod 调度 + 镜像拉取 | 1-3 分钟 | 取决于镜像仓库速度 |
| init 容器下载模型 | 2-5 分钟 | ~470MB，取决于外网/镜像源速度 |
| 主容器启动 + profile 建立 | < 30 秒 | 秒级 |
| **后台 `wren memory index`** | **~15 分钟** | 首次构建 LanceDB 索引，2347 模型向量化 |
| `/healthz` 返回 ok | 立即 | 不等待 index 完成 |

> ✅ **验证**：`kubectl logs -f <pod> -c wren` 看 `/tmp/index.log` 进度；`/healthz` 通即可用，索引后台跑。

---

## 6. 关键配置说明

### 6.1 环境变量（全部运行时注入）

| 变量 | 默认值 | 说明 | 必填 |
|------|--------|------|------|
| `PGHOST` | - | PG 地址 | ✅ |
| `PGPORT` | 5432 | PG 端口 | |
| `PGDATABASE` | onedata | 数据库名 | |
| `PGUSER` | wren_ro | **只读账号** | ✅ |
| `PGPASSWORD` | - | 密码（Secret） | ✅ |
| `GLM_API_KEY` | - | 智谱 key（Secret） | ✅ |
| `LLM_BASE_URL` | `https://open.bigmodel.cn/api/coding/paas/v4` | Coding Plan 端点 | |
| `CHATBI_LLM_MODEL` | `glm-5.3` | 主模型 | |
| `CHATBI_LLM_FALLBACK` | `glm-5.3-flash` | 降级模型 | |
| `HF_HOME` | `/home/ccdev/.cache/huggingface` | **已挂 PVC**，模型缓存 | |
| `WREN_MEMORY_CLONE_TOKEN_FILE` | - | 采纳沉淀 token 文件路径 | 可选 |

### 6.2 entrypoint.sh 启动流程

```bash
1. 校验必需环境变量
2. 生成 /tmp/conn.yml → wren profile add onedata --activate
3. 写 GLM_API_KEY 到 /tmp/.glmkey (chmod 600)
4. 检测 /wren/.wren/memory/schema_items.lance 是否存在
   - 存在 → 跳过 index，直接启动服务
   - 不存在 → 后台跑 `wren memory index` (输出 /tmp/index.log)
5. 处理 clone token（可选）
6. 确保 HF_HOME 目录存在
7. exec python3 /usr/local/bin/wren_server.py
```

### 6.3 wren_server.py 关键端点

| 端点 | 模式 | 用途 |
|------|------|------|
| `POST /wren/exec` | sync | 受控 SQL 执行 / 向量检索 (`mode=sql|fetch`) |
| `POST /wren/ask` | SSE | **编排模式**：规则+schema+LLM 生成 SQL → 执行 → 组织答案 |
| `POST /wren/chat` | SSE | **多轮对话**：带历史上下文、可纠正 |
| `POST /wren/agent` | SSE | **Agent 模式**：claude-code + wren MCP 自主编排 |
| `POST /wren/remember` | sync | 采纳沉淀：确认问法→SQL 存 memory + 推 PR |
| `POST /wren/feedback` | sync | 用户反馈 (correct/wrong) 记录本地 |
| `GET /healthz` | sync | 健康检查 |

---

## 7. 已知坑位与规避

| # | 坑位 | 现象 | 规避/解决 |
|---|------|------|-----------|
| 1 | `HF_ENDPOINT=hf-mirror.com` | `FileMetadataError: metadata header missing` | **绝对不要设** `HF_ENDPOINT`；模型下载走官方源，或预置 PVC |
| 2 | `glm-5.3` 推理模型回复为空 | `max_tokens` 全花在 reasoning，visible tokens 为 0 | 服务端已放大 `max_tokens`；若换模型需同步调整 |
| 3 | `wren memory index` OOM | Pod 被 Kill，重启循环 | Memory limit ≥ 4Gi；若仍 OOM 调大至 8Gi |
| 4 | PVC `ReadWriteOnce` 多副本冲突 | 第 2 个 Pod 起不来 | **replicas: 1**；LanceDB 不支持多写 |
| 5 | `emptyDir` 导致重启丢索引 | 每次重建 15 分钟 | **必须用 PVC**（已修复） |
| 6 | `claude` root 报错 | `dangerously-skip-permissions requires non-root` | 容器 **必须 uid 1000**（已强制） |
| 7 | PG 连接数耗尽 | `too many connections` | 只读账号 + 连接池；检查 `max_connections` |
| 8 | Ingress SSE 断流 | nginx 默认 60s 超时切断长连接 | Ingress annotation: `nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"` |
| 9 | 模型下载卡住 | init 容器一直 Running | 检查外网/防火墙；或预置 PVC 绕过下载 |
| 10 | `wren memory index` 重复跑 | 每次重启都 15 分钟 | entrypoint 已加 sentinel 检测；确认 PVC mountPath 正确 |

---

## 8. 运维操作手册

### 8.1 查看索引构建进度

```bash
kubectl logs -f <pod> -c wren | grep -E "index|embedding|vector"
# 或直接看文件
kubectl exec <pod> -c wren -- tail -f /tmp/index.log
```

### 8.2 手动触发索引重建

```bash
# 删除 PVC 数据（慎用！会重跑 15 分钟）
kubectl exec <pod> -c wren -- rm -rf /wren/.wren/memory/*
# 重启 pod 触发重建
kubectl delete pod <pod> -n om-datacenter
```

### 8.3 查看向量索引状态

```bash
kubectl exec <pod> -c wren -- wren memory fetch --query "测试" --limit 3 -o json
# 返回非空数组 = 索引正常
```

### 8.4 采纳沉淀同步状态

```bash
# 查看后台同步日志
kubectl logs <pod> -c wren | grep "memory-sync"
# 手动触发同步
curl -X POST <service>/wren/remember -d '{"question":"...", "sql":"..."}'
```

### 8.5 修改 LLM 模型（热更，无需重建镜像）

```bash
kubectl set env deployment/wren-nlquery CHATBI_LLM_MODEL=glm-5.3-flash -n om-datacenter
# 或 patch
kubectl patch deployment wren-nlquery -n om-datacenter -p '{"spec":{"template":{"spec":{"containers":[{"name":"wren","env":[{"name":"CHATBI_LLM_MODEL","value":"glm-5.3-flash"}]}]}}}}'
```

### 8.6 滚动更新镜像

```bash
kubectl set image deployment/wren-nlquery wren=<new-image> -n om-datacenter
# 观察
kubectl rollout status deployment/wren-nlquery -n om-datacenter
```

---

## 9. 故障排查清单

### 9.1 Pod 起不来

| 现象 | 排查步骤 |
|------|----------|
| `ImagePullBackOff` | 检查镜像地址、registry secret、网络 |
| `CrashLoopBackOff` | `kubectl logs <pod> -c wren --previous` 看报错 |
| `Init:Error` | `kubectl logs <pod> -c hf-model-init` 看模型下载失败原因 |
| `Pending` | `kubectl describe pod` 看事件：PVC 未绑定/资源不足/SC 缺失 |

### 9.2 服务不可用（Pod Running 但请求失败）

| 症状 | 排查 |
|------|------|
| `/healthz` 404/500 | 看 wren_server 启动日志；检查端口 8910 |
| `/wren/ask` 返回 code=-1 | 看 SSE trace 中 `step` 卡在哪：instructions / schema / llm / sql / rows |
| `memory fetch` 空结果 | 1) 索引未完成 2) LanceDB 路径错 3) embedding 模型缺失 |
| LLM 报 429/5xx | 智谱配额/限流；检查 `CHATBI_LLM_FALLBACK` 是否生效 |
| SQL 执行报错 | 看 trace 中 `stderr`：常为臆造列名/表名，服务会自动重试 1 次 |

### 9.3 性能问题

| 问题 | 排查/优化 |
|------|-----------|
| 首次请求慢 (20-30s) | 正常：glm-5.3 推理模型思考期 10-20s；后续走缓存快 |
| 并发请求排队 | 单副本串行；考虑 HPA + 读写分离（LanceDB 不支持多写） |
| 内存持续增长 | 检查 Flask 连接未关闭 / LanceDB 连接泄漏；定期重启 |

---

## 10. 本地开发 vs 生产差异

| 维度 | 本地开发 | 生产部署 |
|------|----------|----------|
| **工作目录** | `$(pwd)` | `/wren` (WORKDIR) |
| **LanceDB 路径** | `./.wren/memory/` | `/wren/.wren/memory/` (PVC) |
| **模型缓存** | `~/.cache/huggingface/` | `/home/ccdev/.cache/huggingface/` (PVC) |
| **数据持久化** | 否（本地文件） | 是（PVC） |
| **索引复用** | 手动跑 `wren memory index` | 自动复用 PVC，存在则跳过 |
| **多实例** | 单进程 | 单副本 (LanceDB 限制) |
| **密钥管理** | `.env` 文件 | K8s Secret |
| **日志** | stdout/stderr | kubectl logs / Loki |
| **调试** | 直接改代码热重载 | 需重建镜像/滚动更新 |

**本地开发推荐：挂载模式共享索引**

```bash
# 本地目录直接挂到容器，LanceDB 与模型缓存共用，不用重复索引
docker run -d --name wren-dev \
  -v $(pwd):/wren \
  -v ~/.cache/huggingface:/home/ccdev/.cache/huggingface \
  -e PGHOST=... -e PGPASSWORD=... -e GLM_API_KEY=... \
  -p 8910:8910 \
  <image>
```

---

## 11. 扩缩容与高可用

### 11.1 当前限制

- **LanceDB 是嵌入式文件库，不支持多写入者** → `replicas: 1` 强制单副本
- PVC `ReadWriteOnce` 也限制单节点挂载

### 11.2 扩容方案（未来）

| 方案 | 可行性 | 说明 |
|------|--------|------|
| 读写分离：主节点写索引，从节点只读挂载同一 PVC (ROX) | 中 | 需 LanceDB 支持 ROX 多挂载，或用 NFS |
| 外置向量库：迁移到 Milvus/Weaviate/PGVector | 高 | 彻底解决 HA，但引入外部依赖 |
| 多 AZ 部署 + 定期同步索引 | 低 | 运维复杂 |

**当前建议**：单副本 + PVC 持久化 + 合理的 PodDisruptionBudget + 快速重建能力（索引 15 分钟）。

```yaml
# 建议加的 PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: wren-nlquery-pdb
  namespace: om-datacenter
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: wren-nlquery
```

---

## 12. 备份与灾难恢复

### 12.1 需备份的数据

| 数据 | 位置 | 备份频率 | 方式 |
|------|------|----------|------|
| **LanceDB 索引** | PVC `wren-state` (`/wren/.wren/memory/`) | 每日/变更后 | Volume snapshot / 文件级拷贝 |
| **embedding 模型** | PVC `wren-hf-cache` | 首次后无需备份（可重下载） | 可选 |
| **采纳沉淀 SQL** | `knowledge/sql/*.md` (Git) | 每次合并 PR | Git 即备份 |
| **业务规则** | `knowledge/rules/*.md` (Git) | 每次合并 PR | Git 即备份 |
| **用户反馈** | `knowledge/feedback/feedback.jsonl` | 每日 | 同步到对象存储 |

### 12.2 灾难恢复演练

1. **模拟 PVC 丢失**：删除 PVC → 重建 → 验证 init 容器下载模型 + 后台重建索引 (~15 分钟)
2. **模拟镜像仓库不可用**：本地保留镜像 tarball `docker save/load`
3. **模拟 PG 只读账号失效**：轮换密码 → 更新 Secret → 滚动重启

### 12.3 RTO / RPO 目标

| 指标 | 目标 | 说明 |
|------|------|------|
| RTO (恢复时间目标) | < 20 分钟 | 主要耗时在索引重建 (15 分钟) |
| RPO (恢复点目标) | 0 (索引) / 日级 (反馈) | LanceDB 实时写入；反馈文件日级同步 |

---

## 附录 A：关键文件清单

```
om-nlquery/
├── Dockerfile                    # 多阶段构建，非 root
├── wren_server.py                # Flask HTTP API (SSE)
├── deploy/
│   ├── entrypoint.sh             # 启动脚本：profile→模型→索引→服务
│   ├── k8s.yaml                  # K8s 完整资源 (Secret/PVC/Deploy/Svc/Ingress)
│   ├── README.md                 # 部署快速指南
│   └── DEPLOYMENT_GUIDE.md       # 本文档
├── wren_project.yml              # 项目元数据
├── relationships.yml             # 模型关系
├── models/                       # MDL 模型定义
├── knowledge/
│   ├── rules/                    # 业务口径规则 (wren context instructions)
│   └── sql/                      # 采纳沉淀的 NL→SQL (wren memory store)
└── target/mdl.json               # 编译后的 MDL (构建期生成)
```

---

## 附录 B：版本变更记录

| 版本 | 日期 | 变更 | 作者 |
|------|------|------|------|
| v1.0 | 2026-09-03 | 初版：持久化 PVC + init 容器下载模型 + 非 root + 只读账号 | - |

---

> **维护提示**：本文档随部署演进同步更新。重大架构变更（如向量库外置、多副本 HA）需同步更新决策记录与运维手册。
