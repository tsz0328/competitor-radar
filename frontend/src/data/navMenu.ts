/**
 * 侧边栏菜单的**唯一数据源**
 *
 * 三个消费方都从这里取菜单，避免改名 / 增删菜单时多处不同步：
 *   1. 真实侧边栏 `layouts/AppLayout/SideNav.vue`——按登录角色选 USER / ADMIN 两套之一
 *   2. 落地页演示的假外壳 `components/DemoPlayer/DemoShell.vue`——用合并全量 NAV_MENUS
 *
 * 背景：`docs/page-design.md` 记过两次导航改名（情报事件→情报中心、
 * 周报→周度报告），当时靠人工同步落地页预览，容易漏。集中到这里后
 * 改名只需改一处。
 *
 * 管理员端是「管用户数据」的管理后台：登录后只看到 ADMIN 菜单
 * （平台总览 / 用户管理 / 系统设置 / 全部竞品），不进用户业务页。
 */
import type { Component } from "vue";
import {
  DataAnalysis,
  OfficeBuilding,
  List,
  Document,
  TrendCharts,
  Setting,
  HomeFilled,
  Tickets,
  UserFilled,
  Delete,
  Memo,
  Bell,
} from "@element-plus/icons-vue";

export interface NavMenuItem {
  /** 路由 name，同时作为菜单高亮键 */
  name: string;
  /** 菜单显示名 */
  label: string;
  /** 菜单图标 */
  icon: Component;
}

/** 普通用户菜单：完整业务功能（核心业务在前，辅助/后台功能在后） */
export const USER_NAV_MENUS: NavMenuItem[] = [
  { name: "Dashboard", label: "工作台", icon: HomeFilled },
  {
    name: "Competitor",
    label: "竞品管理",
    icon: OfficeBuilding,
  },
  { name: "Event", label: "情报中心", icon: List },
  { name: "Report", label: "周度报告", icon: Document },
  { name: "Trend", label: "趋势分析", icon: TrendCharts },
  { name: "CrawlLog", label: "抓取日志", icon: Tickets },
  { name: "NotificationCenter", label: "通知中心", icon: Bell },
  {
    name: "Trash",
    label: "回收站",
    icon: Delete,
  },
  { name: "Setting", label: "设置", icon: Setting },
];

/** 管理后台菜单：管用户数据（仅管理员可见），系统设置放末尾 */
export const ADMIN_NAV_MENUS: NavMenuItem[] = [
  { name: "AdminOverview", label: "平台总览", icon: DataAnalysis },
  { name: "UserManage", label: "用户管理", icon: UserFilled },
  { name: "AdminData", label: "平台数据", icon: List },
  { name: "AdminAuditLog", label: "审计日志", icon: Memo },
  {
    name: "AdminCompetitors",
    label: "全部竞品",
    icon: OfficeBuilding,
  },
  { name: "AdminSettings", label: "系统设置", icon: Setting },
];