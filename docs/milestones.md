# AI 竞品情报雷达 — 里程碑计划（Milestones）

> 版本：v1.2　作者：唐思哲　更新日期：2026-07-19
> 配套文档：`README.md` / `docs/architecture.md`（技术方案）/ `docs/page-design.md`（首页设计）
> 说明：本文件按**从零搭建的执行顺序**组织里程碑（初始化 → 前端脚手架 → 后端脚手架 → 各业务模块），便于一步步推进与勾选验收。

---

## 〇、已确认的关键决策（地基约束）

| 决策项 | 选择 | 对代码的影响 |
|---|---|---|
| 开发期数据库 | **SQLite + 内存缓存** | 数据层必须 **DB 无关**；生产切 MySQL+Redis 只改连接串 |
| 缓存 | 开发期用进程内内存字典；预留 Redis 实现 | `core/cache.py` 提供 `MemoryCache` / `RedisCache` 两种后端，按配置切换 |
| LLM 接入 | **统一调用层 + 无 Key 的 Mock 兜底** | `core/llm.py` 抽象一个 `LLMClient`，有 Key 走真实 API，无 Key 走规则/Mock，整条流程可跑通 |
| 构建顺序 | **前端先行** | Home 落地页不依赖后端，作为第一刀切入口 |

### DB 无关设计要点（务必遵守，否则切 MySQL 会返工）
- 主键：`BigInteger` 自增（SQLite/MySQL 通用），不要依赖 SQLite 的 `INTEGER` 自增特性。
- JSON 字段：用 `sqlalchemy.JSON`（SQLAlchemy 2.0 在 SQLite 存 TEXT、MySQL 存 JSON，均透明）。
- 枚举字段（`status` / `event_type` / `trend_direction`）：用 `sqlalchemy.Enum(..., native_enum=False)`，存为 `VARCHAR`，两套库都兼容。
- 时间字段：`DateTime(timezone=True)` + `server_default=func.now()`，统一用 Aware datetime。
- 索引：`page_snapshots(competitor_id, crawled_at)`、`content_hash`、`intelligence_events(competitor_id, created_at)` 联合索引。
- 建表方式：开发期 `Base.metadata.create_all(engine)`；生产用 Alembic 迁移（里程碑 11）。

---

## 一、目标目录结构

```text
AI-COMPETITOR-RADAR
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI 入口：CORS、挂载路由、启动事件建表
│   │   ├── core/
│   │   │   ├── config.py           # pydantic-settings 读 .env（DB_URL / JWT / LLM / 缓存）
│   │   │   ├── database.py         # 异步 engine + session 工厂（DB 无关）
│   │   │   ├── security.py         # 密码哈希(bcrypt) + JWT 签发/校验
│   │   │   ├── cache.py            # MemoryCache / RedisCache 抽象
│   │   │   └── llm.py              # LLMClient 抽象 + Mock 兜底
│   │   ├── models/                 # SQLAlchemy 模型（6 张表）
│   │   │   ├── user.py
│   │   │   ├── competitor.py
│   │   │   ├── snapshot.py
│   │   │   ├── event.py
│   │   │   ├── weekly_report.py
│   │   │   └── trend.py
│   │   ├── schemas/                # Pydantic 请求/响应模型
│   │   │   ├── user.py
│   │   │   ├── competitor.py
│   │   │   ├── event.py
│   │   │   ├── report.py
│   │   │   └── trend.py
│   │   ├── api/
│   │   │   ├── deps.py             # get_current_user / get_db 依赖
│   │   │   ├── auth.py             # /api/auth/register|login
│   │   │   ├── competitors.py      # /api/competitors CRUD + 手动抓取
│   │   │   ├── events.py           # /api/events 列表/详情 + SSE(可选)
│   │   │   ├── reports.py          # /api/reports 列表/详情/手动生成
│   │   │   └── trends.py           # /api/trends/{id} 与 chart 数据
│   │   ├── services/
│   │   │   ├── crawler.py          # Playwright 抓取 + trafilatura 提取正文
│   │   │   ├── analyzer.py         # Diff 粗筛 → LLM 分类+摘要 → 写事件
│   │   │   ├── trend.py            # 聚合历史事件 → LLM 趋势判断
│   │   │   ├── report.py           # 周报聚合生成
│   │   │   └── scheduler.py        # APScheduler 定时任务（里程碑 10）
│   │   └── seed.py                 # 可选：造 demo 数据
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── tests/
│
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── env.d.ts
│       ├── router/index.ts         # 路由 + 登录守卫
│       ├── api/                     # axios 实例(拦截器带 Token) + 各模块
│       │   ├── request.ts
│       │   ├── authApi.ts
│       │   ├── competitorApi.ts
│       │   ├── eventApi.ts
│       │   ├── reportApi.ts
│       │   └── trendApi.ts
│       ├── store/                   # Pinia：user / competitor / event
│       ├── layouts/                 # 基础布局 / 带侧边栏后台布局
│       ├── views/
│       │   ├── Home.vue             # 产品首页(landing, 按 page-design.md)
│       │   ├── Login.vue
│       │   ├── Dashboard.vue        # 数据概览 + ECharts 趋势图
│       │   ├── Competitors.vue      # 竞品 CRUD
│       │   ├── Events.vue           # 事件流时间轴
│       │   ├── Reports.vue          # 周报/趋势
│       │   └── Settings.vue
│       ├── components/              # EventCard / TrendChart / StatCard 等
│       └── utils/
│
├── docs/  (architecture.md / page-design.md / milestones.md 本文件)
├── docker-compose.yml              # 里程碑 11：FastAPI+MySQL+Redis+Nginx+前端
├── README.md
├── LICENSE
└── .gitignore
```

---

## 二、里程碑总览（按执行顺序）

| # | 里程碑 | 目标 | 关键产出 | 完成标志 |
|---|---|---|---|---|
| 1 | **初始化项目** | 仓库与文档骨架就绪 | `.gitignore` / `LICENSE` / `README` / `docs/` | 仓库结构清晰、文档齐全（✅ 已基本完成） |
| 2 | **搭建前端脚手架** | Vue3 工程可运行 | Vite+TS 配置、路由、Pinia、Element Plus、Axios 封装 | `npm run dev` 起首页占位，Element Plus+路由+Pinia 生效 |
| 3 | **搭建后端脚手架** | FastAPI 工程可运行 | 入口/配置层/DB 无关层/缓存抽象/6 张表模型 | `uvicorn` 起服务，`/docs` 可见，表自动生成 |
| 4 | **用户认证模块** | 注册/登录拿到 JWT | 后端 `auth` 接口 + 前端登录流 + `request.ts` 拦截器 | 登录拿 JWT，受保护接口可访问 |
| 5 | **竞品管理模块** | 竞品增删改查闭环 | 后端 `competitors` CRUD + 前端管理页 | 前端能增删改查竞品 |
| 6 | **爬虫采集模块** | 能抓页面、比对变化 | Playwright 爬虫 + 快照/Diff + 手动触发接口 | 手动抓取产生快照；无变化不重复 |
| 7 | **AI 分析模块（事件）** | 变化→结构化情报 | `llm.py` + `analyzer` 服务 + `events` 接口 | 抓取变化后 `intelligence_events` 有记录 |
| 8 | **趋势分析与周报** | 聚合历史生成洞察 | `trend.py` + `report.py` + 对应接口 | `trends` / `reports` 可查 |
| 9 | **前端业务页面** | 完整可用人机界面 | Dashboard/事件流/周报页 + 首页完善 | 前后端联调，趋势图、事件流可见 |
| 10 | **任务调度与推送** | 自动化运行 | APScheduler + 邮件(可选) | 启动后按频率自动抓取并产生事件 |
| 11 | **Docker 部署与打磨** | 一键上线 | docker-compose + Nginx + 文档 | `docker-compose up` 起全部服务 |

---

## 三、各里程碑详细任务清单（可勾选）

### 里程碑 1：初始化项目（✅ 基本完成）
- [x] Git 仓库初始化（`.git` 已存在）
- [x] `.gitignore` 完善（覆盖 Python/Node/SQLite/Playwright/密钥/`.workbuddy/` 等）
- [x] `LICENSE`（MIT）
- [x] `README.md`（项目简介 + 技术栈 + 开发计划）
- [x] `docs/architecture.md`（技术方案）、`docs/page-design.md`（首页设计）、`docs/milestones.md`（本文件）

### 里程碑 2：搭建前端脚手架（✅ 已完成）
- [x] **配置层**：`package.json` / `vite.config.ts`(`@` 别名 + `/api` 代理) / `tsconfig.json` / `index.html` / `env.d.ts`
- [x] **应用入口与外壳**：`main.ts`（挂 Pinia/Router/Element Plus）、`App.vue`（`<router-view/>`）、`router/index.ts`（Home/Login 路由）
- [x] **占位页验证**：`views/Home.vue`、`views/Login.vue`（验证 Element Plus + 路由生效）
- [x] **前端目录规范落地**：`api/`(集中接口) / `stores/`(Pinia) / `layouts/` / `components/` / `types/`
- [x] **运行验证**：`npm install` → `npm run dev` 跑通；Landing / Login / Dashboard / 竞品管理 / 情报事件 / AI 报告 / 趋势分析页面均已实现
> 当前进度：前端目录与业务页面已全部落地。注意：各页面目前读的是 `frontend/mock/*.ts` 的**假数据**，**尚未接后端**——等后端接口就绪后再关掉 mock 做联调。

### 里程碑 3：搭建后端脚手架（🔧 进行中）
> 推进方式：后端与前端一致，改为**手写教学推进**（代码即学即写）。已落地内容如下。

- [x] **3.1 入口**：`app/main.py` 起 FastAPI，`/docs` 可访问；已挂 `CORSMiddleware`（允许的来源从配置读，默认 `http://localhost:5173`）。
- [x] **3.2 配置层**：`core/config.py` 用 pydantic-settings 读 `backend/.env`，`Settings` + `get_settings()` 单例；已接管 `DB_URL` / `JWT_SECRET` / `JWT_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` / `CORS_ORIGINS`，代码内不再有硬编码密钥。同时提供 `.env.example`（可提交）与 `.env`（已被 `.gitignore` 忽略）。
  - 验证方式：改 `.env` 的 `DB_URL` 后重启，会按新文件名生成数据库（如 `test_config.db`），证明配置确实生效。
- [x] **3.3 DB 无关层**：`core/database.py` 异步 engine + `get_db` 依赖 + `init_db()`；`Base.metadata.create_all` 在 lifespan 启动事件建表。
- [ ] **3.4 缓存抽象**：`core/cache.py` 实现 `MemoryCache`；预留 `RedisCache`（按 `CACHE_BACKEND` 切换）。
- [x] **3.5 安全**：`core/security.py` 密码 bcrypt 哈希（`hash_password` / `verify_password`）+ JWT 签发/校验（`create_access_token` / `decode_access_token`）。
- [x] **3.6 数据模型**：已落地 3 张表并通过 SQLite 验证 —— `models/user.py`（`users`）、`models/competitor.py`（`competitors`）、`models/source.py`（`monitor_sources`）；`models/base.py` 提供 `Base` / `BigIntPK`（`with_variant` 解决 SQLite 自增）/ `enum_values`（枚举存 `.value`）/ `TimestampMixin`。**其余 4 张表（page_snapshots / intelligence_events / weekly_reports / trend_insights）随里程碑 6-8 补齐**，建表时严格遵守"DB 无关要点"与 `docs/data-source-design.md`。
  - 配套：`core/source_registry.py` 数据源注册表（8 种 v1 类型：`RenderMode` / `SourceType` / `SourceTypeConfig`）—— 爬虫模块的唯一策略来源，也是 v2 新增数据源的扩展点。
- [x] **3.7 Schemas**：`schemas/user.py`（`UserCreate` / `UserOut` / `UserLogin` / `TokenOut`），后续按业务模块扩展。
- [x] **3.8 运行验证**：`uvicorn app.main:app --reload --reload-dir app` 启动正常，`/docs` 可访问，`dev.db` 与 `users` 表自动生成。

> **踩坑记录（防复发）**
> 1. Windows 必须加 `--reload-dir app`：否则 watchfiles 会扫描 `.venv`（数万文件）导致事件循环卡死，表现为"启动成功但一直转圈"。
> 2. SQLite 只有 `INTEGER PRIMARY KEY` 才会自增：直接用 `BigInteger` 建表会报 `NOT NULL constraint failed: users.id`，已用 `BigInteger().with_variant(Integer, "sqlite")` 解决。
> 3. 表结构变更后必须删 `dev.db` 重启：SQLite 不允许改主键类型（开发期直接删库重建，生产用 Alembic，见里程碑 11）。

### 里程碑 4：用户认证模块（🔧 进行中）
- [x] **4.1 后端**：已实现并全部通过 `/docs` 验证 ——
  - `POST /api/users` 注册（密码经 bcrypt 哈希后存储，用户名重复返回 **400**）
  - `GET /api/users` 列表、`GET /api/users/{id}` 详情（不存在返回 **404**）
  - `POST /api/auth/login` 登录（校验密码 → 签发 JWT）
  - `GET /api/auth/me` 受保护接口（`HTTPBearer` 取令牌 → 验签 → 返回当前用户；无效/过期返回 **401**）
  - 补：`api/deps.py` 已抽出 `get_current_user` 依赖（解析 Bearer 令牌 → 查用户 → 失败 401），`/api/auth/me` 与竞品接口均复用它。
- [ ] **4.2 前端接口层**：`api/request.ts`（axios 实例 + 拦截器自动带 Token + 统一错误处理）已具备；`api/authApi.ts` 待与后端路径对齐。
- [ ] **4.3 前端状态**：`stores/user.ts`（存 token / 用户信息）。
- [ ] **4.4 前端登录流**：完善 `Login.vue`；`router` 加登录守卫（未登录跳 `/login`）。
- [ ] **验收**：注册→登录拿 JWT→访问受保护接口成功（**后端链路已通过 `/docs` 验收**，待前端联动后整体验收）。

### 里程碑 5：竞品管理模块
- [x] **5.1 后端**：`api/competitors.py` 已实现 `POST /api/competitors`（201）、`GET /api/competitors`、`GET/PATCH/DELETE /api/competitors/{id}`（删除 204）；全部经 `api/deps.py` 的 `get_current_user` 鉴权，并按 `user_id` 隔离（查不到/不属于自己一律 404）。已在 `/docs` 验证，并用第二个账号验证数据隔离（返回 `[]`）。
- [ ] **5.2 前端**：`api/competitorApi.ts` + `store/competitor.ts` + `views/Competitors.vue`（CRUD + 配置监控 URL/频率）。
- [ ] **验收**：前端能增删改查竞品，数据来自后端。

### 里程碑 6：爬虫采集模块
- [ ] **6.1 爬虫服务**：`services/crawler.py` Playwright 访问 URL，trafilatura 提取正文，去噪。
- [ ] **6.2 快照存储**：写 `page_snapshots`，算 `content_hash`，存 `clean_text`（原始 HTML 存 `backend/storage/`，已加入 `.gitignore`）。
- [ ] **6.3 Diff 比对**：与上次快照 hash 比对；变化则存 diff 文本（difflib）。
- [ ] **6.4 手动触发接口**：`POST /api/competitors/{id}/crawl`。
- [ ] **6.5 失败重试/频率控制**：随机延迟、重试、UA 设置。
- [ ] **验收**：加竞品→手动抓取→`page_snapshots` 有记录；再次抓未变则无新快照/无新事件。

### 里程碑 7：AI 分析模块（事件）
- [ ] **7.1 LLM 抽象**：`core/llm.py` `LLMClient`；有 Key 走 API（DeepSeek/通义/OpenAI 兼容），无 Key 走 Mock 规则生成合理文本。
- [ ] **7.2 事件分类+摘要**：`services/analyzer.py` 用 Diff 粗筛→只对显著变化调 LLM→写 `intelligence_events`（type/summary/confidence）。
- [ ] **7.3 接口**：`api/events.py` 列表/详情 + SSE 实时推送（可选）。
- [ ] **验收**：抓到变化页面后事件有记录（Mock 也能生成摘要）。

### 里程碑 8：趋势分析与周报
- [ ] **8.1 趋势分析**：`services/trend.py` 聚合历史事件统计→LLM 趋势判断→`trend_insights`。
- [ ] **8.2 周报生成**：`services/report.py` 聚合一周事件→LLM 周报（Markdown）→`weekly_reports`。
- [ ] **8.3 接口**：`/api/trends/{id}`、`/api/trends/{id}/chart`、`/api/reports`、`/api/reports/generate`。
- [ ] **验收**：`trends` / `reports` API 返回数据。

### 里程碑 9：前端业务页面
- [ ] **9.1 首页完善**：按 `page-design.md` 实现 Navbar/Hero/Features/Workflow/Preview/Footer。
- [ ] **9.2 Dashboard**：统计卡片 + ECharts 趋势图（封装 `TrendChart` 组件）。
- [ ] **9.3 竞品管理页**：接里程碑 5 的接口与页面。
- [ ] **9.4 事件流**：时间轴 `EventCard` 复用。
- [ ] **9.5 周报/趋势页**：历史回看。
- [ ] **9.6 后台布局**：`layouts/AppLayout.vue`（侧边栏 + 菜单）。
- [ ] **验收**：前后端联调，事件流、趋势图、周报均可视。

### 里程碑 10：任务调度与推送
- [ ] **10.1 APScheduler 集成**：按竞品频率错峰定时抓取（进程内，不引 Celery）。
- [ ] **10.2 邮件推送（可选）**：SMTP 配置，异动/周报推送。
- [ ] **验收**：启动后自动按频率抓取并产生事件。

### 里程碑 11：Docker 部署与打磨
- [ ] **11.1 Alembic 迁移**：生产用迁移而非 `create_all`。
- [ ] **11.2 docker-compose**：FastAPI + MySQL + Redis + Nginx + 前端静态，统一一套配置。
- [ ] **11.3 README/架构图/文档完善**。
- [ ] **验收**：`docker-compose up` 一键起全部。

---

## 四、核心抽象接口草稿（提前定调，避免返工）

```python
# core/llm.py —— 统一调用层，Mock 兜底
class LLMClient:
    def __init__(self, cfg): ...
    async def classify_and_summarize(self, old: str, new: str) -> dict:
        """返回 {event_type, summary, confidence}，无 Key 时返回规则生成结果"""
    async def trend_judgment(self, stats: dict, history: list) -> str: ...
    async def weekly_report(self, events: list) -> str: ...

# core/cache.py —— 缓存后端可切换
class Cache(Protocol):
    def get(self, k): ...
    def set(self, k, v, ttl=None): ...
# MemoryCache（开发） / RedisCache（生产，按 CACHE_BACKEND 选）
```

---

## 五、执行建议

1. 当前位于**里程碑 3（后端脚手架，剩 3.2 配置层 / 3.4 缓存抽象）→ 里程碑 4（用户认证，后端已通、待前端联动）**。
2. 每完成一个里程碑，用"完成标志"核对，跑通再进下一个。
3. 建议按"认证→竞品→采集→AI→趋势/周报→前端业务页"的顺序端到端推进，每个模块都做前后端联调。
4. 阶段一的最小可运行闭环（登录 + 竞品列表）是后续一切的前提，优先打磨稳定。
5. 前后端均采用**手写教学推进**：后端与前端一样逐文件手写，每步可运行、可验证，不采用一次性脚手架生成。
6. 方向边界以 `docs/positioning.md` 为准（只做 SaaS/App 官网与公开可 Diff 数据源，电商商品 v1 不做）；数据源抽象以 `docs/data-source-design.md` 为准。

---

## 六、附录：工具快速搭建命令速查（备选）

> 本项目当前采用 **「手写」模式**以下命令仅作为**想快速起脚手架时的备选方案**，非当前执行项。注意：工具生成的代码均不含业务/配置细节（Element Plus、Router、Pinia、DB 模型等都需后续补），且常带 demo 文件需清理。

### 6.1 前端（Vue3 + TS + Vite）

**方案 A：Vite 官方模板（轻量，不带 Router/Pinia/Element Plus）**
```bash
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm install
# 再补业务需要的库（脚手架不带这些）
npm i element-plus @element-plus/icons-vue pinia vue-router axios echarts
```
> `--template vue-ts` 给 Vue3+TS 标准配置，但不含 Router/Pinia/Element Plus，需后续自己加。

**方案 B：create-vue（官方推荐，可交互勾选 Router/Pinia/ESLint）**
```bash
npm create vue@latest frontend
# 交互式选择 TS / Router / Pinia / ESLint / Vitest；非交互一键：
npm create vue@latest frontend -- --typescript --router --pinia --eslint --vue-router
```

### 6.2 后端（FastAPI）

⚠️ **FastAPI 没有官方 `create` 命令**，分三档：

**档 1：最轻（装包 + 手写 main.py，最接近本项目手写路子）**
```bash
pip install fastapi "uvicorn[standard]" sqlalchemy pydantic email-validator
```

**档 2：社区脚手架 fastapi-mvc（按 MVC 分层生成目录）**
```bash
pip install fastapi-mvc
fastapi-mvc create my-project
```

**档 3：官方全栈模板（cookiecutter，很重：自带前端 + PostgreSQL + Docker + 认证）**
```bash
pipx install cookiecutter
cookiecutter https://github.com/tiangolo/full-stack-fastapi-template
```

### 6.3 工具脚手架 vs 手写（本项目当前手写）

| 对比 | 工具脚手架 | 手写（当前选的） |
|---|---|---|
| 配置稳妥度 | 高（官方调好的） | 中（稳但需仔细） |
| 冗余文件 | 有 demo 要删 | 零冗余 |
| 业务代码 | 都不生成 | 全自己写 |
| 学习价值 | 低（黑盒生成） | 高（每行都懂） |

