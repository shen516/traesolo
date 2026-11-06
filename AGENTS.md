# AGENTS.md — TraeSolo 足球量化分析

面向 AI 编码助手（Trae / Cursor / Claude Code 等）的项目级配置。会话开始时会自动读取本文件。

## 项目一句话

足球纯竞技量化分析工具 5.0（FastAPI + Vue3 全栈）。**仅供学习、研究与数据分析**：任何文案与 UI 不得构成投注建议、禁止赌博引导。

## 常用命令（Windows / PowerShell）

| 操作 | 命令 |
|------|------|
| 一键启动前后端 | 根目录 `start.bat` |
| 后端启动 | `cd backend` → `.\.venv\Scripts\python.exe main.py` → http://localhost:8000（API 前缀 `/api/v1`，文档 `/docs`） |
| 前端启动 | `cd frontend` → `npm run dev` → http://localhost:5173 |
| 后端全量测试 | `cd backend` → `.\.venv\Scripts\python.exe -m pytest tests -q -p no:warnings`（输出中文乱码时先执行 `$env:PYTHONUTF8=1`） |
| 单个测试 | 同上 + `tests/test_xxx.py::test_name` |
| 前端 lint | `cd frontend` → `npm run lint`（`lint:fix` 自动修复；日常上限 `--max-warnings 50`；CI 用 `lint:ci` 要求 0 warning） |
| 前端单测 | `cd frontend` → `npm run test:unit`（Vitest，纯逻辑模块） |
| 前端构建 | `cd frontend` → `npm run build` |
| Docker 部署 | 根目录 `docker compose up -d --build`（API 8000 / 前端 80 / redis / mysql / rq-worker） |

> 注意：`DOC/` 历史文档中出现的 `pytest -X utf8` 参数在当前环境已失效（报 unrecognized arguments），勿再使用。

## 架构速览（跨文件才能理解的要点）

- **入口** `backend/main.py`：启动时建表（`create_all` + `ensure_schema` + `init_database` 种子）、挂鉴权中间件（除白名单外所有请求需登录）、启动 scheduler；`/metrics` 暴露 Prometheus。
- **请求流**：`frontend/src/api/*` → `backend/api/*`（19 个业务模块 + health，统一在 `api/__init__.py` 注册，前缀 `/api/v1`）→ `services/*` → `db/models.py`。
- **配置单一来源** `backend/config.yaml`：模型参数、风控阈值、采集 SLA、Redis、数据库连接；生产可用环境变量 `DATABASE_URL` 覆盖（勿提交真实密码）。
- **预测链路**：`services/ensemble_registry.py`（融合权重存 DB、可动态加载）→ `prediction_runner.py` → `prediction_cache.py`；四模型 ELO + 泊松 + xG + 蒙特卡洛加权融合。
- **模型训练**：`scripts/run_full_train.py` 触发；分联赛网格搜索 + 指数平滑（`config.yaml` 的 `ensemble` 段），权重写回 DB。改模型参数优先改 `config.yaml` 与 `models/`、`services/ensemble_registry.py`。
- **数据采集**：`services/crawler_service.py` 统一调度，P1/P2/P3 优先级 + 分联赛 SLA + quality_alerts；具体爬虫散落在 `services/*_crawler.py`。改采集域先读 `.cursor/skills/traesolo-data-crawler/SKILL.md`。
- **调度 / 队列**：`scheduler_service.py`（schedule 库，进程内定时）+ `worker.py`（RQ worker）+ `job_queue.py`；Redis 锁（`training_lock` / `task_run_lock`）在 Redis 不可用时自动回退内存实现。
- **权限体系**：`api/authz.py` 权限码（如 `simulation:view`）+ `init_db.py` 种子（roles/permissions 表）。**新增权限必须同时改 authz 与种子**。
- **前端约定**：图表逻辑在 `composables/`（useMatchCharts 等）；状态在 `stores/user.js`、`follows.js`；`router/index.js` 有登录/权限守卫；图表统一 ECharts（`utils/echarts`、`utils/chartTheme`）。
- **DB 变更流程**：`db/models.py` 加模型 → Alembic 生成迁移；不要手工改表。

## 关键约束（不可违反）

1. **产品边界**：仅供学习/研究/数据分析，任何文案与 UI 不得构成投注建议、禁止赌博引导。
2. **权威来源**：以仓库代码与 `DOC/`、`backend/模型训练数据梳理.md` 为准；`requirements.md` 含未落地需求，勿按它硬改已实现架构。
3. **模拟预测只读**：`simulation_service.py` / `simulate` 接口不得写入 `predictions` 表（只落 `simulation_history`）。
4. **Windows + OpenBLAS**：大规模蒙特卡洛模拟（≥50k）需 `OPENBLAS_NUM_THREADS=1`，否则可能报 "OpenBLAS: memory allocation" 崩溃。
5. **Python ≥ 3.12**（requirements.txt 与 Dockerfile 一致）；**Pydantic V2**，禁用已弃用 API（`tests/test_pydantic_v2.py` 有守卫）。
6. **测试基线**：当前 `248 passed, 1 skipped`。改后端必须跑全量测试；新增功能配测试（`tests/conftest.py` 提供 `client` / `admin_token` fixture）。
7. **前端 lint**：日常 `--max-warnings 50`，CI `lint:ci` 为 0；改动文件需过 eslint。

## 权威文档（改对应域前先读）

- 表结构：`DOC/数据库表设计.md`、`DOC/database_schema.sql`
- 代码风格：`DOC/代码规范.md`
- 算法与场景：`DOC/竞彩赔率分析算法.md`、`DOC/预测分析场景规则.md`
- 部署：`DOC/部署与工作流文档.md`、`DOC/阿里云Linux部署环境与命令.md`
- **优化与后续规划（改动前必读）**：`DOC/2026-11-04 后续功能开发与改进规划.md`、`DOC/2026-10-30 项目优化改进方案.md`、`DOC/2026-10-26 安全与维护待办清单.md`
- 领域 Skill：`.cursor/skills/traesolo-football-quant`（通用）、`traesolo-model-training`（训练/融合）、`traesolo-data-crawler`（采集/调度）
