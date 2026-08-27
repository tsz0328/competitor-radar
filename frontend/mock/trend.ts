import { MockMethod } from "vite-plugin-mock";
import type { TrendPoint } from "@/types/trend";

// 模拟后端：生成 90 天趋势（后端就绪后整个文件可删）
function buildTrend(): TrendPoint[] {
  return Array.from({ length: 90 }, (_, i) => {
    const d = new Date(2026, 4, 19 + i);
    return {
      date: `${d.getMonth() + 1}/${d.getDate()}`,
      feature: Math.round(10 + i * 0.3 + Math.sin(i / 5) * 8),
      price: Math.round(8 + i * 0.2 + Math.cos(i / 4) * 6),
      sentiment: Math.round(Math.abs(Math.sin(i / 3)) * 20),
    };
  });
}

// 模拟后端缓存：只生成一次
const ALL_TREND = buildTrend();

interface MockContext {
  query: Record<string, string | number>;
}

export default [
  {
    url: "/api/trend",
    method: "get",
    timeout: 300,
    // query.days 对应 ?days=7|30|90
    response: ({ query }: MockContext) => {
      const days = Number(query.days) || 7;
      return { code: 0, data: ALL_TREND.slice(-days) };
    },
  },
] as MockMethod[];
