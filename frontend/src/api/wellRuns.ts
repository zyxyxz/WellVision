import { apiClient } from "./client";

export type WellRunResponse = {
  id: string;
  tenant_id: string;
  warehouse_id?: string | null;
  name: string;
  well_name?: string | null;
  section?: string | null;
  status: string;
  started_at?: string | null;
  ended_at?: string | null;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WellRunChannelSummary = {
  source: string;
  channel: string;
  count: number;
  ts_start?: string | null;
  ts_end?: string | null;
  md_start?: number | null;
  md_end?: number | null;
};

export type WellRunAxisMapPoint = {
  ts: string;
  md: number;
};

export type WellRunAxisMapResponse = {
  well_run_id: string;
  source?: string | null;
  channel?: string | null;
  count: number;
  ts_start?: string | null;
  ts_end?: string | null;
  md_start?: number | null;
  md_end?: number | null;
  rows: WellRunAxisMapPoint[];
};

export type WellRunSegmentResponse = {
  id: string;
  tenant_id: string;
  warehouse_id?: string | null;
  well_run_id: string;
  segment_type: string;
  source: string;
  confidence?: number | null;
  start_ts?: string | null;
  end_ts?: string | null;
  md_start?: number | null;
  md_end?: number | null;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AlignChannelRequest = {
  channel: string;
  source?: string | null;
  alias?: string | null;
  native_axis?: "auto" | "time" | "depth";
  method?: "nearest" | "linear";
  max_gap_seconds?: number | null;
  max_gap_meters?: number | null;
};

export type WellRunAxisMapConfig = {
  enabled?: boolean;
  source?: string | null;
  channel?: string | null;
  max_gap_seconds?: number;
  max_gap_meters?: number;
  map_limit?: number;
};

export type WellRunAlignRequest = {
  axis?: "time" | "depth";
  channels: AlignChannelRequest[];
  grid_mode?: "fixed" | "anchor";
  anchor_alias?: string | null;
  segment_ids?: string[];
  segment_types?: string[];
  start?: string;
  end?: string;
  md_start?: number;
  md_end?: number;
  step_seconds?: number;
  step_meters?: number;
  max_rows?: number;
  axis_map?: WellRunAxisMapConfig;
};

export type WellRunAlignedValue = {
  value?: number | null;
  quality_code: number;
  source?: string | null;
};

export type WellRunAlignedRow = {
  ts?: string | null;
  md?: number | null;
  values: Record<string, WellRunAlignedValue>;
};

export type WellRunAlignResponse = {
  well_run_id: string;
  axis: "time" | "depth";
  step_seconds?: number | null;
  step_meters?: number | null;
  rows: WellRunAlignedRow[];
  stats: Record<string, unknown>;
};

export async function listWellRuns(params?: {
  warehouse_id?: string;
  status?: string;
  limit?: number;
}) {
  const { data } = await apiClient.get<WellRunResponse[]>("/well-runs", { params });
  return data;
}

export async function listWellRunChannels(wellRunId: string, limit = 500) {
  const { data } = await apiClient.get<WellRunChannelSummary[]>(`/well-runs/${wellRunId}/channels`, {
    params: { limit }
  });
  return data;
}

export async function listWellRunAxisMap(
  wellRunId: string,
  params?: {
    source?: string;
    channel?: string;
    limit?: number;
  }
) {
  const { data } = await apiClient.get<WellRunAxisMapResponse>(`/well-runs/${wellRunId}/axis-map`, { params });
  return data;
}

export async function listWellRunSegments(
  wellRunId: string,
  params?: {
    segment_type?: string;
    source?: string;
    limit?: number;
  }
) {
  const { data } = await apiClient.get<WellRunSegmentResponse[]>(`/well-runs/${wellRunId}/segments`, { params });
  return data;
}

export async function alignWellRun(wellRunId: string, payload: WellRunAlignRequest) {
  const { data } = await apiClient.post<WellRunAlignResponse>(`/well-runs/${wellRunId}/align`, payload);
  return data;
}
