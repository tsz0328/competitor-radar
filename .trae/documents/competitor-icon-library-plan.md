# 竞品图标库（后端存储 + 管理员管理）实施计划

## Context（背景与目标）

现状：竞品图标只是一条指向外部站点的 URL 字符串（`competitors.logo_url`），图片本体不在后端。外部站点一变动/封锁即失效——此前 Canva 全站 403、docs.qq favicon 返回 HTML、Asana 错链 401 都是这个原因，前端只能退回首字母头像。

用户需求（已确认决策）：
1. 图标**永久存在后端**：上传文件存**磁盘**（`storage/icons/`）+ 数据库记录（`icon_libraries` 表，按规范化域名唯一）。
2. 解析优先级改为「**后端图标库（按域名）→ 官网抓取解析 → 首字母兜底**」。
3. **仅管理员**可上传图标；管理员端新增「全部竞品」页面，可查看所有用户添加的竞品；编辑范围**仅图标**，其他字段只读。
4. 管理员上传后立即生效：该竞品及**同域名**的其它竞品图标一并替换（图标库是域名级事实源），并清 favicon 缓存。

---

## 一、后端

### 1. 新模型 `backend/app/models/icon_library.py`
```python
class IconLibrary(Base, TimestampMixin):
    __tablename__ = "icon_libraries"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)  # 规范化 host：小写、去 www
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)  # uuid4().hex + ext
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 不加 FK：避免删用户时被外键卡住；种子数据为 NULL
```
在 `backend/app/models/__init__.py` 的 import 与 `__all__` 登记 `IconLibrary`。

### 2. 新 Service `backend/app/services/icon_library.py`
- `normalize_host(value)`：复用 `favicon.clean_host` 的解析，再**去掉前导 `www.`、小写**（与前端 CompetitorLogo / schemas 回退口径一致）。
- `icons_dir()`：`settings.storage_dir / "icons"`，`mkdir(parents=True, exist_ok=True)`。
- `public_icon_url(file_name)`：返回**相对路径** `"/api/icons/{file_name}"`（dev 由 vite 代理 /api 命中；同源部署直接命中；不写死 request.base_url）。
- `find_by_domain(db, domain) -> IconLibrary | None`。
- `apply_icon_for_competitor(db, competitor)`：按 `normalize_host(competitor.official_url)` 查库，命中则写 `competitor.logo_url = public_icon_url(...)`，未命中不动。

### 3. 静态挂载 `backend/app/main.py`
- `from fastapi.staticfiles import StaticFiles`；在 `app = FastAPI(...)` 之后：
  ```python
  Path(settings.storage_dir, "icons").mkdir(parents=True, exist_ok=True)  # StaticFiles 要求目录存在
  app.mount("/api/icons", StaticFiles(directory=Path(settings.storage_dir)/"icons"), name="icons")
  ```
- `<img>` 无法带 Authorization，必须公开静态路由。SVG 一律拒收（XSS 面），目录内只会是白名单格式图片。

### 4. 迁移 `backend/migrations/versions/20260921_1100_add_icon_library.py`
- `down_revision = "20260920_2000_drop_report_unique"`；upgrade 用 `inspector.has_table("icon_libraries")` 幂等判断后 `op.create_table`（含 domain unique、created_at/updated_at）；downgrade 对应 drop。

### 5. 三处解析优先级接入
- `backend/app/api/competitors.py`：
  - `create_competitor`：恢复分支（commit 前）与新建分支（`db.flush()` 拿到 id 后）各调 `await icon_library.apply_icon_for_competitor(db, competitor)`。
  - `competitor_favicon`（GET /favicon）：加 `db: Annotated[AsyncSession, Depends(get_db)]`；先 `find_by_domain`，命中返回库图标，否则回退 `resolve_favicon(domain)`。
- `backend/app/services/analyzer.py`：`_capture_logo_from_html` 加首参 `db: AsyncSession`，函数开头先查库，命中即写 `competitor.logo_url` 并 return（跳过 HTML 解析）；调用点 `_crawl_source_locked`（约 L349）传入 db。

### 6. 管理端 API（`backend/app/api/admin.py` 追加）
- `GET /api/admin/competitors`（`get_current_admin`）：
  - 跨用户查询：`select(Competitor).where(Competitor.deleted_at.is_(None)).order_by(Competitor.id)`，可选 keyword 按名称/官网模糊过滤。
  - 复用 `competitors._with_change_counts` 聚合变化数；新增 schema `AdminCompetitorOut(CompetitorOut)` 增 `owner_username/owner_nickname` 字段（一次性 `select(User)` 建 dict 映射，避免 N+1）。
- `POST /api/admin/competitors/{competitor_id}/icon`（multipart `UploadFile`）：
  1. `get_current_admin`；`db.get(Competitor, id)`（跨用户，只要求未删除）。
  2. 校验 content_type ∈ {png/jpeg/webp/gif} 白名单、大小 ≤ 2MB（新增 config `icon_max_bytes`，默认 2MB）；**拒绝 svg**（可内嵌脚本，XSS 风险）。
  3. `host = normalize_host(competitor.official_url)`，为空则 400。
  4. 写文件 `icons_dir()/uuid4().hex + ext`；命中旧记录且 file_name 不同则删除旧文件；upsert `icon_libraries` 行（select-then-insert/update，捕获 IntegrityError 兜底）。
  5. **同域名批量更新**：遍历未删除竞品，`normalize_host(official_url) == host` 的逐个置 `logo_url = public_icon_url(...)`。
  6. 清缓存：`get_cache().delete(f"favicon:{host}")` 与 `f"favicon:www.{host}"`（favicon.clean_host 保留 www，两个 key 都要清）。
  7. commit，返回新的 `logo_url`。

---

## 二、前端

### 1. `frontend/src/api/admin.ts` 追加
- `AdminCompetitor` 类型（id/name/officialUrl/category/logoUrl/ownerUsername/ownerNickname/changes/todayChanges）。
- `listAdminCompetitors(): Promise<AdminCompetitor[]>`。
- `uploadCompetitorIcon(id, file)`：`new FormData()` append `file`，axios 对 FormData 自动设 multipart（`request.ts` 无需改）。

### 2. 新视图 `frontend/src/views/app/AdminCompetitors.vue`（参照 UserManage.vue）
- el-table：图标（CompetitorLogo，`src=logoUrl`、`domain=officialUrl`、`name`）、名称、官网、分类、所有者、变化数。
- 「图标」操作列 → 弹窗内 `el-upload :http-request="customUpload" :show-file-list="false" accept="image/png,image/jpeg,image/webp,image/gif"`，customUpload 调 `uploadCompetitorIcon`，成功后 `ElMessage.success` + 刷新列表。其余字段只读。

### 3. 路由与菜单
- `frontend/src/data/navMenu.ts`：加 `{ name: "AdminCompetitors", label: "全部竞品", icon: OfficeBuilding, adminOnly: true }`（`SideNav.vue` 已按 `user.is_admin` 过滤 adminOnly 项）。
- `frontend/src/router/index.ts`：`/app` children 加 `{ path: "all-competitors", component: AdminCompetitors, name: "AdminCompetitors" }`（懒加载 import）。

### 4. Mock `frontend/mock/`（admin 竞品 mock）
- 若无 `frontend/mock/admin.ts` 则新建：mock `GET /api/admin/competitors`（从 mock db 取竞品 + 拼 owner 字段）与 `POST /api/admin/competitors/:id/icon`。mock 模式无静态文件，图标自然走 CompetitorLogo 回退链，可接受。

---

## 三、种子数据

`D:\project\competitor-radar\.codebuddy\seed_mock_data.py` 末尾追加 `seed_icons(conn)`：
- 遍历 `COMPETITORS` 的 9 个已实测图标 URL，用 `urllib.request`（带 UA 头）下载到 `backend/storage/icons/{uuid}{ext}`；下载成功才 INSERT `icon_libraries`（domain=规范化 host、file_name、content_type、size、**含 created_at/updated_at**，脚本是 sqlite3 直连需自填时间），并把对应竞品行 `logo_url` 改为 `/api/icons/{file}`；下载失败跳过（保持原外部 URL）。
- 幂等：先 `DELETE FROM icon_libraries` 并清理目录旧文件（或按 domain upsert）。

---

## 四、验证

1. 后端测试：`cd backend && .venv\Scripts\python.exe -m pytest tests/ -q`（现有 105 条须全绿）；新增 `backend/tests/test_icon_library.py`：normalize_host 口径、上传校验（svg 拒绝/超限 400）、同域名批量更新、favicon 命库优先、非管理员 403。
2. 前端类型检查：`cd frontend && npm run type-check`（或 `npx vue-tsc --noEmit`）。
3. 迁移：`cd backend && .venv\Scripts\python.exe -m alembic upgrade head`。
4. 手动链路（backend `python run_dev.py` + 前端 `npm run dev`、mock 关闭）：
   - 管理员登录 → 侧边栏出现「全部竞品」→ 列表可见所有用户竞品 → 对某竞品上传图标 → 该竞品与同域名竞品立即换图；
   - `/api/icons/<file>` 直接 GET 200；
   - 普通用户新建同域名竞品 → logo 直接命中图标库；
   - 重启后端后图标仍在（磁盘 + DB 持久化）；
   - `python .codebuddy/seed_mock_data.py` 重跑 → 9 个竞品换成本地图标，脏数据可重放。

## 五、边界与风险
- mock 模式下 `/api/icons/*` 无文件 → 回退首字母，可接受。
- 生产多副本：`storage_dir` 为本地磁盘需共享卷；favicon 缓存清理在内存缓存下仅单实例生效（最多残留 24h 旧值），生产 CACHE_BACKEND=redis 可跨实例。
- 域名口径统一：图标库用「去 www + 小写」，上传后同时清 `favicon:{host}` 与 `favicon:www.{host}` 两个缓存 key。