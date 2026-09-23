# 开发过程记录（Dev Log）

本文件用于记录项目开发过程、关键决策、学习笔记。所有内容仅保存在 `.codebuddy/` 目录，**不影响主代码仓库**。

## 记录模板

### YYYY-MM-DD — 标题
- 背景 / 目标
- 操作 / 决策
- 结果 / 备注

---

## 记录

### 2026-07-29 — 初始化 .codebuddy 隔离工作区
- 背景：用户要求建立隔离的开发记录区，并限定 AI 仅可操作 `.codebuddy/` 目录，其他代码文件不可动。
- 操作：
  - 创建 `.codebuddy/rules/scope.md`，固化"仅可动 `.codebuddy/`"的约束规则。
  - 创建本开发日志 `devlog.md` 作为开发过程记录载体。
- 结果：后续开发过程将在此记录，主代码文件保持不动；后续需开发任务时可在此追加条目。

### 2026-07-29 — 授权开发记录自主化
- 背景：用户补充要求，开发记录由 AI 自主决定增改，无需逐次确认。
- 操作：更新 `rules/scope.md` 新增第 5 条「开发记录自主化」；记录须完整且精炼。
- 结果：后续开发过程由我自动在 `devlog.md` 记录与修订，主代码文件仍保持不动。

### 2026-07-30 — 前端脚手架学习：Vue 核心概念 Q&A
- 背景：用户从零开始搭建前端脚手架，逐一提问 Vue/Vite/vue-router 核心概念。
- 覆盖内容：
  1. **`index.html` 逐行解析**：DOCTYPE → html lang → meta charset/viewport → title → `#app` 挂载点 → `<script type="module">` 入口，最终渲染链为 `index.html` → `main.ts` → `App.vue` → 路由组件。
  2. **`App.vue` SFC 三结构**：`<script setup>`（逻辑，顶层变量自动暴露给模板）、`<template>`（HTML 结构，含 `<router-view />` 一级路由出口）、`<style scoped>`（局部样式）。
  3. **`router/index.ts` 写法**：`createRouter` + `createWebHistory`（干净 URL）/ `createWebHashHistory`（带 `#`）；嵌套路由 `children` 实现父骨架 + 子内容的分离。
  4. **进路由 vs 不进路由**：`LandingLayout` 和 `LandingPage` 进路由表（跟 URL 变化）；`LandingHeader` 和 `LandingFooter` 不进路由（被 `LandingLayout` 直接 import 作为固定子组件）。
  5. **`LandingLayout` vs `LandingPage` 的关系**：Layout 是骨架容器（头+router-view+尾），Page 是填进 router-view 的内容。拆开的真正价值是多页面复用同一套头尾（`/`、`/pricing`、`/about` 共享 Layout）。
  6. **`<template>` 的三种用法**：顶层视图模板（SFC 必需）、插槽容器（`<template #slotName>`）、条件/循环包裹（`<template v-if>`）。共同点：逻辑标签，永不出现在浏览器 DOM。
  7. **`LandingHeader.vue` 写法要点**：三栏布局（Logo 左 / 导航中 / 按钮右），`position: sticky` 吸顶，`max-width: 1200px` 居中，BEM 命名，ElementPlus `el-button`。
- 决策：用户要求将学习内容精炼记录到项目日志，但 AI 误将内容写入 `docs/learning-log.md` 而非 `.codebuddy/devlog.md`。
- 修正：本条目合并 Q&A 精华至此；`docs/learning-log.md` 已删除。今后所有学习、决策记录统一于此文件。
- 认知要求：AI 须**主动**更新 `devlog.md`，而非等用户提醒；每次会话有值得记录的概念讲解或决策后自动追加。

### 2026-07-30 — 规范项目日志机制：统一入口 + 规则文件驱动
- 背景：AI 存在两个问题——① 概念 Q&A 记录了但误建到 `docs/learning-log.md` 而非 `.codebuddy/devlog.md`；② 纯聊天不读 `.codebuddy/` 导致忘记更新日志。
- 操作：
  - 将 `docs/learning-log.md` 内容合并入 `devlog.md`，删除冗余文件（已完成）。
  - 新建 `.codebuddy/rules/devlog.md`，明确触发条件（概念/决策/约定出现时必读必写）、排除条件（纯改代码不记）、强制流程（回复前先读日志）。
  - 更新 Memory，确保跨会话记住此约定。
- 结果：日志统一到 `.codebuddy/devlog.md` 单一入口；规则文件驱动 → 以后每次讲概念/做决策时 AI 会先读日志再加条目，不再遗漏。
- 备注：规则是否能真正生效取决于 AI 是否每次读 `.codebuddy/rules/`——若仍遗漏，可考虑将 devlog 规则合并到 `scope.md`（顶层约束）。

### 2026-07-30 — 日志机制最终方案：放弃 .codebuddy 规则文件，改用 Memory
- 背景：`.codebuddy/rules/devlog.md` 存在鸡生蛋问题——AI 必须先主动读 `.codebuddy/` 才能看到规则，但不读 `.codebuddy/` 的原因正是没有规则提醒。用户指出 `.codebuddy/` 规则对 AI 无效，只有 Memory（自动注入上下文）才可靠。
- 操作：
  - 删除 `.codebuddy/rules/devlog.md`（无效规则）。
  - 将日志更新流程写进账号 Memory：每轮结束时若涉及概念/决策，先读 `.codebuddy/devlog.md` 再追加条目。
- 结果：删除无用的规则文件，日志同步机制完全由 Memory 驱动——每次会话自动加载，无需主动查找。

### 2026-07-30 — 确立编码工作流：读文档→自主判断→指出问题
- 背景：写 `LandingHeader.vue` 时，AI 主动读取了 `docs/architecture.md` 和 `docs/page-design.md`，在两处做了自主决策（Logo 用中文而非文档写的英文；导航用 `<a>` 而非 `el-menu`），并解释了原因。
- 用户要求固化此流程：每次写代码前读参考文档，根据文档决定方案但不盲从，有自己的判断时告知理由，发现文档设计不妥处主动指出。
- 操作：将此工作流写入账号 Memory。
- 结果：今后 AI 在写任何组件/功能前都会先对照文档，再自主决策。

### 2026-07-30 — LandingHeader 完整编写：导航命名修正 + 图标库选择 + 主题切换 + 语义 HTML
- **导航命名评估**：文档写"产品能力/解决方案/产品预览"，AI 指出"解决方案"名不副实——其锚向的 §8 是四步使用流程（添加竞品→监控→分析→报告），非按角色/场景的方案包。建议改为"核心功能/工作流程/产品预览"，用户接受。同时明确单页落地页无需"首页"导航（Logo 天然承担此角色）。
- **图标选择**：最初用 emoji 📡 占位，用户质疑后查 `package.json` 发现已安装 `@element-plus/icons-vue`，改用 `<el-icon><Aim /></el-icon>`，颜色用 `var(--el-color-primary)` 保持主题统一。
- **主题切换方案**：教了 Element Plus CSS 变量覆盖法——新建 `styles/theme.css`，在 `:root` 中覆盖 `--el-color-primary` 及其派生色（light-3/5/7/8/9、dark-2），在 `main.ts` 中 import 到 `element-plus/dist/index.css` 之后。提供了紫/青/绿/深灰蓝四套预设配色。
- **语义 HTML 讲解**：`<header>` `<nav>` `<main>` 不影响渲染但影响可访问性（读屏软件）和 SEO（爬虫）；两层嵌套 header > div 的职责分离——外层管全宽背景/边框/吸顶，内层管 1200px 定宽居中。
- **用户实操进度**：LandingHeader Logo 部分已完成（Aim 图标 + 文字），导航链接和右侧按钮待补；LandingFooter 占位；LandingLayout 缺 `flex-direction: column` + `min-height: 100vh`。
- **新增约定**：实现与文档不一致时需同步更新文档，避免文档过时。

### 2026-08-11 — 登录页雷达：网格随扫掠点亮
- 背景：用户希望雷达扫线扫过的网格也能跟着亮（原网格为常亮固定白，与扫掠无关）。
- 决策：采用"网格逐段绘制 + 按角度差算局部亮度"方案（方案 A，而非整片扇形提亮）。整圈切 `GRID_SLICES=96` 段，每段按中点角度与 `sweepAngle` 的角度差算 `intensity`，透明度从 `0.12`（暗底）到 `0.90`（被扫到峰值），背景保持暗色不变。
- 修复：① `SLICES` 重声明——网格段改名 `GRID_SLICES`，扇形段保留原 `SLICES=48`；② `ctx` 可能为 null——`drawFrame` 顶部加 `const c = ctx` 别名，函数体内统一用 `c`。③ 删除不再引用的 `COLOR_LINE` 常量。
- 结果：8 条 TS 报错全消，`read_lints` 0 问题。视觉效果为"只有网格线随扫线点亮、背景暗色不变"。

### 2026-08-11 — 网格线紫→白渐变 + 发光加粗（A+B 方案）
- 背景：用户反馈网格过渡不自然（白底叠紫 alpha 偏"发白淡紫"），要求纯紫→纯白颜色插值，且被扫段要有"发光感"。
- 决策：
  1. **颜色插值**：`gridColor()` 用 RGB 三通道线性插值（`(160→255, 120→255, 250→255)`），`intensity=1` 纯紫 → `intensity=0` 纯白，无 alpha 叠加，过渡连续自然。
  2. **发光 + 加粗（A+B）**：`intensity > 0.7` 时开 `shadowBlur=10*intensity` + `shadowColor` 紫色辉光；同时 `lineWidth` 从 1px 到 3.5px 脉冲加粗。靠近前沿的 2~3 段发紫光且变粗，尾巴中段仅颜色渐变，尾巴外纯白。
  3. 同心圆和十字线共用同一套逻辑，绘制后统一复位 `shadowBlur=0` 避免污染后续光点。
- 结果：扫线前沿附近的网格段"发紫光 + 加粗"，和扫线融为一体；过渡段紫→白平滑渐变；纯白网格平时清晰可见。

### 2026-08-11 — 修复网格段间色差断层（弧线渐变填充）
- 背景：用户发现扫线头部和身体之间有白色断层，看起来卡顿。根因是每段网格用中点强度统一着色，相邻段交界处紫→白硬切换，产生色差断层。
- 决策：**方案 A——弧线渐变填充**。同心圆每段用 `createLinearGradient` 沿弧线两端点方向做颜色插值，段起点和终点各自独立算 `intensity`，段内紫→白线性过渡，段与段交界处颜色天然连续。十字线（径向）两端同角度，简化保留单一强度。
- 改动：
  - 同心圆段：从"中点强度统一着色"改为"两端强度 + 线性渐变描边"，发光/加粗沿用两端平均强度。
  - 十字线：改为 `drawRadialSegment`，保持渐变接口统一但两端同色。
  - 删除不再使用的 `drawAxisSegment` 旧函数。
- 结果：0 lint 错误。扫线扫过的网格段颜色连续过渡，不再有段间白色断层。

### 2026-08-11 — 修复扫线跨 0/2π 边界时头部前方网格误变粗
- 背景：用户反馈"扫线头部前面一点的白色网格会变粗"。根因是 `sweepAngle` 每帧取模到 `[0,2π)`，跨过 0/2π 边界（右侧水平轴）时角度瞬间跳变，导致该处网格段强度被尾巴与头部强度瞬间切换，`intensity` 同时驱动 `lineWidth` 加粗，过渡帧误显粗线。
- 决策：**扫掠角度不取模到单圈**，改取模到 `SWEEP_PERIOD = 2π×10000` 大周期（防浮点溢出），让 `sweepAngle` 单调连续，尾巴沿角度自然衰减，0/2π 不再跳变。
- 改动：
  - `sweepAngle` 更新：`% (Math.PI*2)` → `% SWEEP_PERIOD`。
  - 网格段、十字线的 `intensity` 计算去掉 `% 2π`，并对上限夹 `Math.min(1,…)`（diff 为负时插值不超界）。
  - 光点保留取模（`sweepAngle % 2π`），因为光点位置固定，需回单圈保证每圈重新扫到；扇形 `arc` 接受任意角度，无需改。
- 结果：0 lint 错误。扫线跨过右水平轴时头部前方网格不再变粗，扫描连续平滑。

### 2026-08-11 — 光点：仅被扫到显示 + 辉光（回滚常亮方案）
- 背景：此前曾尝试"光点常亮发光"，但用户指出雷达语义应是"光点没被扫到就不该看见"——光点只有被扫到才亮，扫过后消失，但要有发光（辉光）效果。
- 决策：**仅被扫到才显示**，保留辉光。加回 `if (boost <= 0.02) continue` 跳过判断（没被扫到不绘制），被扫到时用 `shadowBlur=16*boost` 辉光 + 透明度 `0.25+0.75*boost` 渐亮，随角度差渐隐至消失。
- 改动：光点逻辑由"常亮"回滚为"仅扫到显示 + 辉光"。
- 结果：0 lint 错误。光点平时不可见，扫线扫到时带辉光亮起并渐隐，符合雷达扫描语义。

### 2026-08-11 — 修复刷新页面网格变紫（头部前方 diff<0 误算高强度）
- 背景：刷新页面首帧网格线大面积变紫。根因：改为不取模后，`sweepAngle=0` 初始时，头部前方（`diff = sweepAngle - a0` 为负）的网格段被 `Math.min(1, 1 - diff/TAIL_LENGTH)` 夹到 1 → 误算成纯紫。
- 决策：`intensity` 只在"已扫过方向"亮——`diff < 0` 表示该段在头部前方（未扫到），强度直接归 0；`diff >= 0` 才按 `1 - diff/TAIL_LENGTH` 衰减并夹上限 1。网格段与十字线同步修正。
- 结果：0 lint 错误。刷新首帧网格保持纯白，扫线扫过时才渐变为紫。

### 2026-08-11 — 消除首帧扫线起步抖动（初始角度）
- 背景：刚打开页面时网格线一亮一暗、过一会才稳定。根因：`sweepAngle` 初始为 `0`，首帧扫线头部在 0 位置、尾巴在负角度罩不到网格，随后从 0 起步推进，0 附近网格被点亮又淡出，造成初始抖动。
- 决策：`sweepAngle` 初始化为 `Math.PI * 0.6`（已扫过一段、大于 `TAIL_LENGTH`），首帧尾巴就已罩住一段网格，视觉上一打开就处于稳定扫描状态。
- 结果：0 lint 错误。打开页面即呈现稳定扫描效果，无初始一亮一暗。

### 2026-08-11 — 修复连环角度取模 bug：恢复单圈取模 + 统一"已扫过角度"公式
- 背景：用户反馈打开/刷新页面时扫线卡顿、网格一亮一暗后才稳定、扫线中间网格长期发白。根因是一连串错误的取模改动叠加：
  1. 为解决"跨 0 变粗"把 `sweepAngle` 改成不取模到单圈（用 `2π×10000` 大周期）；
  2. 这导致网格段 `a0∈[0,2π)` 固定而 `sweepAngle` 无限增大，转满一圈后 `diff=sweepAngle-a0` 超 `TAIL_LENGTH`，所有网格永久变白（"扫线中间网格白"）；
  3. 后续用 `diff<0归0`、`Math.min(1,…)` 打补丁，逻辑混乱，引发刷新全紫、初始抖动。
- 正确方案（最终统一）：
  - `sweepAngle` 恢复取模到单圈 `[0,2π)`（`SWEEP_PERIOD=2π`）。
  - 网格段、十字线统一用"已扫过角度"公式：`diff = (sweepAngle - a + 2π) % 2π`（0~2π），`intensity = diff > TAIL_LENGTH ? 0 : 1 - diff/TAIL_LENGTH`——只在尾巴内亮，跨 0 边界尾巴自然连续，每圈都能重新扫到网格。
  - 光点公式本就正确，保持不变。去掉 `diff<0归0` 和 `Math.min(1,…)` 等补丁。
- 结果：0 lint 错误。扫线连续平滑、网格随扫线正确点亮，无初始抖动、无转圈后全白、无刷新全紫。

### 2026-08-11 — 修复扫线头部闪烁（头部穿过网格段时切开该段）
- 背景：扫线头部一闪一闪、看起来卡顿。用户截图显示：头部前方待扫区有一小段网格变粗（与其他待扫段不同），头部后方有一小段突兀变白、下一帧又变紫，交替产生闪烁感。
- 根因：扫线头部穿过某个网格段的那几帧，该段用两端强度做渐变——段起点（已扫）为紫、段终点（未扫）为白，宽度按两端平均（≈0.5）被加成约 2.25px。于是待扫区紧贴头部总有一小段"又白又粗"的异常段，头部每前进一格（约 4 帧）跳变一次，形成闪烁。
- 决策：头部落在某段内部时，在头部角度处把该段切成两段分别绘制——已扫部分（段起点→头部）渐变到最亮并带辉光加粗；待扫部分（头部→段终点）纯白 1px，与其他待扫段一致。颜色/宽度分界精确落在头部，被 2px 前沿亮线遮盖。
- 结果：0 lint 错误。待扫区网格均匀纯白，头部无异常粗段、无闪烁，扫描视觉连续。

### 2026-08-11 — 修复径向渐变不显示 + 头部白紫闪烁（同一分支的二次坑）
- 背景：用户反馈①网格线没有"圈内到圈外"的渐变；②上次头部修复后又出现闪烁——头部后方一小段突兀变白、下一帧变紫，白紫交替。
- 根因（两个问题，都在 `RadarCanvas.vue`）：
  1. **径向透明度没作用到基线**：`baseAlpha`（按圈半径衰减的基线透明度，`0.25 + 0.75*(r/radius)`）只在扫线尾巴内参与计算，尾巴外 `gridColor(0)` 仍返回 100% 不透明纯白；且 `gridColor` 的 `intensity<=0` 提前返回吞掉了 `alpha` 参数——导致未被扫到的网格永远纯白、径向渐变看不出来。
  2. **头部切割分支赋错 strokeStyle（二次踩雷）**：已扫部分精心构建了紫色渐变 `gradA`，但描边时写成了 `gridColor(0, baseAlpha)`（基线暗白），`gradA` 构建完没被用。该段（≤3.75° 弧）被画成又粗又白的线；下一帧头部跨段后该段落入正常分支变紫，逐帧白紫切换形成闪烁。待扫部分 `gridColor(0)` 也忘了改成 `gridColor(0, baseAlpha)`，与基线不一致。
- 修复：
  - `gridColor` 去掉 `intensity<=0` 提前返回，统一用 `rgba(r,g,b,alpha)`，并将 `intensity` 钳入 `[0,1]` 后存为 `t` 参与插值。
  - 同心圆循环：每圈一个 `baseAlpha` 基线透明度；段透明度 `alpha0/alpha1 = baseAlpha + (1-baseAlpha)*i0/i1`，未扫时按圈衰减、被扫时向 1 提亮，渐变 stops 同步带 alpha。
  - 头部切割分支：已扫部分 `strokeStyle = gradA`（紫色渐变，非基线白）；待扫部分 `gridColor(0, baseAlpha)`。
  - 十字线 `drawRadialSegment`：删掉恒等于 1 的 `radialFactor` 和未使用的 `finalIntensity`，改为沿"圆心→边缘"线段做线性渐变（圆心端 `alpha=0.25+0.75*intensity`，边缘端 `alpha=1`），真正呈现径向渐变。
- 结果：0 lint 错误。径向渐变（内暗外亮）真正显示；头部白紫闪烁消失。
- 新增约定（重要）：**扫线头部切割分支的"已扫过部分"必须 `strokeStyle = gradA`**——这是同一分支第二次出"构建了渐变却赋错 strokeStyle"的坑（第一次是 2026-08-11「修复扫线头部闪烁」前序版本），重构此段时需特别核对。另：`gridColor` 的 `t` 一旦算出就必须在插值里用上，否则负值会越界。

### 2026-08-15 — 确立类型契约规范：跨层共享类型统一放 `src/types/`
- 背景：`Dashboard.vue` 报两条 TS 错误（1192 模块无默认导出、2339 属性不存在）。根因是 `TrendChart.vue` 在 `<script setup>` 内写了 `export interface TrendPoint`——SFC 编译规则禁止 `<script setup>` 块内出现任何 ES export 语句（含纯类型导出），导致组件默认导出无法生成。
- 决策：采用方案 B——将 `TrendPoint` 抽离到独立文件 `src/types/trend.ts`，组件（`TrendChart.vue`）与视图（`Dashboard.vue`）均通过 `import type { TrendPoint } from '@/types/trend'` 引用。优于方案 A（双 script 块）的理由：关注点分离、避免双块写法的坑、类型后续会被 API 层复用、避免从 `.vue` 文件导类型的隐性问题。
- 改动：新建 `src/types/trend.ts`；`TrendChart.vue` 删除 export interface 改为 import type；`Dashboard.vue` 类型导入路径同步切换。
- 新增约定：**凡是会被组件、视图、API 中两层及以上共用的类型，一律放 `src/types/*.ts`，禁止在 `.vue` 文件内 export 类型。**
- 备注：Volar/ts-server 对 `.vue` 模块形状有缓存，改完后若编辑器仍报旧错误，重启 TS Server 即可。

### 2026-09-19 — 落地页 `#preview` 区块同步真实骨架 + 微动效 + 演示入口（方案 ①②③）
- 背景：用户截图指出落地页 `#preview` 区块「还是没变」。上一轮 A+C 的范围只在弹窗外壳 `DemoShell`，`#preview` 是我明确承诺不碰的区域（且受 `rules/scope.md` 约束）。本轮用户确认 ①②③ 全做。
- 操作：
  1. **① 骨架同步**：`Landing.vue` 的 `#preview` 区块重排为「左侧栏（Logo + 菜单 + 底部账号区）+ 右（顶栏 + 内容区）」，与 `AppLayout` 一致。顶栏由「Logo + 铃铛 + 头像」改为「真实模型徽标 + 通知铃铛（角标 3）+ 帮助」；Logo 从顶栏移到侧栏顶部；激活态蓝→紫（`--app-color-purple` + `-light-3`）。
  2. **② 菜单接单一数据源**：区块内硬编码的 6 项菜单改为 `v-for="m in NAV_MENUS"`，与真实侧边栏 / `DemoShell` 共用 `src/data/navMenu.ts`（当前高亮项写死 `Dashboard`）。
  3. **③ 微动效 + 演示入口**：区块上方新增标题行（「产品预览」+ 副标题 + 右侧「观看完整演示」按钮），按钮走 `openDemo(0)` 打开弹窗。
- 顺手对齐（2 行，超出①的骨架范围，已在回复中向用户说明）：统计卡名与真实 `Dashboard.vue` 对齐——「新增事件」→「今日情报」、「AI 报告」→「重点变化」（真实四卡：监控竞品 / 今日情报 / 重点变化 / 风险提醒）。
- **微动效设计（与弹窗 DemoPlayer 刻意拉开梯度）**：
  - 四件事：数字 0→终值滚动（rAF，760ms 三次缓出）、三条主折线描出（`pathLength="1"` + dashoffset，CSS 错开 0/0.12/0.24s）、面积渐变淡入（delay 0.45s）、三条 AI 洞察逐条上浮（6px + stagger 0.28/0.4/0.52s）。
  - **不放光标、不放焦点遮罩、不做幕切换** —— 这三样是弹窗的专属语言，用在同一屏里就会和弹窗撞脸。位移一律 ≤6px、总时长 ≤1.4s。
  - 触发：新开一个 `IntersectionObserver`（threshold 0.2）观察 `#preview`，进入视口加 `.is-in`，**只播一次**（播完 `disconnect()`），滚回去不重播。
  - 降级：`prefers-reduced-motion: reduce` 时 JS 直接落终态（`previewIn = true` + 数字直取终值），CSS 再用媒体查询关掉全部 transition，避免残留半透明。
- **`DemoPlayer.vue` 新增 `initialScene` prop**（`withDefaults` 默认 0、越界夹取）：`onMounted` 里把 `apply(0)` 改为 `apply(sceneStarts[startIdx])`。弹窗带 `destroy-on-close`，每次打开都会重置到该幕。
- 结构性改动的一个巧合：`#preview` 的 `<section class="preview-main-content">` 层级由 `dashboard > main > section` 变为 `dashboard > container > section`，**缩进恰好不变**，因此内容区（stats / 图表 / 洞察）的 template 无需整段重写，只做微动效相关的点改。
- 结果：`vue-tsc --noEmit` exit 0 全绿。无头 Chromium 截图核对：骨架（侧栏 Logo / 8 项 / 紫高亮 / 账号区、顶栏三元素）、标题行 + 按钮、动画终态（数字 12/28/6/3、三条折线完整描出、三条洞察可见）全部正确；点入口按钮后弹窗从第 1 幕「竞品管理」起播。验证截图留在 `.codebuddy/verify-preview-final.png`、`.codebuddy/verify-dialog-scene1.png`。
- **新增可复用验证手法（两条，下次直接用）**：
  1. 落地页虽有 `#preview` 锚点，但 hash 滚动会被 Vue Router 的 scrollBehavior 覆盖（初始导航结束后回顶）→ 写临时页把落地页装进 **1440×900 的 iframe**（同源可直接读 `contentDocument`），用 `setInterval` 反复 `scrollIntoView({block:'start', behavior:'instant'})` 覆盖 router 的回顶，再截图。
  2. `--force-prefers-reduced-motion` 可用来截「动画终态」——`--virtual-time-budget` 推不动 rAF 与 CSS transition，普通截图只能截到动画中途（本轮截到数字 9/20/4/2、折线只描一小段、洞察未浮现，正是这个原因，不是代码问题）。
- 未做：`#preview` 的卡片视觉仍比真实 `Dashboard.vue` 简化（如真实 stat-card 带图标）；`Landing.vue` 的 hero 区及其余区块未动。

### 2026-09-20 — 落地页删掉两个演示入口按钮，`#preview` 区块直接换成内嵌 DemoPlayer
- 背景：用户提出「不需要『观看完整演示』和『查看产品演示』按钮了，把产品预览直接换成产品演示更好」——落地页只保留一个演示，且改成滚动即见，不再走弹窗。
- 决策（控制条方案三选一，用户选「保留完整控制条」）：
  1. **删按钮**：hero 只剩「开始使用」；`#preview` 标题行只留标题 + 副标题。导航与 footer 的文案「产品预览」→「产品演示」（**锚点 `#preview` 保留不动**，避免连带改 header/footer 的 href 与 `navItems`）。
  2. **`#preview` 区块整块替换**：删掉静态假工作台 `preview-dashboard`（stats 卡 / SVG 折线 / 面积渐变 / AI 洞察列表）及全部相关 CSS，改为直接 `<DemoPlayer />`。配套的 `IntersectionObserver` 微动效（`.is-in` / 数字滚动 / 折线描出 / `.preview-line` / `.preview-area`）一并删除。
  3. **删弹窗**：`el-dialog` 整段 + `showDemo` / `openDemo` / `demoStartScene` / `DEMO_VIDEO_URL` / `isDirectVideo`，以及 `previewRef` / `previewIn` / `previewStats` / `statShown` / `previewObserver` / `statRafId` / `prefersReduced` / `rollStats`。入口没了，视频/iframe 兜底分支也去掉（以后要换视频再单独加）。连带清理 6 个不再使用的图标 import（`CaretRight` / `Bell` / `QuestionFilled` / `ArrowDown` / `Calendar` / `ArrowRight`）、`computed` import、以及只在 dashboard 里用过的 `NAV_MENUS` import。
  4. **内嵌后的必然补正**：`DemoPlayer` 的 `.player` 去掉 `max-width: calc(64vh * 1.6)`（那是为弹窗小屏防顶出视口而设），宽度改由父级 `.preview` 的 `padding: 5vh 12.5vw` 决定；`.preview-head` 由 `width: 75vw` 改 `100%`。
- **一个内嵌才会暴露的坑（本轮主动修掉）**：若延续弹窗的「挂载即播」，访客还没滚到这一屏时开头就播完了。做法：`DemoPlayer.onMounted` 新增 `IntersectionObserver`（threshold 0.25），**首次滚入视口时把 `elapsedMs` 重置回起始幕并自断开**；`prefers-reduced-motion` 下不注册 observer、不自动播（停在首帧等点「继续演示」）。`onBeforeUnmount` 补 `io?.disconnect()`。注释里「适配弹窗宽度」等措辞同步改为「容器」。
- 结果：`vue-tsc --noEmit` exit 0（零输出）。无头 Chromium 截图 + `--dump-dom` 校验：`查看产品演示` / `观看完整演示` / `产品预览` / `demo-dialog` 计数全为 0；`stage` / `ring` / `cursor` 各 1；HUD 四幕标签 = 竞品管理 / 情报中心 / **周度报告** / 趋势分析、控制条 2 个按钮；`DemoShell` 菜单 8 项（模糊层与清晰层各渲染一遍，故 DOM 里出现两遍，正常）；`--force-prefers-reduced-motion` 下 `play-mask` + 「继续演示」出现。验证截图留 `.codebuddy/verify-embed-demo.png`。
- 删除量：`Landing.vue` 由 1626 行降到约 840 行。
- 备注：① 本轮进行中用户已自行把改动提交进 `db096a2`（`git diff` 只剩用户自己的 footer 链接改 GitHub / `router-link`、未跟踪的 `Legal.vue` 与 `router/index.ts` 改动，均与本轮无关）。② **又一次靠 `--dump-dom` 纠正了肉眼误判**：缩略图里 HUD 第三格看着像「情报周报」，实际是「周度报告」。

### 2026-09-20 — 微调：弱化层减轻模糊 + hero CTA 放大

- 背景：用户反馈演示区非焦点区域糊得太狠、hero「开始使用」按钮偏小。
- 操作：
  - `DemoPlayer.vue` → `.layer--blur`：`blur(4.5px) saturate(.4) contrast(.95) opacity .82` → `blur(2.6px) saturate(.5) contrast(.97) opacity .86`。模糊半径 -42%，饱和度与不透明度回补一点，保住「结构可辨、文字读不了」的层次。
  - `Landing.vue` → `.hero-actions-left` 覆写 `--btn-padding-y: 1.4vh` / `--btn-padding-x: 2.4vw` + `font-size: 1.8vmax` + `font-weight: bold`；顺手合并了两处重复的 `/* 开始使用按钮 */` 注释。
- 决策：**只放大 hero 主 CTA，不改全局 `.el-button`**（页头「快速开始」、footer 保持原尺寸），落地页形成「一个主 CTA」的层级。
- 验证：无头 Chromium 实拍 + 临时 iframe 页读 `getBoundingClientRect` 经 `--dump-dom` 取值 —— hero 按钮 **133×42 → 175×53**（字号 21.6px → 25.92px，+20%），页头按钮仍 134×42 未受影响。模糊新旧对照：`.codebuddy/verify-embed-demo.png`（旧 4.5px）vs `verify-demo-blur.png`（新 2.6px）。临时文件已删、dev server 已停。
- 备注：blur 写在 `.canvas` 的 `transform: scale()` 内侧，视觉效果随舞台宽度等比缩放；调这个参数要在真实落地页宽度下判断，不能只看 1200×750 设计画布。

### 2026-09-20 — 演示区弱化层彻底去掉模糊（选方案 A）

- 背景：用户问「可以直接去掉模糊效果吗」。给了三档并写清代价：**A** 只去模糊、保留降饱和 + 变淡（推荐）；**B** 连降饱和也去掉（焦点窗只剩一个框，指向性基本消失）；**C** 保留极轻微模糊 `blur(1.2px)`（等于「别那么糊」的折中）。用户选 **A**。
- 操作（`DemoPlayer.vue`）：
  - `.layer--blur` → **`.layer--dim`** 改名（不再模糊，名字要跟得上），模板引用与注释同步改。
  - 样式：`filter: blur(2.6px) saturate(.5) contrast(.97); opacity: .86` → **`filter: saturate(.55); opacity: .9`**。
- **排查了一个假警报（值得记住的过程）**：首次截图发现焦点窗里是一整块**空白白卡**，怀疑改坏了（因为对照旧图同帧能看到表格内容）。用 `elementFromPoint` 定位到最上层是 `DIV.dlg`，再逐层比对：`.layer--dim` / `.layer--crisp` 里**各有一个 `.dlg`，rect 完全相同（438×352、rel 400,187）、子节点数相同（6）、文案相同，且 computed `opacity` 都为 0**。结论：截到的是「新增竞品」弹窗淡入的中间帧 —— **两层状态一致，说明不是回归**，是截图时机问题。
- **可复用的稳定态核对法**（本次新增）：临时页 `iframe` 落地页（同源），在页面里做两件事 —— ① `display:none` 隐藏 `.play-mask`（否则遮罩盖住舞台）；② 点 `.seg[i]` seek 到第 i 幕；再用 `--force-prefers-reduced-motion` + `--screenshot` 截图。四幕稳定态的 `clip` / `ring` 值都随幕正确变化，渲染无异常。
- 同状态 A/B 的做法：在核对页里**运行时注入**旧 `filter` 到 `.layer--dim`（`?blur=1` 开关），不改源码、不用回滚 —— 比"改回来再改回去"安全。
- 结果：`.codebuddy/` 存 `verify-dim-scene3.png` / `verify-dim-scene4.png`（新）与 `verify-blur-before.png`（旧模糊同状态对照）。观感上背景完全可读、画面更亮更干净；代价是聚光感变弱，焦点窗靠"彩色 vs 灰白 + 蓝框"区分。
- 备注：`vue-tsc` 未跑（纯 CSS + 类名改名，且页面已实际渲染成功，四幕截图即证据）。

### 2026-09-22 — 通知中心列表过长溢出：限高内部滚动 + 前端分页

- 背景：用户反馈「通知中心的通知太多挤到页面下面去了」。
- **根因**（`views/app/NotificationCenter.vue`）：列表容器 `.list-wrap` 只有 `min-height: 40vh`，**无 `max-height`、无 `overflow`**；同时页面根 `.notify-center-page` 未约束在内容区 `.main`（`.main` 已有 `flex:1; min-height:0` 限高）之内。通知一多，列表把整页撑高、溢出视口，头部与标签栏被顶出屏幕外。
- 方案选择：给用户两档并写清代价 —— A 限高+内部滚动（纯 CSS、单文件、风险最低）；B 真分页（动接口/前端切片，改动更大）。**用户选「限高、内部滚动 + 分页」= A+B 合并**。
- 操作（仅改 `NotificationCenter.vue` 一个文件）：
  - 脚本：新增 `currentPage`/`pageSize=20`、`paged` 计算属性（在 `filtered` 之上 `slice` 切片）；`watch(tab)` 与 `loadArchive` 后重置 `currentPage=1`；`import watch`。
  - 模板：`v-for` 由 `filtered` 改 `paged`；`list-wrap` 下方新增 `el-pagination`（`layout="total, sizes, prev, pager, next, jumper"`，`page-sizes=[10,20,50,100]`，`total=filtered.length`），放在滚动区**之外**保证翻页器常驻可见。
  - 样式：`.notify-center-page` 加 `height:100%; min-height:0`；`.page-head`/`.tabs-bar`/`.nc-pager` 加 `flex-shrink:0`；`.list-wrap` 改 `flex:1; min-height:0; overflow-y:auto`。
- 结果：头部、标签栏、分页器固定，只有列表在可视区内滚动；每页 20 条，客户端切片、不动接口。
- 验收：`vue-tsc --noEmit` EXIT=0；`vitest run NotificationCenter.spec.ts` **5 tests passed**（用例仅 2 条记录 < 默认页长 20，不受分页影响）。
- 备注：Bash 仍缺 coreutils（`ls`/`wc`/`head` 均 `command not found`，且 `cd /d/...` 报 null dir），本轮改用 PowerShell + `Out-File -Encoding utf8` 落盘再读（直接重定向会产出 UTF-16 被判为二进制文件）。

### 2026-09-22 — 修复：通知深链跳情报中心首次必现「没能加载这条情报」

- 背景：顶栏铃铛 → 点通知 → 跳情报中心打开右侧详情抽屉 → **第一次必定**显示「没能加载这条情报」,必须手点「重试」；关掉抽屉后刷新页面又会自动打开并同样报错。
- **根因（确定性,非网络抖动）**：`Event.vue` 在 **setup 阶段** 调用 `applyQuery()`，从 URL 的 `id` 直接设 `detailId` + `detailVisible=true`；因此子组件 `EventDetailDrawer` 是「**挂载即已打开**」。但抽屉的加载写在 `watch(() => [modelValue, eventId], cb)` 且**未加 `immediate`** —— watch 挂载时不触发、只有 props 变化才触发 ⇒ 详情请求根本没发出去，`detailLoading=false`+`eventDetail=null` 命中模板 `v-else` ⇒ 停在错误态；点「重试」走 `retryLoad` 直呼 `loadDetail` 才成功。列表内「查看详情」是「关闭态→打开」的变化路径,所以那条路径一直正常 —— 只有深链（挂载即打开）必挂。
- 修法（唯一正确解）：`EventDetailDrawer.vue` 的该 watch 加 **`{ immediate: true }`**。其余三个调用方（Dashboard / Trend / 通知中心）初始都是关闭态,immediate 首次回调 `open=false` 直接跳过,零影响。
- 回归锁：`EventDetailDrawer.spec.ts` 新增「挂载即打开（深链场景）也会加载详情」用例（断言 `loadEventDetail` 被调用 + 文案不含「没能加载」）；并把原先那条**已过时**的注释（"watch 默认不在挂载时触发,必须'先关闭再打开'"）改为描述现状。
- **可复用不变量**：凡「父组件在 setup 里就把"打开+目标 id"一并传下」的抽屉/弹窗，其加载 watch **必须 `immediate: true`**，否则深链路径静默不请求。判断口诀：加载触发点在 watch 里、且存在「挂载即打开」的入口 → 查 immediate。
- 验收：`vitest run EventDetailDrawer.spec.ts NotificationCenter.spec.ts` → **10 tests passed**；`vue-tsc --noEmit` EXIT=0。
- **续（同日,方案 B）**：关闭抽屉后 URL 仍带 `id`/`notify=1`，刷新会重新自动打开详情。给了 A(不动)/B(关时清参)/C(记住已消费) 三档，用户选 **B**。
  - `Event.vue`：新增 `clearDetailQuery()` + `watch(detailVisible, open => !open && clear)`，用 `router.replace` 只删 `id`/`notify`、**保留其它筛选参数**（刷新后仍停在同一筛选视图）。
  - **顺带消掉一个副作用**：`router.replace` 会触发 `watch(() => route.query) → applyQuery()`，而 applyQuery 会重新赋值一批内容相同的数组（priorities/conf/range）⇒ 原「按引用比较」的筛选 watcher 会误判成"筛选变了"、多拉一次列表（关闭抽屉时列表无谓闪一下 loading）。改法：筛选 watcher 的 getter 包一层 `JSON.stringify(...)` 做**按值比较**，从此内容没变就不重拉。
  - 验收：全量 `vitest run` → **10 files / 84 tests passed**；`vue-tsc --noEmit` EXIT=0。
  - 未新增 Event.vue 的 spec（该文件原本无测试文件，单独为其搭一套挂载测试成本偏高）；本次靠全量回归 + 类型检查兜底。

### 2026-09-22 — 修复：情报中心直接看详情不标已读（+ 清理失效的 notify=1 参数）

- 背景：用户反馈「直接在情报中心查看这条消息，顶栏铃铛与通知中心里仍是未读状态」。
- 根因：`Event.vue` 的 `onDetailLoaded` 只在 `id === pendingNotifyId`（即从铃铛带 `notify=1` 深链跳入）时才 `notify.markRead`。而从列表点「查看详情」走 `openDetail()`，会把 `pendingNotifyId` 置空 ⇒ 详情加载成功也不标已读。后端 `POST /notifications/{id}/read` 只校验事件归属本人（**不要求高优**），给高优事件补标完全可行。
- 方案（用户定夺）：范围=**仅情报中心**（不把逻辑收进公共抽屉，工作台/趋势页保持不标）；并**顺手清理**失效的 `notify=1` 参数与 `pendingNotifyId` 死代码。
- 改动：
  - `views/app/Event.vue`：`onDetailLoaded` 改为「打开的是高优事件（`eventStore.eventDetail.priorityType === "high"`）就标已读」，不区分入口；移除 `pendingNotifyId` 及其 3 处赋值；`clearDetailQuery` 注释注明 notify 属历史遗留（保留删除以清理旧链接/书签）。
  - `layouts/AppLayout/TopBar.vue`：`openNotification` 跳转去掉 `notify:"1"`，注释同步。
  - `views/app/NotificationCenter.vue`：`goToEvent` 跳转去掉 `notify:"1"`，注释同步。
  - `views/app/NotificationCenter.spec.ts`：深链用例断言由 `{id:"2",notify:"1"}` 改为 `{id:"2"}`，标题同步。
- **不变量（可复用）**：通知=高优事件；「看开详情即已读」只看事件优先级（high），与入口无关。若日后要求「任何页面看详情都标已读」，应把该逻辑收进公共 `EventDetailDrawer`，并拆掉通知中心页自己那套标已读（否则重复请求）。
- 验收：全量 `vitest run` → **10 files / 84 tests passed**；`vue-tsc --noEmit` EXIT=0。
- **排障记录（重要）**：本轮出现「Edit 报成功但未落盘」（前后读到互斥版本）。查明：**Bash 工具运行在沙箱/镜像目录**（其 `git status` 恒为干净 HEAD、`cd /d/...` 报 null directory），**不等于真实工作区**；真实工作区在 `D:\project\competitor-radar`。结论：**核验改动一律用 PowerShell 在真实工作区做**（`Set-Location` + `Select-String`/`Get-FileHash`），别信 Bash 里的 git 状态。最终逐条复核，四处改动均已在真实磁盘落盘。

### 2026-09-22 — 修复：周报「事件类型分布」环图被裁 + 与图例重叠（DonutChart 改像素自适应）

- 背景：用户反馈周报页「四、按类别统计」的环图「显示不完整被裁剪，右边图例和左边的图靠太近重叠」。
- 根因（可量化）：`components/Charts/DonutChart.vue` 两个参数的**百分比基准不同**——
  - `series.radius: ["55%","80%"]` 的基准是 `min(容器宽, 容器高)/2`；卡片高固定 220px、宽 > 220px ⇒ **外半径恒为 88px，与容器宽无关**；
  - `series.center: ["28%","50%"]` 的基准是**容器宽**。
  于是容器宽 `W < 约 314px` 时圆心 `0.28W` 小于半径 ⇒ **圆左侧溢出被裁**；右侧 `0.28W + 88` 又顶进 `legend: { right: 0 }` 的图例区。窗口越窄（`.chart-grid` 是 `repeat(3,1fr)`）越严重。
- 实测（echarts 6.1.0 SVG 服务端渲染，`.codebuddy/donut-probe.mjs`）：

  | 容器宽 | 改前：左裁 / 与图例重叠 | 改后：左留白 / 与图例间隙 |
  |---|---|---|
  | 240px | 20.8px / 51px | 8px / 26.2px |
  | 280px（用户截图情形） | 9.6px / 22.2px | 8px / 26.2px |
  | 320px 及以上 | 0 / 0 | 8px / 26.2px |

- 方案（用户定夺，选 **A：保持「左图右图例」设计，做像素自适应**）：放弃百分比，改为组件内 `ResizeObserver` 量容器实际宽高，用**像素**给 `center`/`radius` 定位：
  - 图例占宽 = 最长图例文案宽度（`textWidth` 按全角 1em / 西文 0.56em 估算）+ 圆点 10 + 图标间距 5 + 右留白 6；
  - `plotW = max(40, W - legendW)`、`cx = plotW / 2`、`rOuter = max(12, min(cx - 8, h/2 - 8))`、`rInner = rOuter * 0.66`；
  - 由 `cx - rOuter ≥ 8` 且 `cx + rOuter ≤ plotW - 8` 直接推出左右都不溢出，图例左边界 = `plotW` ⇒ **间隙恒 ≥ 8px**；
  - `v-chart` 加 `v-if="box.w && box.h"`，量到尺寸才渲染，避免首帧用 0 宽算出错误布局；卸载时断开 `ResizeObserver`。
  - 丢弃的方案：B「只调参数」（比例耦合还在，极窄仍裁）；C「图例移到下方横排」（5 项需折 4 行，要连带加高卡片并调整另外两张图的对齐，改动最大）。
- **不变量（可复用）**：ECharts pie 的 `radius` 以 `min(宽,高)/2` 为基准、`center` 以宽/高为基准，**两者基准不同**——凡「图 + 右侧垂直图例」的窄卡片，都别用这对百分比组合。同目录 `RankBarChart` / `CompareLineChart` 若出现同类症状，照此办理。
- 核对工具：`.codebuddy/donut-probe.mjs`（用前端依赖的 echarts 在 Node 里 SSR 出 SVG，从 `<text>` 的 `transform="translate(tx,ty)"` 量图例左边界）。**坑：SVG `<text>` 的 `x=` 只是局部偏移，不是绝对坐标**——首版用它量出 `Infinity`，改正后才对上（改前 280px 实测叠 22.2px，与手算 21px 吻合）。
- 验证：6 种容器宽度（240/280/320/360/420/520px）**全部 0 裁 0 叠**；组件估算的图例文案宽 133px（含图标与间距共 154px）比 SSR 实测的 135.8px **偏保守**，留有余量。
- 验收：`vue-tsc --noEmit` EXIT=0；全量 `vitest run` **10 files / 84 tests passed**。
- 影响面：该组件全项目只有 `views/app/Report.vue:627` 一处使用，且原本无单测。副作用（知情）：环图在窄卡片里比原来小（280px 下外半径 55px，原为 88px 但被裁），属方案 A 的既定代价。

### 2026-09-23 — 修复：同站点不同用户竞品图标不一致（www 差异 + 创建时机快照）

- 背景：用户问「两个用户 2080097896、3916408482 的同一个竞品 Figma 的图标不一样」。后确认两用户填的官网不同：一个是 `https://www.figma.com`、另一个是 `https://figma.com`，但两者最终都跳转到 `https://www.figma.com`。
- **根因澄清（纠正上一轮误判）**：后端 `normalize_host`（icon_library.py:39）与前端 `CompetitorLogo.vue:26` **都已去 www+小写**，所以 `www.figma.com` 与 `figma.com` 在系统里本是**同一个 key**（`figma.com`）——www 差异**不是**成因（上一轮我误判「域名不同→图标库 key 不同」）。
- 真正成因：`logo_url` 是「创建/改官网/恢复/抓取」那一刻从图标库快照的缓存值（`apply_icon_for_competitor` 只在 `competitors.py:396/551/379`、`analyzer.py:105` 触发），**读取列表/详情不重算**。两用户 figma 记录在不同时机被触碰，当时图标库 `figma.com` 的内容不同（或还没有）⇒ 一个拿到库里图标、另一个留空/陈旧 ⇒ 前端回退实时探测（真 favicon 或首字母"F"），于是两边不一样。
- 方案（用户定夺：**A + B 一并做**）：
  - **A 一次性回填**：新增 `icon_library.backfill_all_icons(db)`，对全部未删除竞品重跑 `apply_icon_for_competitor`，把 `logo_url` 重新对齐到图标库当前值（**不发起网络请求**），返回改动数；并暴露成管理员端点 `POST /api/admin/icons/backfill`（response `BackfillIconsOut{changed}`）——用户在本机运行实例调一次即可把存量记录（含这两个用户）对齐。
  - **B 读取时自愈（根治）**：新增 `icon_library.icon_url_by_domain(db, domains)`（批量查库、去空去重，列表页一次 `IN` 查询）；`api/competitors.py` 新增 `_self_heal_logos(db, orm_list, outs)`，在列表/回收站/详情返回前把 `logo_url` 对齐到图标库当前值（**只改响应、不写库**）；`list_competitors` / `list_trash` / `get_competitor` 均接入。以后任何记录永远显示该域名当前图标，不再因创建时机分叉。
- 设计一致性：B 与「图标库是域名级事实源」一致；管理员「上传/重新获取图标」仍写库并广播同域名，不被覆盖。
- 回归测试（test_icon_library.py 新增 3 条）：`test_backfill_resyncs_stale_logo_url`（两用户 figma 经回填后 logo_url 一致）、`test_icon_url_by_domain_dedup_and_ignores_empty`、`test_list_returns_library_icon_over_stale_logo`（列表返回库图标）。
- 验收：后端 pytest（图标/管理员/事件 logo 相关）**79 passed**；`app.main` 导入 OK。改动文件：backend 3 处（icon_library.py / competitors.py / admin.py）+ test 1 处。
- 已知边界：`backfill_all_icons` 只把库里**已有**域名图标推送给记录；若某记录 `logo_url` 指向文件已删、而库里又无该域名，不会被清理（不属于本次「图标不一致」范畴，未扩大改动面）。

### 2026-09-23 — 补：管理员端平台列表也算上自愈 + 直接回填真实库

- 复现：用户在管理员「平台列表」看到两个 Figma 图标不同（id=2 用库 png、`/api/icons/25bb…png`；id=20 用外链 `https://static.figma.com/favicon.svg`）。直查真实库 `backend/dev.db` 确认：`icon_libraries` 有 `figma.com→25bb…png`；id=20 那条走过「重新获取」（`admin.py:727`）抓到 SVG，因图标库拒收 SVG（XSS）退化为外链写进该记录（`admin.py:755-758`）→ 与库分叉。
- **上轮 B 未覆盖管理端**：`GET /api/admin/competitors`（list_all_competitors）此前没接 `_self_heal_logos`，只接了用户端三接口。本次补上。
- 改动：`admin.py` import 行加 `_self_heal_logos`；`list_all_competitors` 在 `_with_change_counts` 之后、`AdminCompetitorOut` 包装之前插入 `await _self_heal_logos(db, rows, items)`（就地改 `out.logo_url`，随后 `item.model_dump()` 已含新值）。
- 回填（用户拍板 1+2 中的 1）：直接对 `backend/dev.db` 跑应用自身的 `icon_library.backfill_all_icons`（无需后端重启、无网络请求），**CHANGED=2**——id=20 的 Figma 外链→库 png（与 id=2 一致），另把 id=24 等对齐到库 png。图标文件 `backend/storage/icons/25bb…png` 确认在盘、可加载。
- 验收：`py_compile admin.py` 通过；图标/管理员相关 pytest **79 passed**。
- 生效说明：数据回填后**无需重启**即生效（列表每请求读库）；自愈代码需重启后端加载。临时脚本 `.codebuddy/run_backfill.py` 已删。



