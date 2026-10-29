---
layout: default
---

# doc-qa-service 交付文档

企业文档问答后端服务：上传 → 异步索引 → 向量检索 → 带引用的问答。
一条命令部署，可在客户内网离线运行。

[源码仓库](https://github.com/zst020503-ai/doc-qa-service)

## 交付文档

私有化交付需要的四份文档，按现场使用顺序排列：

| 文档 | 什么时候用 | 内容 |
|---|---|---|
| [安装部署手册](安装部署手册.md) | 上门第一天 | 环境要求、离线包制作、部署步骤、验证清单 |
| [运维手册](运维手册.md) | 交付之后 | 启停、日志、备份恢复、巡检清单、扩容 |
| [故障排查手册](故障排查手册.md) | 出问题的时候 | 13 类故障的现象 / 原因 / 排查命令 / 处理 |
| [验收测试清单](验收测试清单.md) | 客户签字之前 | 20 条验收项，可直接打印 |

## 评测报告

[问答质量评测报告](eval-report.md)：20 道标注题的命中率、误拒率、编造率，
以及切分粒度与阈值扫描的完整数据。

结论一句话：当前的默认参数（chunk 300 / 阈值 0.20）是实测扫出来的折中点，
31.2% 的误拒率是词法向量回退方案的上限，换成真实 embedding 模型后必须重测。

## 快速开始

```bash
git clone git@github.com:zst020503-ai/doc-qa-service.git
cd doc-qa-service
cp .env.example .env          # 至少改掉 JWT_SECRET
./scripts/deploy.sh
```

部署完成后打开 `http://localhost/docs` 查看接口文档。

## 相关链接

- [源码与 README](https://github.com/zst020503-ai/doc-qa-service)
- [CI 流水线](https://github.com/zst020503-ai/doc-qa-service/actions)
- [v0.1.0 发布页](https://github.com/zst020503-ai/doc-qa-service/releases/tag/v0.1.0)
