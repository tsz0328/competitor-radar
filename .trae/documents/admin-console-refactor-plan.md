# 管理员端重构：独立管理后台（管用户数据）

## Context

当前管理员与普通用户共用同一套 AppLayout 侧边栏，管理员只是多出「全部竞品」「用户管理」两个菜单，整体仍是「用户自己添加竞品」的视角。目标：把管理员端重构成**真正管用户数据的管理后台**——管理员登录后进入独立的侧边栏（平台总览 / 用户管理 / 系统设置 / 全部竞品），不再看到用户业务页（竞品管理、情报中心等）；管理员自己也不需要用户功能。

已拍板的决策：
1. 复用 AppLayout 外壳，按 `is_admin` 切换侧边栏菜单（不新建布局）。
2. 管理后台 = 平台总览（统计卡片+趋势图）+ 增强版用户管理（每行带数据统计）+ 系统设置（SMTP 从 Setting.vue 迁出）。
3. 「全部竞品」页**保留不动**，作为管理侧边栏第 4 个菜单。
4. 管理员登录后直达管理总览；路由上拦截管理员访问用户业务页（唯一例外：`Setting?tab=account` 用户中心，管理员仍可改自己资料）。

---

## 一、后端

### 1. 新建 `backend/app/services/admin_stats.py`（聚合服务）
- `user_stat_subqueries()`：返回 4 个子查询（每个都是 `select(xx.user_id, func.count().label("cnt")).group_by(...)` 的 subquery）：
  - competitor_sub：`Competitor.user_id`，`where(deleted_at.is_(None))`
  - event_sub：`Competitor.user_id` join `IntelligenceEvent.competitor_id`（事件是历史留痕，不过滤 deleted_at）
  - report_sub：`WeeklyReport.user_id`，`where(deleted_at.is_(None))`
  - crawl_sub：`CrawlLog.user_id`
- `async overview_totals(db) -> dict[str, int]`：8 个 count——`users / active_users / admin_users / competitors / sources / events / reports / crawl_logs`（competitors、reports 带 `deleted_at.is_(None)` 过滤；sources 为 MonitorSource 全量）。
- `async build_global_daily_series(db, days, column)`：全量（跨用户）按 `created_at` 分桶的近 N 天序列，复用 `app/core/timeutil.to_local` + 补 0 模式（照抄 `services/trend.py` 的 `build_daily_totals`，去掉 user 过滤），返回 `[{date:"9/15", date_iso:"2026-09-15", count}]`。events 用 `IntelligenceEvent.created_at`，crawl 用 `CrawlLog.created_at`，days=30。

### 2. 修改 `backend/app/api/admin.py`
- `AdminUserOut` 增加 4 个统计字段（默认 0）：`competitor_count / event_count / report_count / crawl_log_count`。
- `list_users` 改为子查询 + outerjoin + coalesce 聚合查询（**不要** `group_by(User.id)` + 多表 count，避免一对多放大），保留 keyword 过滤；`_admin_user_out` 增加 stats 参数填充。
- 新增 `GET /api/admin/overview`（`get_current_admin` 鉴权），返回：
  ```json
  { "totals": {...八项...}, "event_trend": [...], "crawl_trend": [...] }
  ```
  schema 内联定义在 admin.py（与现有 AdminUserOut 风格一致）。

### 3. 新建 `backend/tests/test_admin.py`
复用 conftest 的 client/session fixture，参考 `tests/test_icon_library.py` 的 `_seed_user/_seed_competitor` 写法：
- 普通用户访问 `/api/admin/overview` → 403。
- 种子 2 用户 + 竞品/事件/周报/日志 → overview totals 精确断言；两条 trend 长度 30、count 合计与种子一致、date_iso 连续。
- `/api/admin/users` 返回带统计字段，空用户全 0，有数据用户数值正确；keyword 过滤仍生效。

---

## 二、前端路由与守卫

### 1. `frontend/src/router/index.ts`
- 新增懒加载 `AdminOverview`（`views/app/AdminOverview.vue`）、`AdminSettings`（`views/app/AdminSettings.vue`）。
- 子路由加 meta：
  - 用户业务页（dashboard/competitor/crawl-log/event/report/trend/trash/setting）→ `meta: { userOnly: true }`
  - 管理页（admin-overview/admin-settings/user-manage/all-competitors）→ `meta: { adminOnly: true }`
- 新增路由 `admin-overview`（name `AdminOverview`）、`admin-settings`（name `AdminSettings`），路径与 name 和菜单一一对应。
- `/app` 顶层 `redirect: { name: "Dashboard" }` 保留：管理员会被守卫二次重定向到 AdminOverview。

### 2. 新建 `frontend/src/router/guard.ts`（可单测纯函数）
```ts
export function resolveRoleRedirect(to, isAdmin: boolean) {
  if (to.meta.adminOnly && !isAdmin) return { name: "Dashboard" };
  if (to.meta.userOnly && isAdmin) {
    if (to.name === "Setting" && to.query.tab === "account") return null; // 管理员用户中心例外
    return { name: "AdminOverview" };
  }
  return null;
}
```
- `index.ts` 的 beforeEach 改为 async：token 校验不变；取 `auth.user?.is_admin`，**仅当非 boolean 时**补拉 `fetchMyProfile()`（照抄 SideNav.vue 的兜底，兜底失败按非管理员处理）。

### 3. 新建 `frontend/src/router/guard.spec.ts`（vitest）
覆盖：普通用户访问 admin 页→Dashboard；管理员访问 user 页→AdminOverview；管理员访问 `Setting?tab=account`→null；无 meta→null。

---

## 三、前端菜单与侧边栏

### 1. `frontend/src/data/navMenu.ts`
- `NavMenuItem` 删除 `adminOnly` 字段；拆为两套：
  - `USER_NAV_MENUS`：现有 adminOnly=false 的全部（工作台/竞品/日志/情报/周报/趋势/回收站/设置）
  - `ADMIN_NAV_MENUS`：平台总览（name `AdminOverview`，icon `DataAnalysis`）、用户管理（`UserManage`，`UserFilled`）、系统设置（`AdminSettings`，`Setting`）、全部竞品（`AdminCompetitors`，`OfficeBuilding`）
- 保留合并导出 `NAV_MENUS = [...USER_NAV_MENUS, ...ADMIN_NAV_MENUS]`（DemoShell 继续展示全貌，不改）。

### 2. `frontend/src/layouts/AppLayout/SideNav.vue`
`visibleMenus` 改为 `user.value?.is_admin ? ADMIN_NAV_MENUS : USER_NAV_MENUS`，其余不动。
`DemoShell.vue` 不改。

---

## 四、前端页面

### 1. 新建 `frontend/src/views/app/AdminOverview.vue`
- header「平台总览」+ 统计卡片网格（复用 Dashboard.vue 的 stat-card 样式类与 `--app-color-*` 变量）：用户数/启用用户/竞品/事件/周报/抓取日志（6 卡）。
- 趋势图：页面内直接用 `vue-echarts` 折线（照 `InfoTrendChart.vue` 的 use 注册方式），单图双 series：event_trend、crawl_trend，x 轴取 `date`。
- 空态：无数据时 `graphic` 显示「暂无趋势数据」。

### 2. 新建 `frontend/src/views/app/AdminSettings.vue`
把 `Setting.vue` 的 SMTP「系统设置」分区（约 L1121-1176 逻辑 + L1625-1723 模板）整体迁出为独立页：
- 复用 `api/admin.ts` 的 `getSystemSettings/updateSystemSettings`（后端不变）。
- 只读态 info-item 列表 + 「修改」按钮 + 编辑表单；保留「留空=清覆盖/回退 .env、授权码留空=不修改」提示；授权码只显示 `*` 掩码或「未设置」。

### 3. 修改 `frontend/src/views/app/Setting.vue`（收尾）
- 删除 SMTP 分区相关脚本（sysForm/sysEditing/sysSaving/loadSystem/saveSystem/cancelSystem/sysPasswordMasked、onMounted 里的 loadSystem 调用、相关 import）、模板 `<section v-show="activeCategory === 'system'">`。
- `CategoryKey` 去掉 `"system"`；`categories` 从 computed 退化为常量 `baseCategories`；`applyTabFromQuery` 里 `categories.value` → `categories`（L121）。
- 删除 `Message` 图标 import（仅 system 分类用）。

### 4. 修改 `frontend/src/views/app/UserManage.vue`
- 表格增加 4 个纯展示统计列（竞品/情报/周报/抓取日志），prop 对应 `competitor_count/event_count/report_count/crawl_log_count`，数字右对齐。

### 5. 修改 `frontend/src/api/admin.ts`
- `AdminUser` 增加 4 个统计字段。
- 新增 `AdminOverviewTotals / AdminDailyPoint / AdminOverview` 接口与 `getAdminOverview()`。

---

## 五、验证

1. 后端：`cd backend && pytest tests/test_admin.py -q`，再全量 `pytest -q`（现有 105 个不回归）。
2. 前端：`cd frontend && npm run build`（含 vue-tsc）；`npx vitest run`。
3. 端到端（真实后端已切好，mock 已关）：
   - 管理员登录 → 落「平台总览」，侧边栏只有 4 个管理菜单；总览卡片/趋势图正常；用户管理每行 4 个统计列数字正确；系统设置可改 SMTP 并保存；Setting.vue 不再有「系统设置」分类。
   - 管理员点底部「用户中心」→ 正常进 `Setting?tab=account`；直接访问 `/app/dashboard` → 重定向总览；无死循环。
   - 普通用户登录 → 落工作台，菜单无管理项；直接访问 `/app/admin-overview`、`/app/user-manage` → 重定向工作台。

## 六、实施顺序

1. 后端：`admin_stats.py` → `admin.py` → `test_admin.py`
2. 前端 API：`api/admin.ts`
3. 新页面：`AdminOverview.vue` → `AdminSettings.vue`
4. `Setting.vue` 收尾
5. `navMenu.ts` + `SideNav.vue`
6. `router/index.ts` + `guard.ts` + `guard.spec.ts`
7. `UserManage.vue` 统计列
8. 全量测试 + 端到端验证

## 风险点

- 菜单 name 与路由 name 必须同步（`AdminOverview`/`AdminSettings`），否则菜单高亮失效。
- 守卫只处理 `typeof is_admin !== "boolean"` 的兜底拉取；失败按非管理员处理，由 SideNav 兜底纠正。
- 重定向目标不带对侧 meta（Dashboard 只 userOnly、AdminOverview 只 adminOnly），避免死循环。
- `/users` 聚合必须用「子查询 + outerjoin + coalesce」，禁止 `group_by(User.id)` 多表 count。
- overview 时间序列必须走 `to_local` 分桶（created_at 带时区，直接 `.date()` 会差一天）。