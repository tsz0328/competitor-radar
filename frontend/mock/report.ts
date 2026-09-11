import { MockMethod } from "vite-plugin-mock";
import type { ReportDetail, ReportListItem } from "@/types/report";

// 报告列表原始数据
const reportList: ReportListItem[] = [
  {
    id: 1,
    title: "2026年第25周 竞品周报",
    type: "weekly",
    typeLabel: "周报",
    range: "6月19日 - 6月25日",
    competitors: 12,
    generatedAt: "2026-06-25",
    favorite: true,
    monthGroup: "2026年6月",
  },
  {
    id: 2,
    title: "2026年第24周 竞品周报",
    type: "weekly",
    typeLabel: "周报",
    range: "6月12日 - 6月18日",
    competitors: 12,
    generatedAt: "2026-06-18",
    favorite: false,
    monthGroup: "2026年6月",
  },
  {
    id: 3,
    title: "2026年6月 竞品月报",
    type: "monthly",
    typeLabel: "月报",
    range: "6月1日 - 6月30日",
    competitors: 12,
    generatedAt: "2026-06-01",
    favorite: false,
    monthGroup: "2026年6月",
  },
  {
    id: 4,
    title: "2026年第23周 竞品周报",
    type: "weekly",
    typeLabel: "周报",
    range: "5月29日 - 6月4日",
    competitors: 12,
    generatedAt: "2026-06-04",
    favorite: false,
    monthGroup: "2026年5月",
  },
  {
    id: 5,
    title: "2026年第22周 竞品周报",
    type: "weekly",
    typeLabel: "周报",
    range: "5月22日 - 5月28日",
    competitors: 12,
    generatedAt: "2026-05-28",
    favorite: false,
    monthGroup: "2026年5月",
  },
  {
    id: 6,
    title: "2026年第21周 竞品周报",
    type: "weekly",
    typeLabel: "周报",
    range: "5月15日 - 5月21日",
    competitors: 12,
    generatedAt: "2026-05-21",
    favorite: false,
    monthGroup: "2026年5月",
  },
];

// 第25周周报详情（完整数据）
const detail25: ReportDetail = {
  id: 1,
  title: "2026年第25周 竞品周报",
  typeLabel: "周报",
  rangeStart: "2026-06-19",
  rangeEnd: "2026-06-25",
  competitors: 12,
  favorite: true,
  summary:
    "本周共监控 12 个竞品，发现 28 个重要变化事件，涉及功能更新、价格调整、内容更新等多个方面。整体来看，协作办公类产品竞争加剧，AI 功能成为产品差异化的关键战场，部分产品开始调整定价策略以应对市场变化。",
  stats: [
    { key: "events", label: "重要变化事件", value: 28, delta: 27, deltaType: "up" },
    { key: "competitors", label: "涉及竞品", value: 8, delta: 14, deltaType: "up" },
    { key: "feature", label: "功能更新", value: 12, delta: 33, deltaType: "up" },
    { key: "price", label: "价格变化", value: 5, delta: 18, deltaType: "down" },
    { key: "impact", label: "高影响事件", value: 7, delta: 40, deltaType: "up" },
  ],
  highlights: [
    {
      id: 1,
      title: "Notion 推出全新 AI 功能套件",
      tag: "功能更新",
      tagType: "tag-feature",
      impact: "高影响",
      impactType: "high",
      points: [
        "Notion AI 新增“智能总结”、“自动翻译”、“任务拆解”等 5 项核心能力，显著提升内容处理效率。",
        "推出 AI Agent 功能，可自动执行跨页面任务流。",
        "可能影响：进一步巩固 Notion 在知识管理领域的领先地位，飞书文档等竞品需加速 AI 能力布局。",
      ],
      affected: ["飞书", "Microsoft Loop", "Confluence"],
      foundAt: "2026-06-20 10:24",
      aiConfidence: 92,
    },
    {
      id: 2,
      title: "飞书调整企业版定价策略",
      tag: "价格变化",
      tagType: "tag-price",
      impact: "中影响",
      impactType: "mid",
      points: [
        "飞书企业版基础版价格下调 15%，高级版新增安全合规模块并小幅提价。",
        "通过“基础版降价 + 高级版增值”的策略覆盖更多中小企业客户。",
      ],
      affected: ["钉钉", "企业微信", "腾讯文档"],
      foundAt: "2026-06-22 09:15",
      aiConfidence: 87,
    },
  ],
  categoryDist: [
    { name: "功能更新", value: 12 },
    { name: "价格变化", value: 5 },
    { name: "内容更新", value: 6 },
    { name: "舆论动态", value: 3 },
    { name: "其他", value: 2 },
  ],
  competitorRank: [
    { name: "Notion", value: 12 },
    { name: "飞书", value: 8 },
    { name: "钉钉", value: 6 },
    { name: "企业微信", value: 5 },
    { name: "Confluence", value: 4 },
  ],
  impactTrend: {
    dates: ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    current: [3, 5, 8, 6, 7, 4, 5],
    previous: [2, 4, 5, 7, 5, 3, 4],
  },
  relatedEvents: [
    {
      id: 1,
      brand: "Notion",
      title: "Notion AI 新增智能总结、自动翻译等 5 项核心能力",
      tag: "功能更新",
      tagType: "tag-feature",
      time: "2026-06-20 10:24",
    },
    {
      id: 2,
      brand: "Notion",
      title: "Notion 推出 AI Agent，支持跨页面任务流自动执行",
      tag: "功能更新",
      tagType: "tag-feature",
      time: "2026-06-20 10:26",
    },
    {
      id: 3,
      brand: "飞书",
      title: "飞书企业版基础版价格下调 15%",
      tag: "价格变化",
      tagType: "tag-price",
      time: "2026-06-22 09:15",
    },
    {
      id: 4,
      brand: "飞书",
      title: "飞书高级版新增安全合规模块",
      tag: "功能更新",
      tagType: "tag-feature",
      time: "2026-06-22 09:18",
    },
    {
      id: 5,
      brand: "钉钉",
      title: "钉钉文档上线 AI 会议纪要功能",
      tag: "内容更新",
      tagType: "tag-content",
      time: "2026-06-23 14:02",
    },
  ],
  relatedCompetitors: [
    { name: "Notion", iconText: "N", iconBg: "#ececec", iconColor: "#222222", changes: 12 },
    { name: "飞书", iconText: "飞", iconBg: "#e6f4ff", iconColor: "#1890ff", changes: 8 },
    { name: "钉钉", iconText: "钉", iconBg: "#e6eaff", iconColor: "#5b6fff", changes: 6 },
    { name: "企业微信", iconText: "企", iconBg: "#e6f9f0", iconColor: "#22c55e", changes: 5 },
    { name: "Confluence", iconText: "C", iconBg: "#fff3e6", iconColor: "#fa8c16", changes: 4 },
    { name: "Microsoft Loop", iconText: "M", iconBg: "#f5e8df", iconColor: "#c96442", changes: 3 },
    { name: "腾讯文档", iconText: "腾", iconBg: "#e6fffb", iconColor: "#13c2c2", changes: 2 },
    { name: "语雀", iconText: "语", iconBg: "#fff1f0", iconColor: "#ff4d4f", changes: 1 },
  ],
  aiSteps: [
    {
      title: "数据采集",
      desc: "从官网、公告、社交媒体等 23 个数据源抓取 12 个竞品的公开信息。",
      time: "2026-06-25 06:00",
    },
    {
      title: "事件识别",
      desc: "AI 模型从采集内容中识别出 28 个有效变化事件，并完成去重与分类。",
      time: "2026-06-25 06:12",
    },
    {
      title: "影响评估",
      desc: "结合历史数据对事件进行影响等级评估，标记 7 个高影响事件。",
      time: "2026-06-25 06:20",
    },
    {
      title: "报告生成",
      desc: "汇总核心摘要、重点变化与统计数据，生成本期竞品周报。",
      time: "2026-06-25 06:30",
    },
  ],
};

// 其他报告：基于列表项生成通用详情
function makeDetail(item: ReportListItem): ReportDetail {
  return {
    ...detail25,
    id: item.id,
    title: item.title,
    typeLabel: item.typeLabel,
    favorite: item.favorite,
    summary: `本期共监控 ${item.competitors} 个竞品，发现 24 个重要变化事件，涉及功能更新、价格调整、内容更新等多个方面。整体来看，AI 能力迭代仍是竞品竞争的主线。`,
    stats: [
      { key: "events", label: "重要变化事件", value: 24, delta: 12, deltaType: "up" },
      { key: "competitors", label: "涉及竞品", value: 7, delta: 8, deltaType: "up" },
      { key: "feature", label: "功能更新", value: 10, delta: 5, deltaType: "down" },
      { key: "price", label: "价格变化", value: 4, delta: 20, deltaType: "up" },
      { key: "impact", label: "高影响事件", value: 5, delta: 10, deltaType: "up" },
    ],
  };
}

export default [
  {
    url: "/api/reports/list",
    method: "get",
    timeout: 300,
    response: () => ({
      code: 0,
      data: { total: 18, reports: reportList },
    }),
  },
  {
    url: "/api/reports/detail",
    method: "get",
    timeout: 300,
    response: ({ query }: { query: Record<string, string> }) => {
      const id = Number(query.id);
      const item = reportList.find((r) => r.id === id) ?? reportList[0];
      return {
        code: 0,
        data: id === 1 ? detail25 : makeDetail(item),
      };
    },
  },
] as MockMethod[];
