import { apiClient } from "./client";

export type DataWarehouseResponse = {
  id: string;
  tenant_id: string;
  project_id?: string | null;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
};

export type DataSourceResponse = {
  id: string;
  tenant_id: string;
  warehouse_id: string;
  name: string;
  source_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

export type DataSourceCreate = {
  name?: string;
  source_type: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
};

export type DataSourceUpdate = {
  name?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
};

export type DataWarehouseCreate = {
  name: string;
  description?: string;
  project_id?: string | null;
  sources?: DataSourceCreate[];
};

export async function listWarehouses() {
  const { data } = await apiClient.get<DataWarehouseResponse[]>("/warehouses");
  return data;
}

export async function createWarehouse(payload: DataWarehouseCreate) {
  const { data } = await apiClient.post<DataWarehouseResponse>("/warehouses", payload);
  return data;
}

export async function updateWarehouse(warehouseId: string, payload: DataWarehouseCreate | Partial<DataWarehouseCreate>) {
  const { data } = await apiClient.patch<DataWarehouseResponse>(`/warehouses/${warehouseId}`, payload);
  return data;
}

export async function listWarehouseSources(warehouseId: string) {
  const { data } = await apiClient.get<DataSourceResponse[]>(`/warehouses/${warehouseId}/sources`);
  return data;
}

export async function createWarehouseSource(warehouseId: string, payload: DataSourceCreate) {
  const { data } = await apiClient.post<DataSourceResponse>(`/warehouses/${warehouseId}/sources`, payload);
  return data;
}

export async function updateWarehouseSource(
  warehouseId: string,
  sourceId: string,
  payload: DataSourceUpdate
) {
  const { data } = await apiClient.patch<DataSourceResponse>(
    `/warehouses/${warehouseId}/sources/${sourceId}`,
    payload
  );
  return data;
}
