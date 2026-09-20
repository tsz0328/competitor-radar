/** 抓取日志：一次抓取 = 一个监控源的一条记录（手动/定时统一沉淀） */
export interface CrawlLogItem {
  id: number;
  competitorId: number;
  competitorName: string;
  sourceId: number | null;
  sourceName: string;
  sourceType: string;
  url: string;
  /** manual=立即抓取 / scheduler=定时自动抓取 */
  trigger: "manual" | "scheduler";
  /** success / failed / skipped */
  status: "success" | "failed" | "skipped";
  httpStatus: number | null;
  /** 相比上次基准是否有变化 */
  changed: boolean;
  /** 是否首次抓取（建立基准） */
  firstTime: boolean;
  /** 本次是否生成了情报事件 */
  eventCreated: boolean;
  durationMs: number;
  error: string | null;
  createdAt: string;
}

/** 分页结果 */
export interface CrawlLogPage {
  items: CrawlLogItem[];
  total: number;
  page: number;
  pageSize: number;
}

/** 列表查询参数 */
export interface CrawlLogQuery {
  page: number;
  pageSize: number;
  status?: string;
  trigger?: string;
  competitorId?: number;
}
