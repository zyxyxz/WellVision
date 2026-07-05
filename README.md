# 🛢️ WellVision - Intelligent Drilling Online Lab Platform
WellVision — 智能钻井在线实验室平台
> **智能钻井线上实验室平台** —— 面向智能短节/智能钻头的全链路数据平台，支持数据采集、可视化、AI分析、多智能体协作与专家审核（Human-in-the-loop），服务科研团队与石油钻井客户。

---

## ✨ 项目目标

本项目旨在构建一个统一的平台，实现：

* 井下工程参数采集后的数据统一导入
* 原始数据治理、结构化存储与可视化展示
* AI算法自动识别钻井异常与钻头健康状态
* 多智能体协同完成分析任务、生成报告
* 专家审核闭环，向石油客户交付结论与建议

平台既可作为科研“线上实验室”，也可作为油田客户交付系统。

---

## ✅ 可行性评估（基于当前 README）

结论：方向可行，但当前仓库仍处于“架构蓝图/产品设计”阶段，落地成可用系统需要把“数据契约 + 云资源选型 + 工程化骨架”先收敛。

优势与可行性基础：

* 技术路线成熟：FastAPI + Postgres/Timescale + 对象存储 + Celery + MLflow 是工业界常见组合
* 业务链路完整：从采集、治理、分析到交付与审核，闭环清晰
* 演进路径合理：Roadmap 从可视化与基础模型逐步走向智能体与大模型

主要风险与需要优先补强的点：

* 数据标准不清晰：井号/井段/BHA/传感器通道等若无统一数据契约，后期会出现大量“不可复用数据”
* 实时与离线边界未定义：哪些走流式处理、哪些走批处理，需要明确
* AI 输出可追溯性不足：需要从 Day 1 设计实验追踪、特征版本、模型版本与审核记录
* 多租户与权限：油田客户视角往往要求严格隔离与审计

建议的落地优先级（非常关键）：

1. 先确定数据契约与分层（Raw/Clean/Feature/Serve）
2. 先跑通一条“云优先”的最小链路：上传 → 存储 → 查询 → 可视化 → 报告
3. 再引入智能体与更复杂的 AI 工作流

---

## 👥 典型用户

| 角色                  | 能力与权限                |
| ------------------- | -------------------- |
| Researcher（研究员）     | 数据探索、在线实验、模型训练、智能体配置 |
| ML Engineer（算法工程师）  | 模型迭代、部署、版本管理         |
| Expert Reviewer（专家） | AI输出审核、规则管理、人机闭环     |
| Client Viewer（客户）   | 查看汇总结论、报告、关键指标       |
| Admin（管理员）          | 系统配置、权限管理、设备接入       |

---

## 🔐 多租户强隔离与可上线版本要求（明确为 In-Scope）

结论：本项目默认按“客户可用的生产级系统”来设计，必须支持多租户强隔离、登录认证、管理员与租户权限体系、审计与可追溯。

强隔离目标（必须满足）：

* 租户数据不可见：任何查询、导出、报告、AI分析结果都必须带租户边界
* 默认云资源：优先托管数据库/对象存储/缓存，减少运维风险
* 全链路审计：关键操作（导入、清洗、审核、发布）必须可追溯到人和版本

推荐隔离策略（从强到弱，建议至少达到“中强隔离”）：

1. 强隔离（推荐生产）：每租户独立数据库/Schema + 独立对象存储前缀与KMS密钥
2. 中强隔离（可接受起步）：单库多租户 + Postgres RLS（行级安全）+ 强制 tenant_id
3. 弱隔离（不建议生产）：仅在应用层过滤 tenant_id

---

## 🏗️ 总体架构

```
设备端 → 数据上传 → FastAPI 后端 → 数据湖/时序库 → AI智能体服务 → 前端展示/报告交付
```

### 分层结构

1. **数据采集层**：智能短节、智能钻头、边缘上传
2. **数据治理层**：Raw/Clean 数据湖 + TimescaleDB
3. **线上实验室层**：数据探索、特征工程、实验管理
4. **AI智能分析层**：多智能体系统 + 钻井专家大模型
5. **客户交付层**：Dashboard + AI报告 + KPI汇总
6. **权限体系层**：多租户隔离 + RBAC角色权限 + 专家人在回路 + 审计追踪

---

## 🧩 核心功能模块

### ✅ 数据接入与治理

* MQTT/HTTP/文件上传
* 原始数据湖（MinIO/S3）
* 数据清洗与时间同步
* 元数据管理（井号/井段/BHA配置）

### ✅ 可视化展示

* 高性能曲线监控（ROP/WOB/Torque/Vibration）
* 异常事件自动标注
* 多井段对比分析

### ✅ AI分析能力

* Stick-slip、Bit bounce 自动识别
* 钻头健康评分（Bit Health Score）
* 参数优化建议窗口
* 自动生成工程报告
* 基础时序算法（移动平均/滚动标准差/变化率/线性趋势等）优先在数据库侧执行，支撑海量数据实时概览

### ✅ 多智能体系统（Agent Hub）

* DataAgent：数据清洗、分段
* SignalAgent：异常检测
* BitHealthAgent：寿命预测
* OptimizationAgent：参数建议
* ReportAgent：报告生成
* KnowledgeAgent：钻井专家问答

### ✅ 人在回路（Human-in-the-loop）

* AI结论需专家审核后交付客户
* 支持规则管理与标注反馈

---

## 🧱 生产级权限与租户模型（建议的默认设计）

为了支撑“客户可用版本”，建议把权限与隔离作为平台底座能力来实现，而不是业务层补丁。

核心实体（最小必备）：

* Tenant（租户/客户）
* User（用户）
* Membership（用户-租户关系，含角色）
* Role / Permission（角色与权限）
* AuditLog（审计日志）

建议的角色分层（清晰且可扩展）：

* PlatformAdmin（平台管理员）：跨租户管理、运维、租户开通/冻结
* TenantAdmin（租户管理员）：本租户内用户管理、数据策略、审核策略
* TenantEngineer（租户工程师）：数据导入、实验、模型与规则配置
* TenantReviewer（租户专家）：审核 AI 结论与报告发布
* TenantViewer（租户客户/只读）：查看看板、报告与关键指标

强隔离落地要点（务必贯彻到所有层）：

* 数据模型强制包含 `tenant_id`
* 所有查询默认带 `tenant_id` 过滤（或使用 RLS 强制）
* 对象存储使用租户前缀：`s3://bucket/{tenant_id}/raw/...`
* AI任务、报告与审核流转必须记录租户与版本信息

认证与会话建议（生产可用）：

* 认证：OIDC/SAML（企业客户）或 JWT + 刷新令牌（起步）
* 会话：短期 Access Token + 可撤销 Refresh Token
* 安全：强制 HTTPS、最小权限原则、关键操作二次确认（可选）

---

## 🧰 技术栈

### 后端（Python）

* FastAPI
* Uvicorn
* Celery（异步任务）

### 数据存储

* 时序与元数据（云优先）：Timescale Cloud / 托管 PostgreSQL（RDS / Azure Database for PostgreSQL / Cloud SQL）
* 数据湖（云优先）：Amazon S3 / Azure Blob Storage / Google Cloud Storage
* 本地开发替代：TimescaleDB（Docker）+ PostgreSQL（Docker）+ MinIO（Docker）

### AI/算法

* PyTorch
* Scikit-learn
* MLflow（模型管理）
* LLM API（OpenAI / Azure）

### 前端

* React + Vite
* ECharts / Plotly

### 部署

* Docker Compose
* Nginx Gateway
* PM2（进程守护与多服务编排）

---

## ☁️ 云优先的存储与数据湖建议（支持多种选择）

目标：默认优先调用云资源，保留本地部署仅用于开发与离线演示。

推荐的“默认云方案（更稳更快上线）”：

* 关系型与时序统一：托管 PostgreSQL + Timescale 扩展（或 Timescale Cloud）
* 数据湖：S3 / Blob / GCS 三选一
* 消息与任务：托管 Redis（或云消息队列 + 任务系统）

工程实现上建议做两层抽象：

* 数据库：统一使用 `DATABASE_URL`（SQLAlchemy / psycopg）
* 对象存储：统一使用 S3 兼容接口（生产用云厂商，开发用 MinIO）

建议的环境变量（示例）：

```bash
# 统一数据库连接（建议直接指向云托管 Postgres/Timescale）
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/wellvision
TIMESCALEDB_ENABLED=true
TIMESCALEDB_CHUNK_INTERVAL_HOURS=24
TIMESCALEDB_COMPRESS_AFTER_HOURS=0
TIMESCALEDB_RETENTION_DAYS=0

# 对象存储（云优先；本地开发可替换为 MinIO）
OBJECT_STORE_PROVIDER=s3
OBJECT_STORE_BUCKET=wellvision-raw
AWS_REGION=us-east-1

# 如果使用 S3 兼容（如 MinIO / R2 / 其他对象存储）
S3_ENDPOINT_URL=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# AI 与任务系统
OPENAI_API_KEY=
REDIS_URL=redis://user:pass@host:6379/0
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}
```

可选技术增强（非常建议尽早考虑）：

* 数据湖表格式：Iceberg 或 Delta Lake（便于治理与回溯）
* 查询加速：Trino / Athena / BigQuery（面向分析与报表）
* 数据质量：Great Expectations（或最小化自定义校验框架）

---

## 📂 推荐项目目录结构

```
wellvision/
│
├── backend/
│   ├── app/
│   │   ├── api/                # 路由层
│   │   ├── services/           # 业务逻辑
│   │   ├── models/             # ORM模型
│   │   ├── agents/             # 多智能体模块
│   │   ├── ai/                 # 算法推理服务
│   │   ├── auth/               # 权限管理
│   │   └── main.py             # FastAPI入口
│   │
│   ├── worker/                 # Celery任务
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/
│   └── package.json
│
├── infra/
│   ├── docker-compose.yml
│   ├── nginx.conf
│   └── scripts/
│
├── docs/
│   ├── architecture.md
│   ├── api-spec.md
│   └── roadmap.md
│
└── README.md
```

---

## 🚀 快速启动（开发环境）

说明：开发阶段默认优先使用 `PM2`（与当前仓库实践一致）；`docker compose` 作为可选方案用于本地演示或依赖服务编排。

### 0. 开发阶段推荐（PM2 优先）

```bash
# 首次安装依赖
cd backend && pip install -r requirements.txt
cd ../frontend && npm install
cd ..

# 启动/重启 WellVision 开发服务
pm2 start ecosystem.config.js --only wellvision-api,wellvision-frontend --update-env
pm2 status
```

### 0.1 时序优化初始化（建议）

当你把 `events` 升级为 `event_metrics + event_metrics_rollup_1m` 双层结构后，建议执行一次历史回填，避免“新数据走时序表、老数据仍在 JSON”的查询割裂。

```bash
cd backend
python3 scripts/backfill_event_metrics.py --batch-size 2000
```

可选：分批执行，降低单次负载。

```bash
python3 scripts/backfill_event_metrics.py --batch-size 1000 --max-batches 20
```

### 1. 克隆项目

```bash
git clone https://github.com/your-org/wellvision.git
cd wellvision
```

### 2. 启动基础设施

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

如端口冲突，可通过环境变量覆盖默认端口（示例：`WELLVISION_WEB_PORT=28080`）。

本地启动后通常包含：

* FastAPI Backend
* PostgreSQL
* Redis
* MinIO
* Frontend (Vite)
* Nginx Gateway

访问地址：

* API Docs: [http://localhost:18080/api/docs](http://localhost:18080/api/docs)
* Web UI / Gateway: [http://localhost:18080](http://localhost:18080)
* MinIO Console: [http://localhost:19001](http://localhost:19001)

### 3. 仅本地手动启动后端（可选）

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

### 4. 仅本地手动启动前端（可选）

```bash
cd frontend
npm install
npm run dev
```

---

## 🚀 部署方式（PM2 进程守护）

适用场景：单机部署、云主机部署、或作为 Docker/K8s 之前的过渡方案。PM2 能很好地管理 FastAPI、Celery、前端预览服务等多个进程。

### 1. 安装 PM2

```bash
npm install -g pm2
pm2 -v
```

### 2. 使用 ecosystem 文件统一管理进程

在仓库根目录创建 `ecosystem.config.js`（示例）：

```js
module.exports = {
  apps: [
    {
      name: "wellvision-api",
      cwd: "./backend",
      script: "uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000 --workers 2",
      interpreter: "python3",
      env: {
        DATABASE_URL: process.env.DATABASE_URL,
        OPENAI_API_KEY: process.env.OPENAI_API_KEY,
        REDIS_URL: process.env.REDIS_URL,
        CELERY_BROKER_URL: process.env.CELERY_BROKER_URL,
        CELERY_RESULT_BACKEND: process.env.CELERY_RESULT_BACKEND,
      },
    },
    {
      name: "wellvision-worker",
      cwd: "./backend",
      script: "celery",
      args: "-A worker.celery_app worker --loglevel=INFO --concurrency=2",
      interpreter: "python3",
      env: {
        DATABASE_URL: process.env.DATABASE_URL,
        REDIS_URL: process.env.REDIS_URL,
        CELERY_BROKER_URL: process.env.CELERY_BROKER_URL,
        CELERY_RESULT_BACKEND: process.env.CELERY_RESULT_BACKEND,
      },
    },
    {
      name: "wellvision-frontend",
      cwd: "./frontend",
      script: "npm",
      args: "run preview -- --host 0.0.0.0 --port 5173",
      interpreter: "none",
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
```

### 3. 启动与自启动

```bash
# 启动全部服务
pm2 start ecosystem.config.js

# 查看状态
pm2 status
pm2 logs wellvision-api

# 开机自启动（按提示执行一次即可）
pm2 startup
pm2 save
```

PM2 是进程守护工具，不替代反向代理。生产环境建议继续配合 Nginx 作为网关与 HTTPS 终止层。

---

## 📌 Roadmap

### Phase 1（0-6个月）

* 数据接入 + 可视化Dashboard
* 异常检测基础模型
* 自动报告生成

### Phase 2（6-12个月）

* 钻头寿命预测
* 多智能体协作框架
* 专家审核闭环

### Phase 3（1-3年）

* 钻井专家大模型
* 强化学习参数优化
* 数字孪生与全局智能钻井助理

---

## 🤝 贡献方式

欢迎研究人员、工程师参与共建：

1. Fork 本仓库
2. 新建 feature 分支
3. 提交 PR

---

## 📄 License

本项目为实验室科研与产业化合作平台，License 可根据合作模式调整。

---

## 📬 联系

如需合作或试用平台，请联系实验室项目组。
