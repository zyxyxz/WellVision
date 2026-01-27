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

## 👥 典型用户

| 角色                  | 能力与权限                |
| ------------------- | -------------------- |
| Researcher（研究员）     | 数据探索、在线实验、模型训练、智能体配置 |
| ML Engineer（算法工程师）  | 模型迭代、部署、版本管理         |
| Expert Reviewer（专家） | AI输出审核、规则管理、人机闭环     |
| Client Viewer（客户）   | 查看汇总结论、报告、关键指标       |
| Admin（管理员）          | 系统配置、权限管理、设备接入       |

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
6. **权限体系层**：RBAC角色权限 + 专家人在回路

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

## 🧰 技术栈

### 后端（Python）

* FastAPI
* Uvicorn
* Celery（异步任务）

### 数据存储

* TimescaleDB（时序数据）
* PostgreSQL（元数据）
* MinIO（数据湖）

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

### 1. 克隆项目

```bash
git clone https://github.com/your-org/wellvision.git
cd wellvision
```

### 2. 启动基础设施

```bash
docker-compose up -d
```

启动后包含：

* FastAPI Backend
* TimescaleDB
* PostgreSQL
* MinIO
* Celery Worker

### 3. 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问：

* API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. 前端启动

```bash
cd frontend
npm install
npm run dev
```

访问：

* Web UI: [http://localhost:5173](http://localhost:5173)

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
