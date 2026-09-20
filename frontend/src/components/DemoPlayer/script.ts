/**
 * 落地页「产品演示」剧本
 *
 * 坐标系：固定设计画布 1200 × 750（见 DESIGN_W / DESIGN_H）。
 * 所有 focus / cursor 的 x、y、w、h 都是这块画布内的 px，
 * 由 DemoPlayer 统一缩放到容器实际尺寸，所以这里可以按 1:1 手摆位置。
 *
 * 画布布局（与 DemoShell.vue 对齐，按真实 AppLayout 的比例单位换算）：
 *   侧边栏   0,   0,  180, 750   （15vw）
 *   顶栏   180,   0, 1020,  60   （8vh）
 *   内容区 180,  60, 1020, 690   （内边距 20 / 22）
 *
 * 锚定规则：内容区右边界（1178）与下边界（730）不受侧栏宽度变化影响，
 * 所以右对齐 / 贴底的元素 x 不变，只有左对齐元素随内容区起点左移而左移。
 */

/** 设计画布宽 */
export const DESIGN_W = 1200;
/** 设计画布高 */
export const DESIGN_H = 750;

/** 焦点窗口矩形：窗口内保持清晰，窗口外模糊降饱和 */
export interface DemoFocus {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 一个演示步骤 */
export interface DemoStep {
  /** 步骤名，仅用于调试与无障碍描述 */
  name: string;
  /** 假光标位置（设计画布坐标）；不填则沿用上一步位置 */
  cursor?: { x: number; y: number };
  /** 该步的焦点窗口；不填则沿用本幕的默认 focus */
  focus?: DemoFocus;
}

/** 一幕演示 = 一个侧边栏菜单页 */
export interface DemoScene {
  /** 唯一 id */
  id: string;
  /** 侧边栏高亮项，与真实菜单 name 对齐 */
  menu: string;
  /** 中文菜单名，显示在 HUD 上 */
  menuLabel: string;
  /** 这一幕在讲什么，显示在 HUD 上 */
  caption: string;
  /** 本幕默认焦点窗口 */
  focus: DemoFocus;
  /** 单步时长（毫秒） */
  stepMs: number;
  steps: DemoStep[];
}

/** 幕与幕之间留白的时长：让焦点窗口有时间滑过去 */
export const SCENE_GAP_MS = 900;

/**
 * 四幕主流程：
 * 添加竞品 → 抓到情报 → 生成周报 → 看出趋势
 */
export const SCENES: DemoScene[] = [
  {
    id: "competitor",
    menu: "Competitor",
    menuLabel: "竞品管理",
    caption: "把要盯的竞品加进来",
    // 新增弹窗实测 430,204,520,402（居中，中心 x=690），四周留 14px
    focus: { x: 416, y: 190, w: 548, h: 430 },
    stepMs: 2100,
    steps: [
      { name: "点新增竞品", cursor: { x: 1118, y: 98 } },
      { name: "填竞品名称", cursor: { x: 690, y: 292 } },
      { name: "自动找到监控页面", cursor: { x: 860, y: 368 } },
      { name: "确认频率并保存", cursor: { x: 849, y: 557 } },
    ],
  },
  {
    id: "event",
    menu: "Event",
    menuLabel: "情报中心",
    caption: "抓取比对，找出「变了什么」",
    // 左对齐列表：随内容区起点左移
    focus: { x: 186, y: 64, w: 540, h: 640 },
    stepMs: 2100,
    steps: [
      { name: "打开情报流", cursor: { x: 320, y: 254 } },
      { name: "选中一条变化", cursor: { x: 550, y: 204 } },
      {
        name: "展开差异详情",
        cursor: { x: 970, y: 254 },
        // 右侧抽屉实测 752,60,448,688（贴内容区右边界），右边收 10px 留出舞台边框
        focus: { x: 738, y: 60, w: 452, h: 686 },
      },
      {
        name: "读 AI 的影响判断",
        cursor: { x: 970, y: 504 },
        focus: { x: 738, y: 60, w: 452, h: 686 },
      },
    ],
  },
  {
    id: "report",
    menu: "Report",
    menuLabel: "周度报告",
    caption: "一键把这周的情报写成周报",
    // 右对齐主栏：右边界固定，x 不随侧栏变化
    focus: { x: 396, y: 80, w: 782, h: 640 },
    stepMs: 2200,
    steps: [
      { name: "点生成周报", cursor: { x: 1112, y: 98 } },
      { name: "AI 正在汇总", cursor: { x: 695, y: 224 } },
      { name: "逐条读本周重点", cursor: { x: 695, y: 334 } },
      {
        name: "看核心数据",
        cursor: { x: 1080, y: 664 },
        focus: { x: 424, y: 470, w: 750, h: 264 },
      },
    ],
  },
  {
    id: "trend",
    menu: "Trend",
    menuLabel: "趋势分析",
    caption: "把零散变化读成一条走向",
    // 左对齐主栏：随内容区起点左移
    focus: { x: 186, y: 126, w: 674, h: 610 },
    stepMs: 2100,
    steps: [
      { name: "选观察范围", cursor: { x: 900, y: 102 } },
      { name: "曲线铺开", cursor: { x: 530, y: 444 } },
      { name: "叠加竞品对比", cursor: { x: 530, y: 624 } },
      {
        name: "读 AI 趋势洞察",
        cursor: { x: 1150, y: 304 },
        // AI 洞察卡实测 870,141,308,234，四周留 14px；
        // 下面的「竞品活跃度」卡从 y=387 起，不框进来
        focus: { x: 856, y: 127, w: 334, h: 262 },
      },
    ],
  },
];

/** 一整轮演示的时长（毫秒） */
export const TOTAL_MS = SCENES.reduce(
  (sum, scene) => sum + scene.stepMs * scene.steps.length + SCENE_GAP_MS,
  0,
);
