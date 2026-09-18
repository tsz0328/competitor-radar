# 竞品雷达 — 数据源抽象与采集配置设计

> 版本：v1.0　作者：唐思哲　更新日期：2026-09-05
> 地位：本文件是**后端爬虫模块（里程碑 6）的唯一输入契约**。里程碑 3 的建表、Schemas、注册表均按本文落地。
> 配套文档：`docs/positioning.md`（产品边界）/ `docs/architecture.md`（技术方案）
> 边界来源：数据源白名单与黑名单以 `docs/positioning.md` 第五、六节为准，本文只做技术化展开。

---

## 一、设计目标

1. **一次建模，多源复用**：把 `competitors.monitor_urls` 这份无结构 JSON 升级为独立 `monitor_sources` 表 + `SOURCE_TYPE_REGISTRY` 注册表，让"竞品挂了哪些监控源、每个源怎么抓、上次抓得怎么样"全部结构化、可索引、可聚合。
2. **v2 可插拔**：新增一种数据源（如 Shopify 商品页）不触碰核心采集链路。
3. **性能分流**：只有确需 JS 渲染的页面才走 Playwright（1-3 秒/次、内存占用高）；静态 RSS / 状态页走 httpx（毫秒级）。
4. **健康度可见**：单源记录 `last_crawled_at` / `last_status` / `fail_count`，单源失败不拖垮整批。

---

## 二、为什么不用 JSON 字段（决策记录）

`competitors.monitor_urls` 现状：

```json
// 里程碑 5 之前的历史设计：无结构 JSON
{"pages": ["https://www.notion.so/", "https://www.notion.so/pricing"]}
```

| 能力 | JSON 字段 | 独立 `monitor_sources` 表 |
|---|---|---|
| 记录单点抓取状态（上次成功时间 / 连续失败次数） | ❌ 无法承载 | ✅ |
| 按 source_type 聚合统计（如"本月定价页变化次数"） | ❌ 语义丢失 | ✅ |
| 为 `page_snapshots` 提供外键归因 | ❌ | ✅ `snapshot.source_id` |
| 索引 / 查询效率 | ❌ | ✅ `(competitor_id, enabled)` |
| 按类型配置默认频率、渲染方式 | ❌ 每次读配置对不上 | ✅ 冗余在行内 + 注册表兜底 |

**代价**：多一张表和一次 join —— 可接受。

**兼容策略**：`competitors.monitor_urls` 字段**保留但标记 deprecated**，里程碑 5 之后不再读写，避免一次性大改波及已完成的竞品管理页。

---

## 三、source_type 类型体系（v1 白名单，共 8 种）

| source_type | label | render | 默认频率 | extractor | differ | LLM 分类提示 |
|---|---|---|---|---|---|---|
| `homepage` | 官网首页 | browser | 1440（每天） | `trafilatura` | `full_text` | 官网首页内容变化（产品定位 / 标语 / 主推功能） |
| `pricing` | 定价页 | browser | 1440 | `trafilatura` + 价格提取 | `full_text` + `structured` | 定价 / 套餐 / 计费方式调整 |
| `changelog` | 更新日志 | browser | 1440 | `trafilatura` | `item_set`（增量条目优先） | 新版本 / 新功能 / 修复说明 |
| `blog` | 官方博客 | http（RSS 优先） | 1440 | `rss`（无 RSS 时降级 `trafilatura`） | `item_set`（标题+摘要集合） | 官方文章发布（产品 / 行业 / 公司动态） |
| `docs` | 帮助文档 | browser | 10080（每周） | `trafilatura` | `full_text` | 帮助文档变更（功能说明 / 使用方式变化） |
| `status` | 服务状态页 | http | 60（每小时） | `trafilatura` | `full_text` | 服务状态 / 故障 / 维护公告 |
| `rss` | 通用 RSS/Atom | http | 60 | `rss` | `item_set` | 订阅源条目变化 |
| `app_store` | 应用商店页 | browser | 1440 | `store_block`（版本号+更新说明） | `structured`（版本号比对优先） | 应用版本更新 / 评分波动 / 新功能上线 |

**v2 预留（本次只登记不实现）**：

| source_type | 说明 |
|---|---|
| `shopify_product` | DTC 独立站 / Shopify 店铺商品页（公开、反爬弱） |
| `app_store_rss` | App Store / Google Play 公开 RSS 与榜单 |
| `open_api` | Amazon PA-API、京东联盟等官方开放平台 API |

> 判据参考 `docs/positioning.md` 5.2：黑名单数据源（电商商品价格销量评论、登录墙页面、需破解签名的接口）**无论 v1/v2 都不做**。v2 只接入"公开可得、可 Diff、官方允许"的数据源。

---

## 四、数据库变更

### 4.1 新增表 `monitor_sources`

```sql
CREATE TABLE monitor_sources (
    id              BIGINT PRIMARY KEY AUTO_INCREMENT,
    competitor_id   BIGINT NOT NULL,                    -- FK -> competitors.id
    source_type     VARCHAR(30) NOT NULL,               -- 取值与 SOURCE_TYPE_REGISTRY 键一致
    name            VARCHAR(100) NOT NULL,              -- 展示名，如「定价页」「更新日志」
    url             VARCHAR(1024) NOT NULL,             -- 实际抓取地址
    render_mode     VARCHAR(10) NOT NULL,               -- 'browser'|'http'，冗余自注册表，快照创建时的策略快照
    interval_minutes INT NOT NULL,                      -- 覆盖频率
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_crawled_at DATETIME,                           -- 上次成功抓取时间
    last_status     VARCHAR(10),                        -- 'success'|'failed'|NULL(从未抓取)
    last_error      TEXT,                               -- 上次失败原因摘要（不含正文）
    fail_count      INT NOT NULL DEFAULT 0,             -- 连续失败次数
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_source_competitor (competitor_id, enabled),
    INDEX idx_source_type (source_type)
)
```

SQLAlchemy 要点：

- 枚举字段（`source_type`、`render_mode`）用 `sqlalchemy.Enum(..., native_enum=False)` 存 VARCHAR（DB 无关，见 `docs/milestones.md` 〇）。
- `render_mode` **不写成对 `source_registry` 的运行时查询**，而是建源时从注册表复制到行内 —— 避免注册表后续改默认值导致历史源语义漂移。
- `enabled = False` 等价"暂停监控该源"，删除源走级联（见 4.3）。

### 4.2 变更表 `page_snapshots`（新增 5 个字段）

```sql
ALTER TABLE page_snapshots
    ADD source_id       BIGINT,     -- FK -> monitor_sources.id（可空：历史数据无归因）
    ADD source_type     VARCHAR(30),-- 冗余，快照落库时的类型快照（注册表变更不漂移）
    ADD http_status     INT,        -- 200 / 304 / 404 ...
    ADD is_success      BOOLEAN,    -- 抓取是否成功（失败也留一条快照记录，便于排查）
    ADD fail_reason     TEXT;       -- 失败原因（不落正文）
```

原字段（不变）：`id`、`competitor_id`、`url`、`raw_html_path`、`clean_text`、`content_hash`、`crawled_at`。

**语义变化**：`page_snapshots` 从"竞品页面快照"升级为"**监控源的抓取记录**"，天然支持"失败留痕"（失败时 `clean_text=NULL`、`content_hash=NULL`、`is_success=False`）。

### 4.3 表关系总览

```
Competitor (competitors) 1 ── n MonitorSource (monitor_sources)
    │                              │
    │ 1                            │ 1
    └────────── n PageSnapshot (page_snapshots) ←──┘
                        │ n
                        ▼
              IntelligenceEvent (intelligence_events)
                        │
                        ├── WeeklyReport (weekly_reports)
                        └── TrendInsight (trend_insights)
```

删除语义：`competitors` 删除 → 级联删其 `monitor_sources`；快照与事件**保留**（历史可回看，仅置空/保留 competitor 名称冗余可选，里程碑 5 再细化）。

### 4.4 索引（合计，纳入里程碑 3 建表）

| 表 | 索引 |
|---|---|
| `page_snapshots` | `(competitor_id, crawled_at)`、`(source_id, crawled_at)`、`content_hash` |
| `intelligence_events` | `(competitor_id, created_at)`、`(source_id)` |
| `monitor_sources` | `(competitor_id, enabled)`、`(source_type)` |
| `weekly_reports` | `(user_id, created_at)` |

---

## 五、事件类型枚举统一（里程碑 3 落地）

前端报告/事件模型现行分类（见 `frontend/src/types/report.ts`）：`功能更新 / 价格变化 / 内容更新 / 舆论动态 / 其他`。

后端枚举最终口径（**唯一对齐点**，`backend/app/models/event.py`）：

| 枚举值（后端存库） | 中文标签（前端展示） | 说明 |
|---|---|---|
| `new_feature` | 功能更新 | 原架构文档 `new_feature` |
| `price_change` | 价格变化 | 原架构文档 `price_change` |
| `content_update` | 内容更新 | 原架构文档 `content_update` |
| `public_sentiment` | 舆论动态 | **原 `negative_review_spike` 改名**。官网方向下"差评/口碑变化"主要来自应用商店评分与舆论，而非电商评论，改名更准 |
| `other` | 其他 | 原架构文档 `other` |

历史兼容：里程碑 7 之前的库里若有 `negative_review_spike`，迁移时映射为 `public_sentiment`。开发期无历史库，直接按新枚举建表。

前端 `tagType`（`tag-feature` / `tag-price` / `tag-content` 等）与后端枚举的映射在里程碑 7 提供接口时给出，本次只统一"后端枚举 ↔ 中文标签"两层。

---

## 六、接口路径统一（里程碑 3 一并修正前端）

### 6.1 现状冲突

- `frontend/src/api/report.ts` 与 `frontend/mock/report.ts`：`GET /api/reports/list`、`GET /api/reports/detail?id=`
- `docs/architecture.md` 第六节：`GET /api/reports`、`GET /api/reports/{id}`、`POST /api/reports/generate`

### 6.2 统一结论（以架构文档 RESTful 口径为准）

| 方法 & 路径 | 说明 |
|---|---|
| `GET /api/reports` | 报告列表（`?type=weekly&page=&page_size=`） |
| `GET /api/reports/{id}` | 报告详情 |
| `POST /api/reports/generate` | 手动触发生成（调试用） |

理由：RESTful、与 `auth / competitors / events / trends` 各组路径风格一致。本次同步修正前端 `api/report.ts` 与 `mock/report.ts`。

**注意**：`POST /api/reports/generate` 与 `GET /api/reports/{id}` 需保证路由不冲突 —— `generate` 是 POST 而 `{id}` 是 GET，天然不冲突；若未来加 `GET /api/reports/generate` 需显式声明。

---

## 七、策略接口与注册表（里程碑 6 实现，本次只定契约 + 落地注册表）

### 7.1 分层职责

```
monitor_sources 行
      │
      ▼
┌─────────────────────────────┐
│ SourceRegistry              │  ← 按 source_type 解析策略三元组
│   get_source_config(type)   │
└──────────┬──────────────────┘
           │
  ┌────────▼─────────┐
  │ Fetcher          │  render=browser → Playwright（复用单例 context）
  │                  │  render=http    → httpx / feedparser
  └────────┬─────────┘
           │ HTML / 结构化文本
  ┌────────▼─────────┐
  │ Extractor        │  trafilatura / rss / store_block / price 提取
  │                  │  → clean_text + 可选结构化字段（版本号、条目列表）
  └────────┬─────────┘
           │ clean_text
  ┌────────▼─────────┐
  │ content_hash     │  sha256(clean_text) 与上次快照比对（索引粗筛）
  │                  │  无变化 → 丢弃；有变化 → 进 Differ
  └────────┬─────────┘
  ┌────────▼─────────┐
  │ Differ           │  full_text / item_set / structured
  │                  │  → 变化块文本（送给 LLM）
  └────────┬─────────┘
           ▼
  LLMClient.classify_and_summarize(old, new)
           ▼
  intelligence_events
```

### 7.2 类型契约草稿（里程碑 6 实现）

```python
# services/crawler.py —— 里程碑 6 交付
class FetchResult(NamedTuple):
    raw_html: str | None
    clean_text: str | None
    http_status: int
    ok: bool
    error: str | None

class Fetcher(Protocol):
    async def fetch(self, source: MonitorSource) -> FetchResult: ...

class Extractor(Protocol):
    def extract(self, raw_html: str) -> str: ...   # 正文/结构化文本
    def to_snapshot_payload(self, raw_html: str) -> dict: ...  # 可选结构化字段

class Differ(Protocol):
    def diff(self, old: str, new: str) -> str: ... # 变化块文本
    def should_trigger(self, old_hash: str, new_hash: str) -> bool: ...
```

v2 新增数据源 = 注册表加一项 + 实现该类型的 Fetcher/Extractor/Differ。**核心 `crawler → analyzer` 主流程不改**。

---

## 八、可靠性设计要点（供里程碑 6 遵守）

1. 抓取失败：只写 `last_status='failed'`、`fail_count+=1`、`last_error`（URL/状态码/错误摘要），**不抛穿主流程**；单源失败不影响同批次其他源。
2. `fail_count >= 5` 时该源自动 `enabled=False` 并提示（防死循环消耗资源），恢复需人工或成功后重置。
3. Playwright 复用单例 browser context，禁止每次抓取新建浏览器。
4. 日志只记 URL、source_type、耗时、状态码、错误摘要；**不记录正文内容与 API Key**。
5. 原始 HTML 落 `backend/storage/`（`.gitignore` 排除），库里只存路径；开发期可用 `STORAGE_DIR` 或开关关闭落盘省空间。

---

## 九、落地清单（与里程碑 3 对应）

| 交付物 | 文件 | 说明 |
|---|---|---|
| 类型配置与注册表 | `backend/app/core/source_registry.py` | `SourceTypeConfig` + `SOURCE_TYPE_REGISTRY`（8 种 v1 + 3 种 v2 预留键）+ `get_source_config()` |
| 新表模型 | `backend/app/models/source.py` | `MonitorSource` |
| 快照表变更 | `backend/app/models/snapshot.py` | `PageSnapshot` 增 `source_id/source_type/http_status/is_success/fail_reason` |
| 事件枚举 | `backend/app/models/event.py` | `EventType`（5 值）+ `EVENT_TYPE_LABELS` |
| 建表索引 | 各模型 | 见 4.4 |
| Schema 校验 | `backend/app/schemas/source.py` | `source_type` 取值校验引用注册表键 |
| Demo 数据 | `backend/app/seed.py` | 8 个协作办公 SaaS 竞品 + 各 3-4 个 `monitor_sources`，与前端 mock 示例一致 |

---

## 十、已落地的能力增强（实现补充）

> 本节记录在原契约基础上后来落地的三处增强，保持与代码一致。

### 10.1 正文噪声剥离（减少假情报，对应原流程第 5/9 步）

`crawler.extract_text` 在「提取正文 → 空白归一化」之后、计算 `content_hash` **之前**，加了一道 `strip_noise`：整行丢弃"每轮渲染必变但无情报价值"的内容。

- 丢弃的行：相对时间（`3 分钟前` / `just now`）、动态元数据行（`当前时间` / `最后更新` / `刷新时间` 等）、整行纯时刻（如 footer 的 `09:30`）、浏览/播放计数（`123 次阅读` / `1.2k views`）。
- **刻意保留**：`发布于/更新于 2026-09-18 新增…`（更新日志的发布日期含真实内容）、`营业时间 09:00-18:00`（时间区间），避免误伤正文。
- 效果：相同实质内容两次抓取的 hash 不变 → 不再产生「Footer 时间变化」类假情报；同时让 diff 只反映真变化。

### 10.2 情报事件 `ai_analysis` 字段（事实与推断分离，对应原流程第 12 步）

`intelligence_events` 在 `summary` 之外新增 `ai_analysis` 列：

- `summary`：页面**事实**（AI 客观描述发生了什么变化）；
- `ai_analysis`：AI 对该变化的**推断/影响判断**（明确标注为「分析，非事实」，措辞用「可能/或/倾向于」）。

LLM 的 `classify_and_summarize` 现在在 JSON 中**同时产出** `summary` 与 `analysis` 两个字段；无 Key 时规则兜底也分别给出事实摘要与按事件类型的影响推断。前端详情抽屉将两者分区展示，并标注「AI 判断 · 仅供参考」。

### 10.3 高优先级事件即时通知（对应原流程第 23 步）

原设计只在「整批抓取结束」后发一条汇总通知。现额外在 `analyzer._create_event` 后判断：若事件 `priority == "high"`，**立即**单条推送一条通知（标题含竞品名与事件类型、正文含摘要与「查看详情」链接）。

- 通知仍走 `notifier.notify`：推送失败绝不影响主流程，且只在 `NOTIFY_ENABLED=true` 时发送；
- 「查看详情」链接由新增配置 `frontend_base_url`（默认 `http://localhost:5173`）拼出，形如 `{frontend_base_url}/app/event`；
- 批次汇总通知（scheduler 在整批结束后发出）保留，二者互补：批次汇总覆盖「只有中/低优先级事件」的场景，单条即时通知覆盖「高优先级需立即关注」的场景。
