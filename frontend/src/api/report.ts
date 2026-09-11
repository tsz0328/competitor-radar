import request from "@/api/request";
import type { ReportDetail, ReportListResult } from "@/types/report";

export function fetchReportList(): Promise<ReportListResult> {
  return request.get<unknown, ReportListResult>("/api/reports/list");
}

export function fetchReportDetail(id: number): Promise<ReportDetail> {
  return request.get<unknown, ReportDetail>("/api/reports/detail", {
    params: { id },
  });
}
