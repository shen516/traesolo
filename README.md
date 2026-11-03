# 足球纯竞技量化分析工具（TraeSolo）

面向数据分析员、体育研究者、足球爱好者及投资机构的专业足球赛事分析平台，通过多模型深度融合与科学算法，提供赛事预测与量化分析服务。

## 核心特性

- **多模型预测**：泊松分布、ELO 评级、xG 预期进球、蒙特卡洛模拟等多模型深度融合
- **多源数据采集**：500 彩票网、竞彩、ESPN 等数据源爬虫，支持定时与手动触发
- **智能风控**：异常波动识别与风险控制体系
- **模型持续进化**：模型训练、评估监控与动态学习机制
- **完整权限体系**：用户管理、角色权限、登录防护与验证码

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12+ / FastAPI / SQLAlchemy / Alembic |
| 前端 | Vue 3 / Vite / Pinia / Vue Router / ECharts |
| 存储 | MySQL 8.0 / SQLite（本地开发）/ Redis 7 |
| 异步任务 | RQ (Redis Queue) + schedule 定时调度 |
| 部署 | Docker Compose / Nginx |

## 项目结构

```
├── backend/            # FastAPI 后端
│   ├── api/            # REST API 路由
│   ├── services/       # 业务服务（爬虫、预测、风控、调度等）
│   ├── models/         # 预测模型（泊松、ELO、xG、蒙特卡洛、集成）
│   ├── db/             # 数据库连接与模型定义
│   ├── alembic/        # 数据库迁移
│   └── tests/          # 后端测试
├── frontend/           # Vue 3 前端
│   └── src/
│       ├── views/      # 页面
│       ├── components/ # 组件
│       ├── api/        # 接口封装
│       └── stores/     # Pinia 状态
├── DOC/                # 项目文档（需求、设计、部署等）
├── docker-compose.yml  # 容器编排
└── start.bat           # Windows 一键启动脚本
```

## 快速开始

### 环境要求

- Python >= 3.12
- Node.js >= 18
- （可选）Docker 与 Docker Compose

### 本地开发启动

```bash
# 1. 后端
cd backend
python -m venv .venv
.venv\Scripts\activate.bat      # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r requirements.txt
python main.py                  # http://localhost:8000

# 2. 前端
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Windows 下也可直接运行根目录 `start.bat` 一键启动前后端。

启动后访问：

- 前端：<http://localhost:5173>
- 后端接口文档：<http://localhost:8000/docs>

### Docker 部署

```bash
docker compose up -d --build
```

包含服务：model-api（8000）、frontend（80）、redis、mysql、rq-worker。

## 测试

```bash
cd backend
pytest
```

```bash
cd frontend
npm run lint
```

## 文档

更多设计与部署文档见 [DOC/](DOC/) 目录：

- `数据库表设计.md` / `database_schema.sql` — 数据库设计
- `部署与工作流文档.md` / `阿里云Linux部署环境与命令.md` — 部署指南
- `竞彩赔率分析算法.md` / `预测分析场景规则.md` — 算法与规则说明
- `代码规范.md` — 代码规范
