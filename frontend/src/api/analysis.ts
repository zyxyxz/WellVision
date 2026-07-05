import { apiClient } from "./client";

export type SeriesQuery = {
  field: string;
  start?: string;
  end?: string;
  limit?: number;
  bucket_minutes?: number;
  warehouse_id?: string | null;
};

export type SeriesPoint = {
  ts: string;
  value: number;
};

export type SeriesResponse = {
  field: string;
  points: SeriesPoint[];
  stats: Record<string, number>;
};

export type AlgorithmInfo = {
  id: string;
  name: string;
  description: string;
  params: AlgorithmParam[];
  kind?: string;
};

export type AlgorithmParam = {
  key: string;
  label: string;
  type: "number" | "field" | "text" | "boolean";
  default: number | string | boolean;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  description?: string | null;
};

export type FieldSummary = {
  name: string;
  count: number;
};

export type AlgorithmRunResponse = {
  algorithm_id: string;
  run_id?: string | null;
  result_series: SeriesPoint[];
  result_points?: { x: number; y: number }[];
  x_axis?: string | null;
  metrics: Record<string, number | string>;
};

export type AnalysisRunResponse = {
  id: string;
  algorithm_id: string;
  field: string;
  warehouse_id?: string | null;
  params: Record<string, unknown>;
  base_stats: Record<string, unknown>;
  metrics: Record<string, unknown>;
  created_at: string;
};

export type ReportTemplate = {
  id: string;
  tenant_id: string;
  created_by_user_id?: string | null;
  name: string;
  description?: string | null;
  prompt_template: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type ReportTemplateCreate = {
  name: string;
  description?: string;
  prompt_template: string;
  enabled?: boolean;
};

export type AIChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type AIChatSession = {
  id: string;
  tenant_id: string;
  user_id?: string | null;
  warehouse_id?: string | null;
  title?: string | null;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export async function listAlgorithms() {
  const { data } = await apiClient.get<AlgorithmInfo[]>("/analysis/algorithms");
  return data;
}

export async function listReportTemplates() {
  const { data } = await apiClient.get<ReportTemplate[]>("/analysis/report-templates");
  return data;
}

export async function createReportTemplate(payload: ReportTemplateCreate) {
  const { data } = await apiClient.post<ReportTemplate>("/analysis/report-templates", payload);
  return data;
}

export async function listFields(limit = 1500, warehouseId?: string | null) {
  const params: Record<string, unknown> = { limit };
  if (warehouseId) params.warehouse_id = warehouseId;
  const { data } = await apiClient.get<FieldSummary[]>("/analysis/fields", { params });
  return data;
}

export async function loadSeries(query: SeriesQuery) {
  const { data } = await apiClient.post<SeriesResponse>("/analysis/series", query);
  return data;
}

export async function listAnalysisRuns(params?: {
  algorithm_id?: string;
  field?: string;
  limit?: number;
  warehouse_id?: string;
}) {
  const { data } = await apiClient.get<AnalysisRunResponse[]>("/analysis/runs", { params });
  return data;
}

export async function compareSeries(left: SeriesQuery, right: SeriesQuery) {
  const { data } = await apiClient.post("/analysis/compare", { left, right });
  return data as { field: string; left: SeriesResponse; right: SeriesResponse };
}

export async function runAlgorithm(input: {
  algorithm_id: AlgorithmInfo["id"];
  series: SeriesQuery;
  params?: Record<string, unknown>;
}) {
  const { data } = await apiClient.post<AlgorithmRunResponse>("/analysis/run", input);
  return data;
}

export async function generateAIReport(input: {
  title: string;
  series: SeriesQuery;
  algorithm_result?: AlgorithmRunResponse | null;
  notes?: string;
  save_as_report?: boolean;
  report_title?: string;
  template_id?: string | null;
}) {
  const { data } = await apiClient.post<{ model: string; report_markdown: string; report_id?: string | null }>(
    "/analysis/ai-report",
    input
  );
  return data;
}

export async function listChatSessions() {
  const { data } = await apiClient.get<AIChatSession[]>("/analysis/chat/sessions");
  return data;
}

export async function listChatMessages(sessionId: string) {
  const { data } = await apiClient.get<AIChatMessage[]>(`/analysis/chat/sessions/${sessionId}/messages`);
  return data;
}

export async function sendChatMessage(input: {
  session_id?: string | null;
  title?: string;
  message: string;
  context?: Record<string, unknown>;
}) {
  const { data } = await apiClient.post<{
    session_id: string;
    model: string;
    reply: string;
    message_id: string;
  }>("/analysis/chat", input);
  return data;
}

export type AIChatStreamFinal = {
  session_id: string;
  model: string;
  reply: string;
  message_id: string;
};

export async function sendChatMessageStream(
  input: {
    session_id?: string | null;
    title?: string;
    message: string;
    context?: Record<string, unknown>;
  },
  handlers: {
    onDelta: (delta: string) => void;
    onFinal: (final: AIChatStreamFinal) => void;
    onError: (message: string) => void;
  },
  options?: { signal?: AbortSignal }
) {
  const token = localStorage.getItem("wellvision_token");
  const baseURL = import.meta.env.VITE_API_BASE_URL ?? "/api";
  const url = baseURL.startsWith("http") ? `${baseURL}/analysis/chat/stream` : `${baseURL}/analysis/chat/stream`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(input),
    signal: options?.signal
  });
  if (!resp.ok) {
    let detail = "AI chat failed";
    try {
      const data = await resp.json();
      detail = data?.detail || detail;
    } catch {
      detail = await resp.text();
    }
    handlers.onError(detail || "AI chat failed");
    return;
  }
  if (!resp.body) {
    handlers.onError("Empty response stream");
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n").filter((line) => line.startsWith("data:"));
      for (const line of lines) {
        const data = line.replace(/^data:\s*/, "").trim();
        if (!data) continue;
        if (data === "[DONE]") return;
        try {
          const payload = JSON.parse(data) as { type: string; delta?: string; message?: string };
          if (payload.type === "delta" && payload.delta) {
            handlers.onDelta(payload.delta);
          } else if (payload.type === "final") {
            handlers.onFinal(payload as unknown as AIChatStreamFinal);
          } else if (payload.type === "done") {
            return;
          } else if (payload.type === "error") {
            handlers.onError(payload.message || "AI chat failed");
            return;
          }
        } catch (err) {
          handlers.onError(String(err));
          return;
        }
      }
    }
  }
}
