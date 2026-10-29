# doc-qa-service

企业文档问答后端服务：上传 → 异步索引 → 向量检索 → 带引用的问答。一条命令部署，可在内网离线运行。

![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-compose-2496ED)

[![CI](https://github.com/zst020503-ai/doc-qa-service/actions/workflows/ci.yml/badge.svg)](https://github.com/zst020503-ai/doc-qa-service/actions)

## 它和常见 RAG demo 的区别

- **检索不到就拒答**，不把是否编造交给模型自觉。阈值不是拍脑袋，20 道题扫出来的（[评测报告](docs/eval-report.md)）
- **上传与解析分离**，接口 200ms 返回 202，解析走异步队列，前端轮询状态
- **云端 API 和本地 Ollama / vLLM 同一套代码**，只改 `base_url` 和 `model`
- **四份交付文档齐全**：安装部署、运维、故障排查（13 条）、验收清单（20 条）

## 快速开始

```bash
cp .env.example .env          # 至少改掉 JWT_SECRET，国内网络另设 PIP_INDEX_URL
./scripts/deploy.sh
```

打开 http://localhost/docs 查看接口文档。

```bash
# 注册
curl -X POST http://localhost/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"12345678"}'

# 上传文档（TOKEN 换成上一步返回的 access_token）
curl -X POST http://localhost/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@./README.md'

# 等 status 变成 ready 后提问
curl -X POST http://localhost/api/v1/qa/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"这个服务怎么部署？"}'
```

## 自检与评测

```bash
# 冒烟测试：不需要数据库，验证应用加载、路由、鉴权、切分、向量
python scripts/smoke_test.py

# 问答质量评测：自动上传 samples/ 里的文档，跑 20 条测试问题
python scripts/eval_qa.py --base-url http://localhost --report docs/eval-report.md
```

冒烟测试覆盖 16 项检查，返回码非 0 即有问题，适合放在部署脚本或 CI 的第一道关卡。
评测脚本输出命中率、误拒率、编造率、P95 延迟，编造率超过 10% 时返回非 0。

`tests/questions.jsonl` 里 20 条问题，16 条可答（带期望关键词）、4 条不可答（考察拒答）。
换模型或调 `ANSWER_THRESHOLD` 之后必须重跑，否则阈值就是拍脑袋定的。

**实测结论见 [docs/eval-report.md](docs/eval-report.md)**：在 mock 词法向量下，分片越细命中率越高
（800 字切成 2 片命中 56.2%，300 字切成 6 片命中 81.2%），但细分会让所有分数整体上移，
不该答的问题也容易过线。默认值 `300 / 0.20` 是实测扫出来的折中点，编造率 25%、误拒率 31.2%——
31.2% 的误拒是词法向量的天花板，不是参数没调好，换成真实 embedding 必须重测。

## 不用 Docker 本地跑

调试代码时不必每次都构建镜像，本机有 PostgreSQL 15+ 且装了 pgvector 即可：

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://docqa@127.0.0.1:5432/docqa
export UPLOAD_DIR=/tmp/docqa-uploads
export JWT_SECRET=local-dev-only

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000   # 终端 1
python -m app.worker                                          # 终端 2
```

表结构在应用启动时自动创建，`vector` 扩展也会自动 `CREATE EXTENSION`。

本机若用 Postgres.app（已装在 `~/Applications`），启动方式：

```bash
~/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl \
  -D ~/pgdata-docqa -o "-p 5432" -l ~/pgdata-docqa/server.log start
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册并返回 JWT |
| POST | `/api/v1/auth/login` | 登录 |
| GET | `/api/v1/auth/me` | 当前用户 |
| POST | `/api/v1/documents` | 上传文档，返回 202，异步处理 |
| GET | `/api/v1/documents` | 分页列表 |
| GET | `/api/v1/documents/{id}` | 查询处理状态（前端轮询用） |
| DELETE | `/api/v1/documents/{id}` | 删除文档及其分片 |
| POST | `/api/v1/qa/ask` | 提问，返回答案 + 引用 |
| GET | `/healthz` `/readyz` | 存活 / 就绪探针 |

## 架构

![架构图](docs/images/architecture.svg?v=2)

```
nginx :80
   └── app (FastAPI)  :8000
         ├── api/v1/*        路由层：只做参数校验和调用
         ├── services/*      业务层：切分、检索、拒答、编排
         ├── repositories/*  数据层：只写 SQL，不写业务
         └── providers/*     模型接入层：embedding / chat
   └── worker (python -m app.worker)
         └── 轮询 documents 表，SKIP LOCKED 认领任务，解析并向量化
   └── db (pgvector/pg16)
```

**为什么用轮询 worker 而不是 Celery？**
单机日请求量在千级，多引一个 Redis 只增加部署和排障成本。
认领任务用 `SELECT ... FOR UPDATE SKIP LOCKED`，多个 worker 并发也不会重复处理，
这条路以后要换 Celery 也能平移。

## 目录结构

```
doc-qa-service/
├── app/
│   ├── main.py              应用入口、请求 ID 中间件、探针
│   ├── worker.py            异步任务消费进程
│   ├── models.py            users / documents / chunks
│   ├── schemas.py           请求与响应模型
│   ├── core/                配置、鉴权、错误、日志
│   ├── db/                  引擎与会话
│   ├── api/v1/              路由层
│   ├── services/            业务层
│   ├── repositories/        数据层
│   └── providers/           embedding / chat 接入
├── docs/                    四份交付文档
│   ├── 安装部署手册.md
│   ├── 运维手册.md
│   ├── 故障排查手册.md
│   └── 验收测试清单.md
├── samples/                 演示用知识库（员工手册、产品 FAQ）
├── tests/questions.jsonl    20 条评测问题
├── scripts/
│   ├── deploy.sh            一键部署
│   ├── rollback.sh          按 tag 回滚
│   ├── smoke_test.py        不依赖数据库的冒烟测试
│   └── eval_qa.py           问答质量评测
├── nginx/nginx.conf
└── docker-compose.yml
```

## 关键设计

**1. 上传与解析分离**
PDF 解析动辄几十秒，同步处理会把请求挂死。上传只落盘 + 写一条 `pending` 记录，
接口 200ms 内返回 202；worker 异步消费，前端轮询 `GET /documents/{id}` 看状态。
解析失败不吞异常，原因写回 `documents.error`，用户能看到为什么失败。

**2. 检索不到就拒答**
先算检索最高相似度，低于 `ANSWER_THRESHOLD` 直接返回「文档中没有找到相关内容」，
并附带最接近的 3 段供人工判断，而不是让模型自由发挥。
企业场景里说不知道是成本，说错才是事故。

**3. 云端 / 本地一套代码**
`providers/llm.py` 统一走 OpenAI 兼容接口，本地换 Ollama / vLLM 只改 `OPENAI_BASE_URL`。
同一份代码既能跑 SaaS 也能进内网私有化部署。

**4. 离线可用**
`EMBEDDING_PROVIDER=mock` 时用词法哈希向量，不需要任何 API Key 就能把链路跑通，
用于交付前的自检。**它只验证管线，不代表检索效果**，正式环境必须切到真实模型。

## 配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `...@db:5432/docqa` | 本机调试改 localhost |
| `JWT_SECRET` | dev 值 | 上线必须换 |
| `EMBEDDING_PROVIDER` | `mock` | `mock` / `openai` |
| `LLM_PROVIDER` | `mock` | `mock` / `openai` |
| `RETRIEVE_TOP_K` | 5 | 检索条数 |
| `ANSWER_THRESHOLD` | 0.20 | 低于此相似度拒答，实测标定值，换模型必须重测 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 300 / 50 | 按字符切分，不是 token |

## 交付文档

在线版：**https://zst020503-ai.github.io/doc-qa-service/**

私有化交付需要的四份文档都在 `docs/`：

| 文档 | 用途 | 篇幅 |
|---|---|---|
| [安装部署手册](docs/安装部署手册.md) | 从裸机到可用，含离线包制作与验证步骤 | 7 节 |
| [运维手册](docs/运维手册.md) | 启停、日志、备份恢复、巡检清单、扩容 | 10 节 |
| [故障排查手册](docs/故障排查手册.md) | 13 类故障的现象 / 原因 / 排查命令 / 处理 | 13 条 |
| [验收测试清单](docs/验收测试清单.md) | 20 条验收项，客户签收用 | 20 条 |

`故障排查手册` 是这里面最值钱的一份——面试时被问「服务起不来你怎么排查」，
直接翻到 F01/F03，照着讲。有这份东西和没有，是两个层级的可信度。

## 待办（按优先级）

- [x] 20 条测试问题 + 评测脚本
- [x] 四份交付文档
- [ ] 前端页面（Streamlit 最简版）
- [ ] 混合检索（向量 + 关键词）
- [ ] alembic 迁移替代启动时 `create_all`
- [ ] 日志轮转写进 compose 默认配置

## License

MIT
