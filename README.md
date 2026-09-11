# 车间停机管理（Downtime Tracker）

记录车间产线/设备停机事件，并基于 **5 Whys** 做根因分析、跟踪改善措施闭环。

- 前端：React 18 + TypeScript + Ant Design 5 + Vite
- 后端：Python 3.11 + FastAPI + SQLAlchemy 2
- 数据库：PostgreSQL（本地开发无 PG 时可用 SQLite 冒烟）

## 功能（本期）

1. **事件登记**：操作工选择产线 → 设备、停机原因（按大类分组）、起止时间、时长（可自动计算或后补）、班次、操作工、工单/备注。
2. **事件列表**：按产线/状态/日期/关键字筛选、分页，展示状态、是否已分析、未闭环措施数。
3. **根因分析**：班组长在事件详情页填写问题描述 + 5 Whys + 根因结论。
4. **改善措施跟踪**：为事件挂措施（内容/责任人/计划完成日期/状态），支持状态流转、编辑、删除。
5. **原因分析（帕累托）**：按停机原因聚合次数/时长，按次数降序并给出累计占比，识别累计 ≤ 80% 的“关键少数”原因。

事件状态流转：`待分析 open → 分析/改善中 analyzing → 已关闭 closed`（首次保存 5 Whys 自动转入 analyzing）。

## 目录

```
backend/        FastAPI 服务（app/：models/schemas/routers/seed）
frontend/       React 前端（src/pages、src/components）
docker-compose.yml  PostgreSQL + 后端
```

## 快速启动（docker compose，含 PostgreSQL）

```bash
docker compose up -d --build
# 后端: http://localhost:8000  （/docs 为接口文档）
cd frontend && npm install && npm run dev
# 前端: http://localhost:5173 （已配置 /api 代理到 8000）
```

首次启动自动建表并写入演示数据（3 条产线、8 台设备、11 个停机原因、12 个近 7 天事件，其中 1 个含完整 5 Whys 与措施）。

## 本地开发（不使用 Docker）

后端：

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# 方式 A：连接本机 PostgreSQL（先建好库/账号）
cp backend/.env.example backend/.env   # 按需修改 DT_DATABASE_URL
.venv/bin/uvicorn app.main:app --reload --app-dir backend

# 方式 B：仅冒烟，用 SQLite（设置环境变量）
DT_DATABASE_URL="sqlite:////tmp/downtime.db" \
  .venv/bin/uvicorn app.main:app --reload --app-dir backend
```

> 无 root、也无法用 Docker 时，可像 `tools/pgctl.sh` 那样从 `postgresql-15` 的 deb 包解包出
> 便携版 PostgreSQL（默认监听 `127.0.0.1:55433`，socket 放在 `tools/pgrun`），再用
> `DT_DATABASE_URL=postgresql+psycopg://downtime:downtime@127.0.0.1:55433/downtime` 连接。
> `tools/` 下的运行时与数据目录已在 `.gitignore` 中忽略。

前端：

```bash
cd frontend
npm install
npm run dev
```

## 主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/lines` `/api/equipments?line_id=` `/api/reasons` | 基础数据 |
| GET | `/api/events` | 事件列表（分页/筛选） |
| POST | `/api/events` | 登记事件 |
| GET | `/api/events/{id}` | 事件详情（含 5 Whys、措施） |
| PATCH | `/api/events/{id}` | 修改/状态流转 |
| PUT | `/api/events/{id}/analysis` | 提交/更新 5 Whys |
| POST/PATCH/DELETE | `/api/events/{id}/actions[/{aid}]` | 改善措施 CRUD |
| GET | `/api/analytics/pareto` | 原因聚合帕累托数据 |

## 说明 / 后续可扩展

- 认证与按角色（操作工/班组长）权限控制、审计日志暂未实现。
- 停机时长以登记值为准；开始/结束时间可后补。
- 后续可加：按班次/设备维度分析、停机趋势、措施超期提醒、导出报表。
