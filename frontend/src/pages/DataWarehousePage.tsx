import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tabs,
  Typography,
  Upload,
  message
} from "antd";
import type { UploadProps } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { listFields, type FieldSummary } from "../api/analysis";
import {
  listDatasets,
  listImportJobs,
  previewDataset,
  type DatasetPreviewResponse,
  type DatasetResponse,
  type ImportJob,
  createImportJob,
  updateImportJob,
  startImportJob,
  pauseImportJob,
  cancelImportJob,
  uploadDatasetMultipart
} from "../api/ingestion";
import { ingestEvent, listEvents, type EventResponse } from "../api/events";
import {
  createWarehouseSource,
  listWarehouseSources,
  listWarehouses,
  updateWarehouseSource,
  type DataSourceResponse,
  type DataWarehouseResponse
} from "../api/warehouses";
import { useAuth } from "../auth/AuthProvider";

const SOURCE_TYPE_OPTIONS = [
  { label: "FILE", value: "file_upload" },
  { label: "HTTP", value: "http_stream" },
  { label: "MQTT", value: "mqtt" }
];

type SourceFormValues = {
  source_type: string;
  name?: string;
  stream_source?: string;
  stream_topic?: string;
  mqtt_broker?: string;
  enabled?: boolean;
};

type SourceEditFormValues = {
  name?: string;
  enabled?: boolean;
  config?: string;
};

type EventFilterForm = {
  source?: string;
  topic?: string;
  limit: number;
};

type StreamingIngestForm = {
  source: string;
  topic?: string;
  payload: string;
};

function formatBytes(value?: number | null) {
  if (!value) return "-";
  const mb = value / (1024 * 1024);
  if (mb < 1) return `${(value / 1024).toFixed(1)} KB`;
  return `${mb.toFixed(2)} MB`;
}

export function DataWarehousePage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const { warehouseId } = useParams<{ warehouseId: string }>();
  const navigate = useNavigate();
  const tenantReady = Boolean(me?.tenant_id);

  const [warehouse, setWarehouse] = useState<DataWarehouseResponse | null>(null);
  const [loadingWarehouse, setLoadingWarehouse] = useState(false);

  const [sources, setSources] = useState<DataSourceResponse[]>([]);
  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [events, setEvents] = useState<EventResponse[]>([]);
  const [fields, setFields] = useState<FieldSummary[]>([]);
  const [importJobs, setImportJobs] = useState<ImportJob[]>([]);

  const [loadingSources, setLoadingSources] = useState(false);
  const [loadingDatasets, setLoadingDatasets] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [loadingImports, setLoadingImports] = useState(false);
  const [creatingSource, setCreatingSource] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [ingesting, setIngesting] = useState(false);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<DatasetPreviewResponse | null>(null);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importingDataset, setImportingDataset] = useState<DatasetResponse | null>(null);
  const [editingImportJob, setEditingImportJob] = useState<ImportJob | null>(null);
  const [importSaving, setImportSaving] = useState(false);

  const [editSourceOpen, setEditSourceOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<DataSourceResponse | null>(null);
  const [savingSource, setSavingSource] = useState(false);

  const [sourceForm] = Form.useForm<SourceFormValues>();
  const [sourceEditForm] = Form.useForm<SourceEditFormValues>();
  const [streamingForm] = Form.useForm<StreamingIngestForm>();
  const [eventFilterForm] = Form.useForm<EventFilterForm>();
  const [importForm] = Form.useForm();

  const sourceLabels = useMemo(
    () => ({
      file_upload: t("data.sourceFile"),
      http_stream: t("data.sourceHttp"),
      mqtt: t("data.sourceMqtt"),
      custom: t("data.sourceCustom")
    }),
    [t]
  );

  async function loadWarehouse() {
    if (!tenantReady || !warehouseId) return;
    setLoadingWarehouse(true);
    try {
      const data = await listWarehouses();
      const found = data.find((item) => item.id === warehouseId) ?? null;
      setWarehouse(found);
    } catch (err) {
      message.error(t("data.warehouseLoadFail"));
    } finally {
      setLoadingWarehouse(false);
    }
  }

  async function loadSources() {
    if (!warehouseId) return;
    setLoadingSources(true);
    try {
      const data = await listWarehouseSources(warehouseId);
      setSources(data);
    } catch (err) {
      message.error(t("data.sourceLoadFail"));
    } finally {
      setLoadingSources(false);
    }
  }

  async function loadDatasets() {
    if (!warehouseId) return;
    setLoadingDatasets(true);
    try {
      const data = await listDatasets({ warehouse_id: warehouseId });
      setDatasets(data);
    } catch (err) {
      message.error(t("data.datasetsLoadFail"));
    } finally {
      setLoadingDatasets(false);
    }
  }

  async function loadEvents(filters?: Partial<EventFilterForm>) {
    if (!warehouseId) return;
    setLoadingEvents(true);
    try {
      const values = eventFilterForm.getFieldsValue() as Partial<EventFilterForm>;
      const merged = {
        ...values,
        ...filters,
        limit: filters?.limit ?? values.limit ?? 800
      };
      const data = await listEvents({
        warehouse_id: warehouseId,
        source: merged.source,
        topic: merged.topic,
        limit: merged.limit
      });
      setEvents(data);
    } catch (err) {
      message.error(t("data.eventsLoadFail"));
    } finally {
      setLoadingEvents(false);
    }
  }

  async function loadFields() {
    if (!warehouseId) return;
    setLoadingFields(true);
    try {
      const data = await listFields(1200, warehouseId);
      setFields(data.slice(0, 24));
    } catch (err) {
      message.error(t("data.fieldsLoadFail"));
    } finally {
      setLoadingFields(false);
    }
  }

  async function loadImportJobs() {
    if (!warehouseId) return;
    setLoadingImports(true);
    try {
      const data = await listImportJobs({ warehouse_id: warehouseId });
      setImportJobs(data);
    } catch (err) {
      message.error(t("data.importLoadFail"));
    } finally {
      setLoadingImports(false);
    }
  }

  async function refreshAll() {
    await Promise.all([loadWarehouse(), loadSources(), loadDatasets(), loadEvents(), loadFields(), loadImportJobs()]);
  }

  useEffect(() => {
    if (!tenantReady) return;
    void refreshAll();
  }, [tenantReady, warehouseId]);

  useEffect(() => {
    if (!tenantReady || !warehouse) return;
    eventFilterForm.setFieldsValue({ limit: 800 });
    streamingForm.setFieldsValue({ source: "http" });
  }, [tenantReady, warehouse, eventFilterForm, streamingForm]);

  const uploadProps: UploadProps = {
    accept: ".csv,.parquet",
    maxCount: 1,
    showUploadList: false,
    customRequest: async (options) => {
      const file = options.file as File;
      if (!warehouseId) return;
      setUploading(true);
      setUploadProgress(0);
      try {
        await uploadDatasetMultipart(file, {
          warehouseId,
          fallbackToDirect: true,
          onProgress: (progress) => {
            setUploadProgress(progress.percent);
            options.onProgress?.({ percent: progress.percent }, file);
          }
        });
        message.success(t("data.uploadSuccess"));
        options.onSuccess?.({}, file);
        await loadDatasets();
        await loadImportJobs();
      } catch (error: any) {
        const detail = error?.message || error?.response?.data?.detail;
        if (detail) {
          message.error(`${t("data.uploadFail")}：${detail}`);
        } else {
          message.error(t("data.uploadFail"));
        }
        options.onError?.(error as Error);
      } finally {
        setUploading(false);
        setUploadProgress(null);
      }
    }
  };

  const handleStreamingIngest = async () => {
    const values = await streamingForm.validateFields();
    if (!warehouseId) return;
    setIngesting(true);
    try {
      const payload = JSON.parse(values.payload);
      await ingestEvent({
        source: values.source,
        topic: values.topic,
        payload,
        warehouse_id: warehouseId
      });
      message.success(t("data.streamingSuccess"));
      streamingForm.setFieldsValue({ payload: "", topic: values.topic });
      await loadEvents();
      await loadFields();
    } catch (err) {
      message.error(t("data.streamingFail"));
    } finally {
      setIngesting(false);
    }
  };

  const openImportModal = (dataset: DatasetResponse, job?: ImportJob) => {
    setImportingDataset(dataset);
    setEditingImportJob(job || null);
    setImportModalOpen(true);
    importForm.resetFields();
    importForm.setFieldsValue({
      has_header: true,
      delimiter: ",",
      ...(job
        ? {
            has_header: job.has_header,
            delimiter: job.delimiter || ",",
            time_column: job.time_column,
            start_time: job.start_time,
            sample_rate_seconds: job.sample_rate_seconds
          }
        : {})
    });
  };

  const submitImportJob = async () => {
    if (!importingDataset) return;
    const values = await importForm.validateFields();
    setImportSaving(true);
    try {
      const startTimeVal = values.start_time;
      let startTime: string | undefined = undefined;
      if (startTimeVal) {
        if (typeof startTimeVal === "string") {
          startTime = startTimeVal;
        } else if (typeof startTimeVal.toISOString === "function") {
          startTime = startTimeVal.toISOString();
        }
      }
      let job: ImportJob | null = null;
      if (editingImportJob) {
        job = await updateImportJob(editingImportJob.id, {
          has_header: values.has_header,
          delimiter: values.delimiter || undefined,
          time_column: values.time_column || undefined,
          start_time: startTime,
          sample_rate_seconds: values.sample_rate_seconds || undefined
        });
      } else {
        job = await createImportJob({
          dataset_id: importingDataset.id,
          warehouse_id: warehouseId,
          has_header: values.has_header,
          delimiter: values.delimiter || undefined,
          time_column: values.time_column || undefined,
          start_time: startTime,
          sample_rate_seconds: values.sample_rate_seconds || undefined
        });
      }
      message.success(t("data.importCreated"));
      setImportModalOpen(false);
      setImportingDataset(null);
      setEditingImportJob(null);
      await loadImportJobs();
      if (job?.status === "pending") {
        await startImportJob(job.id);
        await loadImportJobs();
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("data.importCreateFail"));
    } finally {
      setImportSaving(false);
    }
  };

  const handleImportAction = async (job: ImportJob, action: "start" | "pause" | "cancel") => {
    try {
      if (action === "start") await startImportJob(job.id);
      if (action === "pause") await pauseImportJob(job.id);
      if (action === "cancel") await cancelImportJob(job.id);
      await loadImportJobs();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("data.importActionFail"));
    }
  };

  const handleAddSource = async () => {
    if (!warehouseId) return;
    const values = await sourceForm.validateFields();
    setCreatingSource(true);
    try {
      let config: Record<string, unknown> = {};
      if (values.source_type === "http_stream") {
        config = { source: values.stream_source || "http", topic: values.stream_topic || null };
      }
      if (values.source_type === "mqtt") {
        config = { broker_url: values.mqtt_broker || null, topic: values.stream_topic || null };
      }
      await createWarehouseSource(warehouseId, {
        source_type: values.source_type,
        name: values.name,
        config,
        enabled: values.enabled ?? true
      });
      message.success(t("data.sourceCreateSuccess"));
      sourceForm.resetFields();
      await loadSources();
    } catch (err) {
      message.error(t("data.sourceCreateFail"));
    } finally {
      setCreatingSource(false);
    }
  };

  const handleToggleSource = async (source: DataSourceResponse, enabled: boolean) => {
    if (!warehouseId) return;
    try {
      await updateWarehouseSource(warehouseId, source.id, { enabled });
      message.success(t("data.sourceUpdateSuccess"));
      await loadSources();
    } catch (err) {
      message.error(t("data.sourceUpdateFail"));
    }
  };

  const openEditSource = (source: DataSourceResponse) => {
    setEditingSource(source);
    sourceEditForm.setFieldsValue({
      name: source.name,
      enabled: source.enabled,
      config: JSON.stringify(source.config ?? {}, null, 2)
    });
    setEditSourceOpen(true);
  };

  const handleSaveSource = async () => {
    if (!warehouseId || !editingSource) return;
    const values = await sourceEditForm.validateFields();
    setSavingSource(true);
    try {
      const configText = values.config?.trim() || "{}";
      const config = JSON.parse(configText);
      await updateWarehouseSource(warehouseId, editingSource.id, {
        name: values.name,
        enabled: values.enabled,
        config
      });
      message.success(t("data.sourceUpdateSuccess"));
      setEditSourceOpen(false);
      await loadSources();
    } catch (err) {
      message.error(t("data.sourceUpdateFail"));
    } finally {
      setSavingSource(false);
    }
  };

  const handlePreview = async (datasetId: string) => {
    setPreviewOpen(true);
    setPreviewLoading(true);
    try {
      const data = await previewDataset(datasetId, 20);
      setPreviewData(data);
    } catch (err) {
      message.error(t("data.previewLoadFail"));
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  if (!tenantReady) {
    return (
      <Alert type="warning" showIcon message={t("data.noTenant")} description={t("data.noTenantDesc")} />
    );
  }

  if (!warehouseId) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("data.warehouseSelectTip")}
        description={t("data.warehouseEmpty")}
      />
    );
  }

  if (!loadingWarehouse && !warehouse) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("data.warehouseNotFound")}
        description={t("data.warehouseNotFoundDesc")}
        action={
          <Button type="primary" onClick={() => navigate("/data")}
          >
            {t("data.backToList")}
          </Button>
        }
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space wrap align="center" style={{ width: "100%", justifyContent: "space-between" }}>
        <Space>
          <Button onClick={() => navigate("/data")}>{t("data.backToList")}</Button>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {warehouse?.name || t("data.warehouseDetailTitle")}
          </Typography.Title>
        </Space>
        {warehouse ? <Tag color="blue">{warehouse.name}</Tag> : null}
      </Space>

      <Card loading={loadingWarehouse}>
        {warehouse ? (
          <Space direction="vertical" size={8}>
            <Typography.Text strong>{warehouse.name}</Typography.Text>
            <Typography.Text type="secondary">{warehouse.description || "-"}</Typography.Text>
            <Typography.Text type="secondary">
              {t("data.created")}: {new Date(warehouse.created_at).toLocaleString()}
            </Typography.Text>
          </Space>
        ) : (
          <Empty description={t("data.warehouseLoading")} />
        )}
      </Card>

      <Tabs
        items={[
          {
            key: "fields",
            label: t("data.fieldsTab"),
            children: (
              <Card title={t("data.fieldsTitle")} loading={loadingFields}>
                {fields.length ? (
                  <Space wrap>
                    {fields.map((f) => (
                      <Tag key={f.name} color="blue">
                        {f.name} · {f.count}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <Typography.Text type="secondary">{t("data.noFields")}</Typography.Text>
                )}
              </Card>
            )
          },
          {
            key: "datasets",
            label: t("data.datasetsTab"),
            children: (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                  {t("data.uploadHint")}
                </Typography.Paragraph>
                <Upload {...uploadProps}>
                  <Button type="primary" loading={uploading}>
                    {t("data.uploadButton")}
                  </Button>
                </Upload>
                {uploading && uploadProgress !== null ? (
                  <Progress percent={uploadProgress} size="small" />
                ) : null}
                <Divider style={{ marginBlock: 8 }} />
                <Table<DatasetResponse>
                  rowKey="id"
                  dataSource={datasets}
                  pagination={{ pageSize: 8, showSizeChanger: true }}
                  loading={loadingDatasets}
                  columns={[
                    { title: t("data.filename"), dataIndex: "filename" },
                    {
                      title: t("data.format"),
                      dataIndex: "file_format",
                      render: (fmt) => <Tag color={fmt === "parquet" ? "purple" : "blue"}>{fmt}</Tag>
                    },
                    { title: t("data.size"), dataIndex: "size_bytes", render: (v) => formatBytes(v) },
                    {
                      title: t("data.created"),
                      dataIndex: "created_at",
                      render: (v) => new Date(v).toLocaleString()
                    },
                    {
                      title: t("data.storageKey"),
                      dataIndex: "storage_key",
                      render: (v) => (
                        <Typography.Text code style={{ maxWidth: 260 }} ellipsis>
                          {v}
                        </Typography.Text>
                      )
                    },
                    {
                      title: t("data.actions"),
                      render: (_, record) => (
                        <Space>
                          <Button size="small" onClick={() => handlePreview(record.id)}>
                            {t("data.preview")}
                          </Button>
                          <Button size="small" type="primary" onClick={() => openImportModal(record)}>
                            {t("data.import")}
                          </Button>
                        </Space>
                      )
                    }
                  ]}
                />
                <Card title={t("data.importJobsTitle")} loading={loadingImports}>
                  <Table<ImportJob>
                    rowKey="id"
                    dataSource={importJobs}
                    pagination={{ pageSize: 6, showSizeChanger: true }}
                    columns={[
                      { title: t("data.importJobDataset"), dataIndex: "dataset_id", render: (v) => v.slice(0, 8) + "..." },
                      { title: t("data.importJobStatus"), dataIndex: "status" },
                      {
                        title: t("data.importJobProcessed"),
                        render: (_, record) => {
                          if (record.total_rows && record.total_rows > 0) {
                            const percent = Math.min(
                              100,
                              Number(((record.processed_rows / record.total_rows) * 100).toFixed(2))
                            );
                            return (
                              <Space direction="vertical" size={2} style={{ width: 220 }}>
                                <Typography.Text>
                                  {record.processed_rows} / {record.total_rows}
                                </Typography.Text>
                                <Progress
                                  percent={percent}
                                  size="small"
                                  status={
                                    record.status === "failed"
                                      ? "exception"
                                      : record.status === "completed"
                                        ? "success"
                                        : "active"
                                  }
                                />
                              </Space>
                            );
                          }
                          return <Typography.Text>{record.processed_rows}</Typography.Text>;
                        }
                      },
                      {
                        title: t("data.actions"),
                        render: (_, record) => (
                          <Space>
                            {record.status === "needs_config" ? (
                              <Button
                                size="small"
                                onClick={() => {
                                  const dataset = datasets.find((d) => d.id === record.dataset_id);
                                  if (dataset) {
                                    openImportModal(dataset, record);
                                  }
                                }}
                              >
                                {t("data.importConfig")}
                              </Button>
                            ) : null}
                            <Button size="small" onClick={() => handleImportAction(record, "start")}>
                              {t("data.importStart")}
                            </Button>
                            <Button size="small" onClick={() => handleImportAction(record, "pause")}>
                              {t("data.importPause")}
                            </Button>
                            <Button size="small" danger onClick={() => handleImportAction(record, "cancel")}>
                              {t("data.importCancel")}
                            </Button>
                          </Space>
                        )
                      }
                    ]}
                  />
                </Card>
              </Space>
            )
          },
          {
            key: "events",
            label: t("data.eventsTab"),
            children: (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Card size="small" title={t("data.streamingTab")}>
                  <Form layout="vertical" form={streamingForm}>
                    <Form.Item name="source" label={t("data.streamingSource")} rules={[{ required: true }]}>
                      <Input placeholder="http / mqtt / edge-gateway" />
                    </Form.Item>
                    <Form.Item name="topic" label={t("data.streamingTopic")}>
                      <Input placeholder="rig/alpha/torque" />
                    </Form.Item>
                    <Form.Item
                      name="payload"
                      label={t("data.streamingPayload")}
                      rules={[{ required: true, message: t("data.streamingPayload") }]}
                    >
                      <Input.TextArea rows={5} placeholder='{"timestamp":"2026-01-27T15:30:00Z","rpm":120}' />
                    </Form.Item>
                    <Button type="primary" onClick={handleStreamingIngest} loading={ingesting}>
                      {t("data.streamingSubmit")}
                    </Button>
                  </Form>
                </Card>

                <Card size="small" title={t("data.filtersTitle")}>
                  <Form layout="vertical" form={eventFilterForm}>
                    <Space wrap style={{ width: "100%" }}>
                      <Form.Item name="source" label={t("data.source")} style={{ minWidth: 180, marginBottom: 0 }}>
                        <Input placeholder="http / mqtt / edge" allowClear />
                      </Form.Item>
                      <Form.Item name="topic" label={t("data.topicContains")} style={{ minWidth: 220, marginBottom: 0 }}>
                        <Input placeholder="rig/demo" allowClear />
                      </Form.Item>
                      <Form.Item name="limit" label={t("data.limit")} style={{ width: 140, marginBottom: 0 }}>
                        <InputNumber min={50} max={5000} step={50} style={{ width: "100%" }} />
                      </Form.Item>
                      <Form.Item label=" " style={{ marginBottom: 0 }}>
                        <Button type="primary" onClick={() => loadEvents()} loading={loadingEvents}>
                          {t("common.apply")}
                        </Button>
                      </Form.Item>
                      <Form.Item label=" " style={{ marginBottom: 0 }}>
                        <Button
                          onClick={() => {
                            eventFilterForm.setFieldsValue({ source: undefined, topic: undefined, limit: 800 });
                            void loadEvents({ source: undefined, topic: undefined, limit: 800 });
                          }}
                          loading={loadingEvents}
                        >
                          {t("common.reset")}
                        </Button>
                      </Form.Item>
                    </Space>
                  </Form>
                </Card>

                <Card title={t("data.eventsTitle")} loading={loadingEvents}>
                  <Table<EventResponse>
                    rowKey="id"
                    dataSource={events}
                    pagination={{ pageSize: 8, showSizeChanger: true }}
                    columns={[
                      {
                        title: t("data.created"),
                        dataIndex: "created_at",
                        render: (v) => new Date(v).toLocaleString()
                      },
                      { title: t("data.source"), dataIndex: "source", render: (v) => <Tag>{v}</Tag> },
                      { title: t("data.topicContains"), dataIndex: "topic", render: (v) => v ?? "-" },
                      {
                        title: t("data.payload"),
                        dataIndex: "payload",
                        render: (payload) => (
                          <Typography.Text code style={{ maxWidth: 360 }} ellipsis>
                            {JSON.stringify(payload)}
                          </Typography.Text>
                        )
                      }
                    ]}
                  />
                </Card>
              </Space>
            )
          },
          {
            key: "sources",
            label: t("data.sourcesTab"),
            children: (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Card size="small" title={t("data.sourceCreateTitle")}>
                  <Form layout="vertical" form={sourceForm} initialValues={{ enabled: true }}>
                    <Space wrap style={{ width: "100%" }}>
                      <Form.Item name="source_type" label={t("data.sourceType")} rules={[{ required: true }]}>
                        <Select
                          style={{ minWidth: 220 }}
                          options={SOURCE_TYPE_OPTIONS.map((opt) => ({
                            label: sourceLabels[opt.value as keyof typeof sourceLabels],
                            value: opt.value
                          }))}
                        />
                      </Form.Item>
                      <Form.Item name="name" label={t("data.sourceName")}>
                        <Input placeholder={t("data.sourceNamePlaceholder")} />
                      </Form.Item>
                      <Form.Item name="enabled" label={t("data.sourceStatus")} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    </Space>
                    <Form.Item shouldUpdate noStyle>
                      {() => {
                        const type = sourceForm.getFieldValue("source_type");
                        if (!type || type === "file_upload") return null;
                        return (
                          <Space wrap style={{ width: "100%" }}>
                            <Form.Item name="stream_source" label={t("data.streamingSource")}>
                              <Input placeholder="http / edge-gateway" />
                            </Form.Item>
                            <Form.Item name="stream_topic" label={t("data.streamingTopic")}>
                              <Input placeholder="rig/alpha/torque" />
                            </Form.Item>
                            <Form.Item name="mqtt_broker" label={t("data.mqttBroker")}>
                              <Input placeholder="mqtt://broker:1883" />
                            </Form.Item>
                          </Space>
                        );
                      }}
                    </Form.Item>
                    <Button type="primary" onClick={handleAddSource} loading={creatingSource}>
                      {t("data.sourceCreateAction")}
                    </Button>
                  </Form>
                </Card>
                <Card title={t("data.sourcesTitle")} loading={loadingSources}>
                  <Table<DataSourceResponse>
                    rowKey="id"
                    dataSource={sources}
                    pagination={{ pageSize: 8, showSizeChanger: true }}
                    columns={[
                      { title: t("data.sourceName"), dataIndex: "name" },
                      {
                        title: t("data.sourceType"),
                        dataIndex: "source_type",
                        render: (v) => <Tag>{sourceLabels[v as keyof typeof sourceLabels] || v}</Tag>
                      },
                      {
                        title: t("data.sourceStatus"),
                        dataIndex: "enabled",
                        render: (v, record) => (
                          <Switch checked={v} onChange={(checked) => handleToggleSource(record, checked)} />
                        )
                      },
                      {
                        title: t("data.sourceConfig"),
                        dataIndex: "config",
                        render: (v) => (
                          <Typography.Text code style={{ maxWidth: 280 }} ellipsis>
                            {JSON.stringify(v || {})}
                          </Typography.Text>
                        )
                      },
                      {
                        title: t("data.actions"),
                        render: (_, record) => (
                          <Button size="small" onClick={() => openEditSource(record)}>
                            {t("data.edit")}
                          </Button>
                        )
                      }
                    ]}
                  />
                </Card>
              </Space>
            )
          }
        ]}
      />

      <Modal
        open={previewOpen}
        title={t("data.previewTitle")}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={900}
      >
        {previewLoading ? (
          <Typography.Text type="secondary">{t("common.loading")}</Typography.Text>
        ) : previewData?.message ? (
          <Alert type="info" showIcon message={previewData.message} />
        ) : previewData && previewData.columns.length ? (
          <Table
            rowKey={(row) => JSON.stringify(row)}
            dataSource={previewData.rows}
            pagination={false}
            scroll={{ x: true }}
            columns={previewData.columns.map((col) => ({
              title: col,
              dataIndex: col,
              render: (v) => String(v ?? "")
            }))}
          />
        ) : (
          <Typography.Text type="secondary">{t("data.previewEmpty")}</Typography.Text>
        )}
      </Modal>

      <Modal
        open={importModalOpen}
        title={t("data.importConfigTitle")}
        onCancel={() => setImportModalOpen(false)}
        onOk={submitImportJob}
        confirmLoading={importSaving}
        okText={t("data.importStart")}
      >
        <Form layout="vertical" form={importForm}>
          <Form.Item name="time_column" label={t("data.importTimeColumn")}>
            <Input placeholder={t("data.importTimeColumnPlaceholder")} />
          </Form.Item>
          <Form.Item name="start_time" label={t("data.importStartTime")}>
            <Input placeholder={t("data.importStartTimePlaceholder")} />
          </Form.Item>
          <Form.Item name="sample_rate_seconds" label={t("data.importSampleRate")}>
            <InputNumber min={0.001} step={0.001} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="delimiter" label={t("data.importDelimiter")}>
            <Input placeholder="," />
          </Form.Item>
          <Form.Item name="has_header" label={t("data.importHasHeader")} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message={t("data.importHint")}
            style={{ marginTop: 8 }}
          />
        </Form>
      </Modal>

      <Modal
        open={editSourceOpen}
        title={t("data.sourceEditTitle")}
        onCancel={() => setEditSourceOpen(false)}
        onOk={handleSaveSource}
        confirmLoading={savingSource}
        okText={t("common.save")}
      >
        <Form layout="vertical" form={sourceEditForm}>
          <Form.Item name="name" label={t("data.sourceName")}>
            <Input placeholder={t("data.sourceNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="enabled" label={t("data.sourceStatus")} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="config"
            label={t("data.sourceConfig")}
            rules={[
              {
                validator: async (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (err) {
                    return Promise.reject(new Error(t("data.jsonInvalid")));
                  }
                }
              }
            ]}
          >
            <Input.TextArea rows={6} placeholder='{"key":"value"}' />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
