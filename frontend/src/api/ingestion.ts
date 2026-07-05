import { apiClient } from "./client";

export type DatasetResponse = {
  id: string;
  tenant_id: string;
  warehouse_id?: string | null;
  uploaded_by_user_id?: string | null;
  filename: string;
  content_type?: string | null;
  file_format: string;
  storage_bucket: string;
  storage_key: string;
  size_bytes?: number | null;
  created_at: string;
};

export async function listDatasets(params?: { warehouse_id?: string }) {
  const { data } = await apiClient.get<DatasetResponse[]>("/ingestion/datasets", { params });
  return data;
}

export async function uploadDataset(file: File, warehouseId?: string) {
  const form = new FormData();
  form.append("file", file);
  if (warehouseId) {
    form.append("warehouse_id", warehouseId);
  }
  const { data } = await apiClient.post<DatasetResponse>("/ingestion/datasets", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
}

type MultipartUploadInitiateResponse = {
  upload_id: string;
  bucket: string;
  key: string;
  file_format: string;
  part_size_bytes: number;
  max_parts: number;
};

type MultipartUploadPresignPartResponse = {
  upload_id: string;
  key: string;
  part_number: number;
  url: string;
};

type MultipartUploadPart = {
  part_number: number;
  etag: string;
  size: number;
};

type MultipartResumeState = {
  upload_id: string;
  key: string;
  part_size_bytes: number;
  parts: MultipartUploadPart[];
};

export type MultipartUploadProgress = {
  loadedBytes: number;
  totalBytes: number;
  percent: number;
  partNumber?: number;
  totalParts: number;
};

const MULTIPART_RESUME_PREFIX = "wellvision:multipart:v1";

function buildMultipartResumeKey(file: File, warehouseId?: string) {
  const warehouseScope = warehouseId || "none";
  return `${MULTIPART_RESUME_PREFIX}:${warehouseScope}:${file.name}:${file.size}:${file.lastModified}`;
}

function loadMultipartResumeState(key: string): MultipartResumeState | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MultipartResumeState;
    if (!parsed?.upload_id || !parsed?.key || !parsed?.part_size_bytes) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function saveMultipartResumeState(key: string, state: MultipartResumeState) {
  try {
    window.localStorage.setItem(key, JSON.stringify(state));
  } catch {
    // Ignore cache failures; upload can continue without resume persistence.
  }
}

function clearMultipartResumeState(key: string) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Ignore cache cleanup failure.
  }
}

async function initiateMultipartUpload(file: File, warehouseId?: string) {
  const { data } = await apiClient.post<MultipartUploadInitiateResponse>("/ingestion/datasets/multipart/initiate", {
    filename: file.name,
    warehouse_id: warehouseId,
    content_type: file.type || undefined,
    size_bytes: file.size
  });
  return data;
}

async function presignMultipartPart(uploadId: string, key: string, partNumber: number) {
  const { data } = await apiClient.post<MultipartUploadPresignPartResponse>("/ingestion/datasets/multipart/presign-part", {
    upload_id: uploadId,
    key,
    part_number: partNumber
  });
  return data;
}

async function completeMultipartUpload(args: {
  uploadId: string;
  key: string;
  filename: string;
  contentType?: string;
  warehouseId?: string;
  parts: MultipartUploadPart[];
}) {
  const { data } = await apiClient.post<DatasetResponse>("/ingestion/datasets/multipart/complete", {
    upload_id: args.uploadId,
    key: args.key,
    filename: args.filename,
    content_type: args.contentType,
    warehouse_id: args.warehouseId,
    parts: args.parts.map((part) => ({
      part_number: part.part_number,
      etag: part.etag
    }))
  });
  return data;
}

async function abortMultipartUpload(uploadId: string, key: string) {
  await apiClient.post("/ingestion/datasets/multipart/abort", {
    upload_id: uploadId,
    key
  });
}

function extractEtagFromUploadResponse(xhr: XMLHttpRequest): string {
  const headerEtag = xhr.getResponseHeader("ETag") || xhr.getResponseHeader("etag");
  if (headerEtag) {
    return headerEtag.replace(/"/g, "").trim();
  }
  const responseText = xhr.responseText || "";
  const matched = responseText.match(/<ETag>"?([^"<]+)"?<\/ETag>/i);
  if (matched?.[1]) {
    return matched[1].replace(/"/g, "").trim();
  }
  throw new Error("Missing ETag from upload response. Please expose ETag in object storage CORS config.");
}

function uploadPartViaSignedUrl(
  url: string,
  chunk: Blob,
  onProgress?: (loadedChunkBytes: number) => void
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url, true);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(event.loaded);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(extractEtagFromUploadResponse(xhr));
        } catch (error) {
          reject(error);
        }
      } else {
        reject(new Error(`Part upload failed with status ${xhr.status}.`));
      }
    };
    xhr.onerror = () => reject(new Error("Part upload failed due to network error."));
    xhr.send(chunk);
  });
}

export async function uploadDatasetMultipart(
  file: File,
  options?: {
    warehouseId?: string;
    onProgress?: (progress: MultipartUploadProgress) => void;
    fallbackToDirect?: boolean;
  }
) {
  const warehouseId = options?.warehouseId;
  const resumeKey = buildMultipartResumeKey(file, warehouseId);
  let resumed = true;

  let state = loadMultipartResumeState(resumeKey);
  if (!state) {
    resumed = false;
    const init = await initiateMultipartUpload(file, warehouseId);
    state = {
      upload_id: init.upload_id,
      key: init.key,
      part_size_bytes: init.part_size_bytes,
      parts: []
    };
    saveMultipartResumeState(resumeKey, state);
  }

  const partSizeBytes = Math.max(5 * 1024 * 1024, state.part_size_bytes);
  const totalParts = Math.max(1, Math.ceil(file.size / partSizeBytes));
  if (totalParts > 10000) {
    throw new Error("File too large: part count exceeds 10,000. Increase multipart part size.");
  }

  const uploadedPartMap = new Map<number, MultipartUploadPart>();
  for (const part of state.parts) {
    uploadedPartMap.set(part.part_number, part);
  }
  let uploadedBytes = 0;
  for (const part of uploadedPartMap.values()) {
    uploadedBytes += part.size;
  }
  options?.onProgress?.({
    loadedBytes: uploadedBytes,
    totalBytes: file.size,
    percent: file.size ? Number(((uploadedBytes / file.size) * 100).toFixed(2)) : 0,
    totalParts
  });

  try {
    for (let partNumber = 1; partNumber <= totalParts; partNumber += 1) {
      if (uploadedPartMap.has(partNumber)) continue;

      const partStart = (partNumber - 1) * partSizeBytes;
      const partEnd = Math.min(file.size, partStart + partSizeBytes);
      const chunk = file.slice(partStart, partEnd);
      const signedPart = await presignMultipartPart(state.upload_id, state.key, partNumber);

      const partUploadedBase = uploadedBytes;
      const etag = await uploadPartViaSignedUrl(signedPart.url, chunk, (loadedChunkBytes) => {
        const loaded = Math.min(file.size, partUploadedBase + loadedChunkBytes);
        options?.onProgress?.({
          loadedBytes: loaded,
          totalBytes: file.size,
          percent: file.size ? Number(((loaded / file.size) * 100).toFixed(2)) : 0,
          partNumber,
          totalParts
        });
      });

      const savedPart: MultipartUploadPart = {
        part_number: partNumber,
        etag,
        size: chunk.size
      };
      uploadedPartMap.set(partNumber, savedPart);
      state.parts = Array.from(uploadedPartMap.values()).sort((a, b) => a.part_number - b.part_number);
      saveMultipartResumeState(resumeKey, state);

      uploadedBytes += chunk.size;
      options?.onProgress?.({
        loadedBytes: uploadedBytes,
        totalBytes: file.size,
        percent: file.size ? Number(((uploadedBytes / file.size) * 100).toFixed(2)) : 0,
        partNumber,
        totalParts
      });
    }

    const completed = await completeMultipartUpload({
      uploadId: state.upload_id,
      key: state.key,
      filename: file.name,
      contentType: file.type || undefined,
      warehouseId,
      parts: Array.from(uploadedPartMap.values()).sort((a, b) => a.part_number - b.part_number)
    });
    clearMultipartResumeState(resumeKey);
    return completed;
  } catch (error) {
    if (!resumed && uploadedBytes === 0 && options?.fallbackToDirect) {
      try {
        await abortMultipartUpload(state.upload_id, state.key);
      } catch {
        // Ignore abort failure and still fallback.
      }
      clearMultipartResumeState(resumeKey);
      return uploadDataset(file, warehouseId);
    }
    throw error;
  }
}

export type DatasetPreviewResponse = {
  dataset_id: string;
  file_format: string;
  columns: string[];
  rows: Record<string, unknown>[];
  truncated: boolean;
  message?: string | null;
};

export async function previewDataset(datasetId: string, limit = 20) {
  const { data } = await apiClient.get<DatasetPreviewResponse>(`/ingestion/datasets/${datasetId}/preview`, {
    params: { limit }
  });
  return data;
}

export type ImportJob = {
  id: string;
  tenant_id: string;
  dataset_id: string;
  warehouse_id?: string | null;
  created_by_user_id?: string | null;
  status: string;
  error_message?: string | null;
  total_rows?: number | null;
  processed_rows: number;
  has_header: boolean;
  delimiter?: string | null;
  source_label?: string | null;
  import_mode?: string | null;
  time_column?: string | null;
  start_time?: string | null;
  sample_rate_seconds?: number | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export async function listImportJobs(params?: { dataset_id?: string; warehouse_id?: string }) {
  const { data } = await apiClient.get<ImportJob[]>("/ingestion/import-jobs", { params });
  return data;
}

export async function createImportJob(payload: {
  dataset_id: string;
  warehouse_id?: string | null;
  has_header?: boolean;
  delimiter?: string | null;
  time_column?: string | null;
  start_time?: string | null;
  sample_rate_seconds?: number | null;
}) {
  const { data } = await apiClient.post<ImportJob>("/ingestion/import-jobs", payload);
  return data;
}

export async function updateImportJob(jobId: string, payload: Partial<Omit<ImportJob, "id" | "tenant_id">>) {
  const { data } = await apiClient.patch<ImportJob>(`/ingestion/import-jobs/${jobId}`, payload);
  return data;
}

export async function startImportJob(jobId: string) {
  const { data } = await apiClient.post<ImportJob>(`/ingestion/import-jobs/${jobId}/start`);
  return data;
}

export async function pauseImportJob(jobId: string) {
  const { data } = await apiClient.post<ImportJob>(`/ingestion/import-jobs/${jobId}/pause`);
  return data;
}

export async function cancelImportJob(jobId: string) {
  const { data } = await apiClient.post<ImportJob>(`/ingestion/import-jobs/${jobId}/cancel`);
  return data;
}
