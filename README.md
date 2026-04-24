# om-data

开源社区数据仓库，用于存储和管理开源项目的元数据及社区运营指标配置。

## 项目结构

```
om-data/
├── src/
│   ├── projects.yaml                    # 开源项目清单
│   ├── community/
│   │   └── metric/
│   │       └── period_value_config.yaml # 社区服务指标配置
│   └── test.py                          # 测试文件
└── .github/
    └── workflows/                       # CI/CD 工作流
```

## 数据说明

### 项目清单 (projects.yaml)

定义了多个开源项目及其代码仓库地址：

| 项目 | 代码仓库 |
|------|----------|
| openGauss | gitcode.com/opengauss |
| Cantian | gitee.com/openeuler/cantian, gitee.com/openeuler/cantian-connector-mysql, gitcode.com/Cantian |
| openFuyao | gitcode.com/openFuyao |
| openLooKeng | gitcode.com/openlookeng |
| A-Tune | gitee.com/openeuler/A-Tune |
| iSulad | gitee.com/openeuler/iSulad |
| StratoVirt | gitee.com/openeuler/stratovirt |
| ModelEngine | gitcode.com/ModelEngine |
| Kmesh | github.com/kmesh-net/kmesh |
| Kuasar | github.com/kuasar-io/kuasar |
| Kurator | github.com/kurator-dev/kurator |
| Kappital | github.com/kappital/kappital |
| Oniro | github.com/eclipse-oniro4openharmony |
| open-ebackup | gitcode.com/eBackup |
| xuanwu | gitcode.com/xuanwu |
| cangjie | gitcode.com/Cangjie |
| openInula | gitcode.com/openInula |
| openHiTLS | gitcode.com/openHiTLS |
| Sermant | gitcode.com/huaweicloud/Sermant |
| DevUI | gitcode.com/DevCloudFE/vue-devui |
| OpenTiny | gitcode.com/opentiny |

### 指标配置 (period_value_config.yaml)

社区服务指标配置，支持以下指标：

| 指标 | 说明 | 维度 |
|------|------|------|
| visit_time | 服务/模块访问时间 | service, module |
| stay_time | 服务/模块停留时间 | service, module |
| previous_visit_time | 上个周期访问时间 | service, module |
| previous_stay_time | 上个周期停留时间 | service, module |

配置支持按日、周、月周期计算，适用于 openubmc、openeuler 等社区。

## 使用方式

```bash
# 克隆仓库
git clone <repository-url>

# 查看项目清单
cat src/projects.yaml

# 查看指标配置
cat src/community/metric/period_value_config.yaml
```

## 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -am 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request