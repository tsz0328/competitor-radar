/**
 * 侧边栏菜单的**唯一数据源**
 *
 * 两个消费方都从这里取菜单，避免改名 / 增删菜单时两边不同步：
 *   1. 真实侧边栏 `layouts/AppLayout/SideNav.vue`
 *   2. 落地页演示的假外壳 `components/DemoPlayer/DemoShell.vue`
 *
 * 背景：`docs/page-design.md` 记过两次导航改名（情报事件→情报中心、
 * 周报→周度报告），当时靠人工同步落地页预览，容易漏。集中到这里后
 * 改名只需改一处。
 *
 * 注意：演示外壳会展示全部菜单（含 adminOnly 项），因为它演的是
 * 管理员视角的产品全貌；真实侧边栏按登录用户权限过滤。
 */
import type { Component } from "vue";
import {
  OfficeBuilding,
  List,
  Document,
  TrendCharts,
  Setting,
  HomeFilled,
  Tickets,
  UserFilled,
} from "@element-plus/icons-vue";

export interface NavMenuItem {
  /** 路由 name，同时作为菜单高亮键 */
  name: string;
  /** 菜单显示名 */
  label: string;
  /** 菜单图标 */
  icon: Component;
  /** 是否仅管理员可见 */
  adminOnly: boolean;
}

export const NAV_MENUS: NavMenuItem[] = [
  { name: "Dashboard", label: "工作台", icon: HomeFilled, adminOnly: false },
  {
    name: "Competitor",
    label: "竞品管理",
    icon: OfficeBuilding,
    adminOnly: false,
  },
  { name: "CrawlLog", label: "抓取日志", icon: Tickets, adminOnly: false },
  { name: "Event", label: "情报中心", icon: List, adminOnly: false },
  { name: "Report", label: "周度报告", icon: Document, adminOnly: false },
  { name: "Trend", label: "趋势分析", icon: TrendCharts, adminOnly: false },
  { name: "Setting", label: "设置", icon: Setting, adminOnly: false },
  // 用户管理仅管理员可见
  { name: "UserManage", label: "用户管理", icon: UserFilled, adminOnly: true },
];
