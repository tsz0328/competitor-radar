# 竞品雷达

> 🚀 监控同类 SaaS / App 官网与公开可 Diff 数据源的 AI 竞品情报系统。

## 📖 项目简介

竞品雷达 锁定「**监控同类型 SaaS / App 的官网与公开可 Diff 的数据源**」这一方向：持续抓取竞品官网首页、定价页、更新日志、博客、帮助文档、状态页、RSS 与应用商店页，用**快照 Diff** 找出「页面变了什么」，再由 LLM 翻译成「**这件事意味着什么**」，以情报事件、周报、趋势洞察的形式主动呈现。

传统竞品分析依赖人工刷网站、截图、写报告，效率低且容易遗漏重要更新。本项目用「自动采集 → 差异对比 → AI 解读 → 主动呈现」这条链路替代人工巡检。

### 数据源白名单（v1）

| 类型 | 说明 | 抓取方式 | 默认频率 |
|---|---|---|---|
| 官网首页 / 定价页 | 品牌与价格体系变动 | 浏览器渲染 | 每天 |
| 更新日志 / Changelog | 新版本、新功能 | 浏览器渲染 | 每天 |
| 官方博客 / RSS | 官方文章发布 | HTTP / RSS | 每天 ~ 每小时 |
| 帮助文档 | 文档内容变更 | 浏览器渲染 | 每周 |
| 服务状态页 | 故障与维护公告 | HTTP | 每小时 |
| 应用商店页 | 版本更新与评分 | 浏览器渲染 | 每天 |

**明确不做（v1）**：任何需登录、需破解接口签名、平台 ToS 禁止的数据源。**电商商品对标**（淘宝 / 京东 / 拼多多 / 抖音的价格、销量、评论）不在 v1 范围内，v2 仅以「数据源插件」形式接入公开可得、可 Diff 的数据源。详见 [`docs/positioning.md`](docs/positioning.md)。

---

## ✨ 功能特性

- 🔍 自动监控竞品官网及指定页面
- 🤖 AI 自动生成变化摘要
- 📊 历史版本 Diff 对比
- 📈 趋势分析与可视化
- 📄 AI 自动生成周报
- ⏰ 定时任务自动执行（进程内 APScheduler，按每个页面自己的频率抓取）
- 📬 异动与周报推送（可选，支持日志 / 邮件两种后端）

---

## 🏗️ 技术栈

### Frontend

- Vue 3
- TypeScript
- Vite
- Element Plus
- Pinia
- Axios
- ECharts

### Backend

- FastAPI
- SQLAlchemy 2.0
- Pydantic
- JWT Authentication

### Database

- MySQL
- Redis

### AI

- LLM API（OpenAI Compatible Interface）
- DeepSeek
- Qwen

### Crawler

- Playwright
- Trafilatura

### Deployment

- Docker
- Docker Compose
- Nginx

---

## 📂 项目结构

```text
竞品雷达
│
├── backend/                 # FastAPI 后端
│
├── frontend/                # Vue3 前端
│
├── docs/                    # 项目文档
│   └── architecture.md
│
├── README.md
├── LICENSE
└── .gitignore
```

---

## 🚀 快速开始

### 克隆项目

```bash
git clone https://github.com/yourname/competitor-radar.git

cd competitor-radar
```

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # macOS / Linux；Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # SPA 官网渲染兜底所需的内核（不装只走 httpx）
cp .env.example .env             # 按需修改 JWT_SECRET / LLM_API_KEY
python run_dev.py                # 开发启动（带热重载）
```

启动后访问 <http://localhost:8000/docs> 查看接口文档（SQLite 表会自动创建）。

> 为什么用 `run_dev.py` 而不是 `uvicorn --reload`：Windows 下 `uvicorn --reload`
> 会让 uvicorn>=0.36 启用 SelectorEventLoop，而它**不支持创建子进程**，
> Playwright 驱动起不来、渲染兜底静默失效（报"未提取到有效正文"）。
> `run_dev.py` 只是显式换成 ProactorEventLoop，其余行为一致；非 Windows 平台无差别。

### 前端

```bash
cd frontend
npm install
npm run dev
```

启动后访问 <http://localhost:5173>（`/api` 已代理到 `http://localhost:8000`）。

### 一键部署（Docker Compose）

不想配本地环境的话，一条命令起全部（MySQL + Redis + 后端 + 前端）：

```bash
cp .env.example .env             # 可选：改掉默认密码与 JWT_SECRET
docker compose up --build
```

| 地址 | 说明 |
|---|---|
| http://localhost:8080 | 前端页面（Nginx 托管） |
| http://localhost:8080/docs | 接口文档（Nginx 反代到后端） |

生产要点：

- **表结构由 Alembic 管理**：后端容器入口自动执行 `alembic upgrade head`（`DB_AUTO_CREATE=false`）；开发期仍是启动时 `create_all`，两条路径建出的表结构一致（已验证）
- **只有前端容器对外暴露端口**，MySQL / Redis / 后端都只在 compose 内部网络里，外面摸不到
- **后端可横向扩容**：`docker compose up --scale backend=2`——多个副本通过 Redis 分布式锁（`CACHE_BACKEND=redis`）保证同一批到期的页面只被一个实例抓取
- **定时任务随应用启动**：APScheduler 按每个监控页自己的频率抓取，每周一 06:00 自动生成周报；`GET /api/scheduler` 可看下次执行时间

---

## 📌 开发计划

- [x] 项目规划
- [x] 技术方案设计
- [x] 项目目录初始化
- [x] FastAPI 后端初始化（路由 / 配置 / 异步 ORM / `/docs` 可用）
- [x] Vue3 前端初始化（路由 / Pinia / Element Plus / 业务页面骨架）
- [x] 用户认证模块（注册 / 登录 / JWT 鉴权 + 前端路由守卫）
- [x] 竞品管理模块（CRUD + 监控源配置 + 图标多级回退 + 手动抓取）
- [x] 爬虫采集（httpx + trafilatura + feedparser，快照 + Diff）
- [x] AI 分析模块（LLM 统一层 + 事件分类摘要，无 Key 走规则兜底）
- [x] 趋势分析与周报（趋势洞察 + 周报生成与列表/详情）
- [x] Dashboard / 事件流 / AI 报告 / 趋势分析页面接真实接口
- [x] 任务调度（APScheduler 进程内调度：按各源频率自动抓取 + 每周自动生成周报）
- [x] 通知推送（可选，默认关闭；支持日志 / 邮件后端）
- [x] Playwright 渲染兜底（SPA 官网可抓；静态页仍走 httpx 毫秒级返回）
- [x] Docker 部署（compose 一键起 MySQL/Redis/后端/Nginx + Alembic 迁移）

---

## 📚 项目文档

详细设计与定位文档：

```text
docs/positioning.md         # 产品定位：目标用户 / 核心场景 / 数据源白名单与黑名单
docs/architecture.md        # 技术方案：架构 / 数据模型 / API 清单
docs/data-source-design.md  # 数据源抽象：source_type 注册表与策略接口
docs/milestones.md          # 里程碑与执行清单
docs/page-design.md         # 首页设计
```

---

## 📅 Roadmap

### v1.0（进行中）

- 用户系统与竞品管理
- 官网与公开数据源自动抓取（快照 + Diff）
- AI 事件分析（功能更新 / 价格变化 / 内容更新 / 舆论动态 / 其他）
- 情报事件流、周报生成、趋势洞察
- 定时调度与邮件推送

### v2.0

- **电商等新数据源以「数据源插件」形式接入**：扩展 `source_type` 注册表（Shopify 商品页、App Store 与 Google Play 公开 RSS/榜单、Amazon PA-API / 京东联盟等官方开放平台 API）。只接入公开可得、可 Diff 的数据源，不绕过登录、不破解签名
- 多用户协作与团队空间
- LangGraph 多 Agent 分析
- 向量数据库，支持「过去某竞品做过哪些价格调整」这类语义检索

---

## 📄 License

本项目基于 MIT License 开源。

---

## ⭐ 项目状态

✅ v1 核心链路已跑通并端到端实测：配置竞品 → 定时抓取 → 快照 Diff → 情报事件 → 周报/趋势 → 一键部署。SPA 官网由 Playwright 兜底渲染。
🚧 仍在路上：v2 数据源插件（电商商品等以插件形式接入）。

欢迎 Star、Issue 和交流讨论。