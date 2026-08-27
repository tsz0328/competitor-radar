/**
 * 竞品监控列表数据模型
 * 供 API 层、stores、视图层共用
 */
export interface CompetitorItem {
  id: number;
  name: string;
  domain: string;
  logoUrl?: string;
  /** 分类标签，如 SaaS工具 / AI产品 */
  category: string;
  /** 分类标签样式类型 */
  categoryType: "saas" | "ai" | "brand" | "ecommerce";
  /** 一句话描述 */
  desc: string;
  /** 监控页面名称列表 */
  pages: string[];
  /** 折叠的额外页面数量 */
  extraPages: number;
  /** 监控频率，如 每天 08:00 */
  frequency: string;
  frequencyDesc: string;
  /** 最近抓取相对时间，如 2 小时前 */
  lastFetchAgo: string;
  /** 最近抓取绝对时间 */
  lastFetchTime: string;
  /** 监控开关：true=开启，false=暂停 */
  enabled: boolean;
  /** 状态：监控中 / 监控异常 / 已暂停 */
  status: string;
  statusType: "success" | "warning" | "info";
  statusDesc: string;
  /** 最近变化条数 */
  changes: number;
  /** 今日新增变化 */
  todayChanges: number;
}
