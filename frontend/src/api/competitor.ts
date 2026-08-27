import request from "@/api/request";
import type { CompetitorItem } from "@/types/competitor";

export function fetchCompetitors(): Promise<CompetitorItem[]> {
  return request.get<unknown, CompetitorItem[]>("/api/competitors/CompetitorList");
}
