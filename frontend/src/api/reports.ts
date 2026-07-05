import { apiClient } from "./client";

export type ReportStatus = "draft" | "in_review" | "published" | "rejected";

export type ReportResponse = {
  id: string;
  tenant_id: string;
  created_by_user_id: string;
  reviewed_by_user_id?: string | null;
  title: string;
  content_markdown: string;
  summary_json?: Record<string, unknown>;
  status: ReportStatus;
  review_comment?: string | null;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
};

export async function listReports(status?: ReportStatus) {
  const { data } = await apiClient.get<ReportResponse[]>("/reports", {
    params: status ? { status } : undefined
  });
  return data;
}

export async function createReport(input: { title: string; content_markdown: string }) {
  const { data } = await apiClient.post<ReportResponse>("/reports", input);
  return data;
}

export async function createReportFromRun(input: { run_id: string; title?: string; notes?: string }) {
  const { data } = await apiClient.post<ReportResponse>("/reports/from-analysis-run", input);
  return data;
}

export async function updateReport(reportId: string, input: { title: string; content_markdown: string }) {
  const { data } = await apiClient.patch<ReportResponse>(`/reports/${reportId}`, input);
  return data;
}

export async function submitReport(reportId: string) {
  const { data } = await apiClient.post<ReportResponse>(`/reports/${reportId}/submit`);
  return data;
}

export async function approveReport(reportId: string, comment?: string) {
  const { data } = await apiClient.post<ReportResponse>(`/reports/${reportId}/approve`, { comment });
  return data;
}

export async function rejectReport(reportId: string, comment?: string) {
  const { data } = await apiClient.post<ReportResponse>(`/reports/${reportId}/reject`, { comment });
  return data;
}
