import request from "@/api/request";
import type { TrendPoint } from "@/types/trend";

export function fetchTrend(days: 7 | 30 | 90): Promise<TrendPoint[]> {
  return request.get<unknown, TrendPoint[]>("/api/trend", { params: { days } });
}
