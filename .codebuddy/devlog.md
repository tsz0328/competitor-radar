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
