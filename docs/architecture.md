# 竞品雷达 — 技术方案文档

> 版本：v1.0　作者：唐思哲　更新日期：2026-06

---

## 一、项目概述

### 1.1 项目背景

产品经理、创业团队在做竞品分析时，普遍依赖人工刷网站、截图、写报告，效率低、易遗漏、无法及时发现竞品的细微变化（新功能上线、定价调整、用户口碑变化）。

### 1.2 项目目标

构建一个**自动化竞品情报系统**：系统定时抓取指定竞品的官网/更新日志/用户评论等公开信息，通过 AI 提炼关键变化，生成结构化情报报告，并主动推送给用户，而不是等用户来问。

### 1.3 核心价值主张

| 痛点 | 系统解法 |
|---|---|
| 人工刷网站耗时 | 定时任务自动抓取 |
| 信息零散难提炼 | AI 自动摘要 + 关键变化提取 |
| 不知道"变了什么" | 历史快照对比，自动生成 Diff |
| 被动查询 | 主动推送周报/异动提醒 |

### 1.4 不做什么（边界）

- **不做电商商品对标**：淘宝 / 京东 / 拼多多 / 抖音等平台的价格、销量、评论不在 v1 范围内（需登录、接口签名与平台 ToS 均构成硬约束）。v2 仅以「数据源插件」形式接入**公开可得、可 Diff** 的数据源（DTC 独立站 / Shopify 商品页、App Store 与 Google Play 公开 RSS 与榜单、Amazon PA-API / 京东联盟等官方开放平台 API），不绕过登录、不破解签名
- **不做需登录 / 需破解签名 / ToS 明确禁止的数据源**。v1 白名单与黑名单详见 `docs/positioning.md`；白名单即：官网首页、定价页、更新日志、官方博客、帮助文档、服务状态页、RSS、应用商店页
- 不做付费数据源接入（如天眼查 API），第一版只做公开网页信息
- 不做情感分析模型自研，直接调用大模型能力
- 不做多用户 SaaS 化（第一版单用户/小团队即可）

---

## 二、整体架构

### 2.1 架构分层图

```
┌─────────────────────────────────────────────────┐
│                   前端展示层                      │
│   Vue3 + TypeScript + Element Plus + ECharts     │
│   Dashboard / 竞品管理 / 报告详情 / 趋势图          │
└───────────────────┬───────────────────────────────┘
                     │ HTTP / SSE
┌───────────────────▼───────────────────────────────┐
│                  后端服务层（FastAPI）              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 用户认证  │ │竞品管理API│ │  报告查询/推送API  │  │
│  │  (JWT)   │ │  (CRUD)  │ │                   │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
└───────────────────┬───────────────────────────────┘
                     │
       ┌─────────────┼─────────────────┐
       ▼             ▼                 ▼
┌────────────┐ ┌────────────┐  ┌─────────────────┐
│  采集层     │ │  AI分析层   │  │  任务调度层       │
│ Playwright │ │ 直接调用LLM │  │ APScheduler /    │
│ 爬虫引擎    │ │ API + Pydantic│ Celery（后期）     │
│ 反爬策略    │ │ 摘要/对比   │  │ 定时触发抓取任务   │
└─────┬──────┘ └─────┬──────┘  └─────────────────┘
      │              │
      ▼              ▼
┌─────────────────────────────────────────┐
│              数据存储层                   │
│  MySQL（结构化数据）+ Redis（缓存/队列）    │
│  本地文件/对象存储（网页快照、截图）         │
└─────────────────────────────────────────┘
```

### 2.2 数据流向（一次完整抓取-分析-推送流程）

```
定时任务触发
    ↓
Playwright 访问竞品页面 → 抓取 HTML/文本
    ↓
清洗结构化（去广告、去导航栏，提取正文）
    ↓
存入数据库（带时间戳的快照）
    ↓
与上一次快照做 Diff 对比（文本相似度算法）
    ↓
若有显著变化 → 调用 LLM 生成摘要 + 分类（功能更新 / 价格变化 / 内容更新 / 舆论动态 / 其他）
    ↓
写入"情报事件"表
    ↓
定时（每周）汇总所有事件 → LLM 生成周报
    ↓
周期性聚合历史事件 → 统计变化频率/类型分布 → LLM 生成趋势判断
    ↓
前端展示 / 邮件推送
```

---

## 三、技术栈选型与理由

| 层级 | 技术选型 | 选型理由 |
|---|---|---|
| 前端框架 | Vue3 + TypeScript | 已有基础，可复用 |
| UI 组件库 | Element Plus | 已用过，开发效率高 |
| 图表 | ECharts | 已用过，适合做趋势图 |
| 状态管理 | Pinia | 已用过 |
| 后端框架 | FastAPI | 异步性能好，自动生成 API 文档，AI 生态原生支持 |
| ORM | SQLAlchemy 2.0（异步） | Python 后端标准选型 |
| 数据校验 | Pydantic | FastAPI 强依赖，类型安全 |
| 数据库 | MySQL 8.0 | 已有基础，结构化数据存储 |
| 缓存/队列 | Redis | 缓存抓取结果、任务队列、Session |
| 爬虫引擎 | Playwright（Python） | 支持动态渲染页面，比 requests/BeautifulSoup 更适合现代网站 |
| AI 调用方式 | 直接调用 LLM API + Pydantic 结构化输出 | 核心逻辑（摘要/分类）较简单，重型框架的抽象层会增加不必要的调试成本，详见后文说明 |
| Agent 编排（V2） | LangGraph | 多Agent协作场景才需要的状态化编排，是当前招聘JD最高频要求的Agent框架 |
| 大模型 API | 可选：通义千问 / DeepSeek / OpenAI 兼容接口 | 国内访问稳定、成本低 |
| 向量数据库 | Chroma（本地） | 轻量，适合存储历史报告做语义检索（V2功能） |
| 定时任务 | APScheduler | 第一版够用，比 Celery 轻量 |
| 鉴权 | JWT | 已有经验，直接复用 |
| 容器化 | Docker + Docker Compose | 一键启动全部依赖服务 |
| 部署 | 云服务器（轻量应用服务器即可）+ Nginx | 成本可控 |

---

## 四、数据库设计

### 4.1 核心表结构

**用户表 `users`**
```sql
id              BIGINT PRIMARY KEY AUTO_INCREMENT
username        VARCHAR(50) UNIQUE NOT NULL
password_hash   VARCHAR(255) NOT NULL
email           VARCHAR(100)
created_at      DATETIME
```

**竞品表 `competitors`**
```sql
id              BIGINT PRIMARY KEY AUTO_INCREMENT
user_id         BIGINT           -- 所属用户
name            VARCHAR(100)     -- 竞品名称
official_url    VARCHAR(255)     -- 官网地址
category        VARCHAR(50)      -- 行业分类（同类 SaaS / App）
status          ENUM('active','paused')
created_at      DATETIME
```

> 说明：早期设计里的 `monitor_urls`（JSON 页面名数组）**已废弃**——无结构 JSON 无法承载「页面类型 / 频率 / 渲染方式 / Diff 策略」，由下面的 `monitor_sources` 表取代。

**监控源表 `monitor_sources`**（竞品身上一个具体要盯的页面）
```sql
id                  BIGINT PRIMARY KEY AUTO_INCREMENT
competitor_id       BIGINT          -- 所属竞品
source_type         VARCHAR(30)     -- homepage|pricing|changelog|blog|docs|status|rss|app_store
name                VARCHAR(100)    -- 展示名，如「定价页」
url                 VARCHAR(1024)
render_mode         VARCHAR(10)     -- browser|http（建源时冗余，避免注册表变更后历史数据语义漂移）
interval_minutes    INT
enabled             BOOLEAN
last_crawled_at     DATETIME
last_status         VARCHAR(10)     -- success|failed
last_error          TEXT
fail_count          INT             -- 连续失败次数，达阈值自动停用该源
created_at          DATETIME
```

**网页快照表 `page_snapshots`**（一次抓取记录：抓到了什么、有没有变化）
```sql
id              BIGINT PRIMARY KEY AUTO_INCREMENT
competitor_id   BIGINT
source_id       BIGINT         -- 归属监控源（失败记录同样留痕）
source_type     VARCHAR(30)
url             VARCHAR(1024)
raw_html_path   VARCHAR(255)   -- 原始HTML存储路径（文件系统/对象存储）
clean_text      TEXT           -- 清洗后的正文
content_hash    VARCHAR(64)    -- 内容哈希，用于快速判断是否变化
http_status     INT
is_success      BOOLEAN
fail_reason     TEXT
change_detected BOOLEAN        -- 相比上次基准是否变化
diff_text       TEXT           -- difflib 差异，仅变化时写入
crawled_at      DATETIME
```

> 留痕策略：**首次抓取 / 内容变化 / 抓取失败**三种情况写快照；成功且未变化只刷新 `monitor_sources` 的健康度字段，避免按小时抓取把表撑大。

**情报事件表 `intelligence_events`**
```sql
id              BIGINT PRIMARY KEY AUTO_INCREMENT
competitor_id   BIGINT
source_id       BIGINT
snapshot_id     BIGINT         -- 关联的快照
event_type      ENUM('new_feature','price_change','content_update','public_sentiment','other')
title           VARCHAR(255)   -- AI 生成的一句话标题
summary         TEXT           -- AI 生成的说明
diff_detail     TEXT           -- 触发本次事件的差异原文
keywords        JSON
confidence      FLOAT          -- AI 判断的置信度 0~1
priority        VARCHAR(10)    -- high|mid|low
created_at      DATETIME
```

**周报表 `weekly_reports`**
```sql
id               BIGINT PRIMARY KEY AUTO_INCREMENT
user_id          BIGINT
report_type      VARCHAR(10)    -- weekly|monthly（v1 只生成 weekly）
title            VARCHAR(255)   -- 如 2026年第37周 竞品周报
range_start      DATE
range_end        DATE
competitor_count INT
event_count      INT
summary          TEXT           -- AI 写的核心摘要
content          TEXT           -- AI 写的周报正文（Markdown）
payload          JSON           -- 冻结的结构化报表：stats/highlights/分类分布/排行/趋势/关联事件
created_at       DATETIME
```

> 数字与叙述分离：`payload` 里的所有统计都由数据库聚合得出并冻结，LLM 只负责 `summary` / `content` 两段文字，不得编造数字。

**趋势洞察表 `trend_insights`**
```sql
id                  BIGINT PRIMARY KEY AUTO_INCREMENT
competitor_id       BIGINT
period_days         INT
direction           ENUM('rising','stable','declining')  -- 变化节奏
summary             TEXT       -- AI 生成的趋势判断文本
highlights          JSON       -- 趋势要点
event_count         INT
high_impact_count   INT
coverage_days       INT        -- 有变化的天数
created_at          DATETIME
```

### 4.2 索引设计要点

- `page_snapshots(competitor_id, crawled_at)` 联合索引，便于按时间查历史快照
- `content_hash` 加索引，快速判断网页是否发生变化（避免每次都做全文 Diff）
- `intelligence_events(competitor_id, created_at)` 联合索引，便于周报汇总查询

---

## 五、核心模块详细设计

### 5.1 爬虫采集模块

```
职责：
- 根据竞品配置的 URL 列表，定时访问页面
- 处理反爬（设置 User-Agent、随机延迟、必要时用代理池）
- 提取正文内容（去除导航栏、广告、页脚等噪音）
- 生成内容哈希，与上次快照对比，判断是否需要进一步处理

技术要点：
- Playwright 处理 JS 渲染页面（很多官网用 React/Vue 构建，纯 requests 拿不到内容）
- 使用 trafilatura 或自定义规则提取正文（去噪）
- 失败重试机制（网络异常、页面结构变化导致抓取失败）
- 频率控制（避免被目标网站封禁 IP）
```

### 5.2 AI 分析模块

```
职责：
- 对比新旧快照，识别"显著变化"（避免抓取到无意义的微小改动）
- 调用大模型，将变化内容分类（新功能/价格/评论激增等）
- 生成结构化摘要（不是简单复述原文）
- 周期性汇总多个事件，生成周报

Pipeline 设计（不依赖 LangChain，直接调用 LLM API）：

设计原则：核心链路只有"摘要+分类"这种单次调用场景，逻辑简单、
步骤固定，引入 LangChain 的 Chain/Agent 抽象反而会增加理解和调试成本
（详见文末"技术选型说明"）。因此采用更轻量可控的方式：

1. Diff 预处理：用文本相似度算法（如 difflib）先做粗筛，
   减少不必要的 LLM 调用（省 token、省钱）
2. 事件分类：直接调用 LLM API，通过 Prompt 模板 + Pydantic 模型
   约束返回的 JSON 结构（新功能/价格/评论激增等分类），
   FastAPI 原生支持 Pydantic 校验，链路更短
3. 摘要生成：基于分类结果，再次调用 LLM API 生成简洁摘要
4. 周报汇总：将一周内所有事件拼接成结构化 Prompt，交给 LLM
   生成有逻辑结构的报告

V2 阶段（多Agent协作）：当需要让"抓取Agent""分析Agent""报告Agent"
互相协作、动态决策时，引入 LangGraph 做状态图编排（见第十节）

### 5.3 趋势分析模块（链路闭环的关键一环）

```
职责：
这是整条链路里把"孤立事件"升级为"AI工作流"的核心环节。
没有这一步，系统只是"每次抓到变化就调一次AI分类"，
本质上还是"事件触发型脚本"；
有了这一步，AI才是在基于历史数据做连续判断，这才是工作流。

具体做什么：
- 周期性（每周/每月）拉取某竞品过去N个时间窗口的 intelligence_events
- 统计维度：变化频率（多久调一次价/多久上一次新功能）、
  变化类型分布（这个竞品最近主要在哪个方向发力）、
  变化速度趋势（节奏是在加快还是放缓）
- 把统计结果 + 历史事件摘要一起交给 LLM，
  生成"趋势判断"而不是简单的"事件复述"
  例如："该竞品近3个月调价频率较前3个月提升一倍，
        且新功能集中在AI能力方向，推测正在加速抢占AI细分市场"

技术实现：
- 数据库层：基于 intelligence_events(competitor_id, created_at, event_type)
  做聚合查询（COUNT/GROUP BY 时间窗口）
- 分析层：聚合结果序列化后作为 Prompt 上下文，调用 LLM 生成趋势判断
- 输出：写入新表 trend_insights，供周报模块和前端趋势图共同使用
```
```

### 5.4 任务调度模块

```
职责：
- 按用户配置的频率（每天/每周）触发对应竞品的抓取任务
- 任务失败重试、日志记录
- 后续可扩展为分布式任务队列（Celery + Redis），第一版用 APScheduler 足够

调度策略：
- 不同竞品可设置不同抓取频率（重要竞品每天抓，次要竞品每周抓）
- 错峰执行，避免同一时间大量任务并发导致资源紧张
```

### 5.5 前端模块设计

```
页面结构：
├── Dashboard（数据概览）
│   - 监控中竞品数量、本周新增事件数、趋势图（ECharts）
├── 竞品管理（Competitor）
│   - 增删改查竞品、配置监控URL、设置抓取频率
├── 情报事件流（Events）
│   - 时间轴形式展示所有检测到的变化事件
├── 周报详情（Report）
│   - 展示AI生成的周报，支持历史周报回看
└── 系统设置（Settings）
    - 推送方式配置（邮件/站内通知）、账户管理

组件复用：
- 事件卡片组件（Event Card）：在 Dashboard 和 Events 页复用
- 趋势图组件：封装 ECharts，传入不同数据展示不同维度
- 统一请求封装：Axios 实例 + 拦截器（Token自动携带，已有经验）
```

---

## 六、API 设计（核心接口示例）

```
认证相关
POST   /api/auth/register          注册
POST   /api/auth/login             登录，返回 JWT
GET    /api/auth/me                当前登录用户

竞品与监控源
GET    /api/competitors                获取竞品列表（含各竞品的监控源）
POST   /api/competitors                新增竞品（可一并提交要监控的页面）
GET    /api/competitors/{competitor_id}           竞品详情
PATCH  /api/competitors/{competitor_id}           编辑竞品（传了 sources 即按此整份对齐监控源）
DELETE /api/competitors/{competitor_id}           删除竞品（级联删除其监控源）
POST   /api/competitors/{competitor_id}/crawl     立即抓取该竞品下所有启用的监控页面
GET    /api/source-types                          可选的数据源类型目录（口径来自注册表）

情报事件
GET    /api/events                 获取事件列表（支持按竞品/类型/天数筛选，返回统计 + 记录）
GET    /api/events/{event_id}      事件详情（含差异原文）

周报
GET    /api/reports                获取周报列表
GET    /api/reports/{report_id}    周报详情
POST   /api/reports/generate       手动触发生成周报（定时生成见里程碑 10）

趋势分析
GET    /api/trends/overview                全部竞品汇总的趋势序列（Dashboard 用）
GET    /api/trends/{competitor_id}         某竞品的趋势洞察（缺省或过期时自动生成一次）
GET    /api/trends/{competitor_id}/chart   返回趋势图表所需的时间序列数据

实时能力（可选，体验加分项）
GET    /api/events/stream          SSE，实时推送新检测到的事件
```

> 约定：错误的 HTTP 状态码（400/401/404/422…）统一返回 `{code, message, data}` 响应壳，`code` 为与状态码解耦的业务码（如 `40101` 账号或密码错误、`40401` 竞品不存在），前端按 `code` 分流、文案以后端 `message` 为准。
> 实现提示：`/api/trends/overview` 必须声明在 `/api/trends/{competitor_id}` 之前，否则 `overview` 会被当作 `competitor_id` 解析。

---

## 七、部署架构

```
单机部署方案（适合个人项目/演示）：

┌─────────────────────────────────────┐
│           云服务器（Linux）            │
│                                       │
│  ┌─────────┐  ┌─────────┐           │
│  │ Nginx   │→ │ 前端静态  │           │
│  │ (反向代理)│  │ 资源     │           │
│  └────┬────┘  └─────────┘           │
│       │                              │
│       ▼                              │
│  ┌─────────┐  ┌─────────┐           │
│  │ FastAPI │→ │ MySQL   │           │
│  │ (Docker)│  │ (Docker)│           │
│  └────┬────┘  └─────────┘           │
│       │                              │
│       ▼                              │
│  ┌─────────┐  ┌─────────┐           │
│  │ Redis   │  │ 定时任务  │           │
│  │ (Docker)│  │ 进程      │           │
│  └─────────┘  └─────────┘           │
└─────────────────────────────────────┘

docker-compose.yml 统一管理所有服务，
本地开发和云端部署用同一套配置，保证环境一致性

落地要点（里程碑 11 已实现，见根目录 `docker-compose.yml`）：

- **入口收口**：只有 Nginx 对外暴露端口，`/api/` 与 `/docs` 反代到后端；MySQL / Redis / 后端只在 compose 内部网络中
- **建表方式双轨**：开发期应用启动时 `create_all`（`DB_AUTO_CREATE=true`）；生产由后端容器入口执行 `alembic upgrade head`（`DB_AUTO_CREATE=false`），应用不再越权改已上线库的结构。两条路径建出的表结构已验证一致
- **定时任务是进程内的**：APScheduler 随 FastAPI lifespan 启停（图中独立的「定时任务进程」已合并进 FastAPI 进程）。多副本扩容（`--scale backend=2`）时，各副本通过 `CACHE_BACKEND=redis` 的分布式锁互斥，同一批到期的页面只被一个实例抓取——这正是 Redis 在本方案里的核心用途
- **缓存抽象**：`core/cache.py` 提供 `MemoryCache`（开发）/ `RedisCache`（生产）两种后端，`CACHE_BACKEND` 一键切换
```

---

## 八、开发阶段规划

```
阶段一（第1-2周）：基础设施搭建
- 项目初始化（前后端脚手架）
- 数据库表设计落地
- 用户认证模块（JWT登录注册）
- Docker环境搭建

阶段二（第3-4周）：核心采集能力
- Playwright爬虫开发
- 内容清洗与去噪
- 快照存储与Diff对比逻辑

阶段三（第5-7周）：AI分析能力
- LLM API调用封装（Prompt模板 + Pydantic结构化输出）
- 事件分类与摘要生成
- 趋势分析模块（聚合历史事件 + 生成趋势判断）
- 周报生成逻辑

阶段四（第8-9周）：前端完整开发
- Dashboard、竞品管理、事件流、周报页面
- 前后端联调

阶段五（第10-11周）：任务调度与自动化
- APScheduler定时任务集成
- 邮件推送功能

阶段六（第12周）：部署与打磨
- Docker Compose整合部署
- README、架构图、技术博客撰写
- 演示视频录制
```

---

## 九、风险与应对

| 风险 | 应对方案 |
|---|---|
| 目标网站反爬升级，抓取失败 | 设置合理频率，必要时引入代理池；做好失败重试与告警 |
| 网站改版导致提取规则失效 | 抓取逻辑与解析规则分离，便于针对单个网站快速调整 |
| LLM 调用成本过高 | 先用文本相似度算法粗筛，只对"显著变化"调用LLM，减少无效调用 |
| 法律合规风险 | 仅抓取公开页面信息，不绕过登录验证，不抓取个人隐私数据 |

---

## 十、后续可扩展方向（V2规划，先了解，不影响第一版）

```
- 多Agent协作：拆分为"抓取Agent"、"分析Agent"、"报告Agent"，
  用LangGraph编排，体现Multi-Agent架构能力（面试加分项）
- 向量化历史报告，支持语义搜索"过去某竞品做过哪些价格调整"
- 多用户SaaS化，支持团队协作
- 接入更多数据源（小红书、知乎等社媒平台的竞品提及）
```

---

## 十一、技术选型说明：为什么核心链路不用 LangChain

这部分专门写出来，是因为这是一个值得在面试时主动讲的工程判断，而不是回避的弱点。

**背景**：LangChain 在社区存在真实争议。有团队反馈，简单场景下引入 LangChain 后，团队花在理解和调试框架抽象上的时间，跟构建功能本身一样多；也有开发者测算过，用 LangChain 实现简单 RAG 的成本是直接调用 API 的数倍。核心问题在于：LangChain 的 Chain/Agent 抽象适合"标准化复杂流程"，但对本项目这种"单次调用+结构化输出"的简单场景，反而是过度设计。

**本项目的判断**：
```
核心链路（摘要生成、事件分类）：
└── 逻辑单一、步骤固定 → 直接调 LLM API + Pydantic 约束输出
    更轻量、更可控、出问题更容易定位

V2 多Agent协作（抓取/分析/报告Agent互相决策）：
└── 需要状态管理、动态分支、多角色交互 → 用 LangGraph
    这类复杂编排场景，正是框架该发挥价值的地方
```

**一句话总结**：不是"要不要用框架"，而是"在什么复杂度下用什么工具"。简单问题用简单方案解决，复杂的状态化协作才交给专门的编排框架，这本身就是技术选型能力的体现。

