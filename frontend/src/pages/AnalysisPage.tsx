import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message
} from "antd";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import {
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  createReportTemplate,
  generateAIReport,
  listAlgorithms,
  listAnalysisRuns,
  listFields,
  listReportTemplates,
  loadSeries,
  runAlgorithm,
  sendChatMessageStream,
  type AlgorithmInfo,
  type AlgorithmParam,
  type AlgorithmRunResponse,
  type AnalysisRunResponse,
  type AIChatMessage,
  type ReportTemplate,
  type SeriesPoint,
  type SeriesQuery,
  type SeriesResponse
} from "../api/analysis";
import { PageHeader, PageShell } from "../components/PageShell";
import { listWarehouses, type DataWarehouseResponse } from "../api/warehouses";
import { createReportFromRun } from "../api/reports";
import { useAuth } from "../auth/AuthProvider";

const { RangePicker } = DatePicker;

type FieldOption = { label: string; value: string };

type QueryForm = {
  field: string;
  range?: [dayjs.Dayjs, dayjs.Dayjs];
  limit: number;
};

type AlgorithmParamValue = string | number | boolean;

type AlgoForm = {
  algorithm_id: AlgorithmInfo["id"];
  params?: Record<string, AlgorithmParamValue>;
};

type AIForm = {
  title: string;
  notes?: string;
  save_as_report?: boolean;
  report_title?: string;
  template_id?: string;
};

type TemplateForm = {
  name: string;
  description?: string;
  prompt_template: string;
  enabled?: boolean;
};

type SavedSegment = {
  id: string;
  name: string;
  warehouse_id: string | null;
  field: string;
  start?: string;
  end?: string;
  limit: number;
};

type BrushSelection = {
  startIndex: number;
  endIndex: number;
  data: Array<{ ts: string; label: string }>;
};

type ChartDataPoint = {
  ts: string;
  label: string;
} & Record<string, string | number>;

function toSeriesQuery(values: QueryForm): SeriesQuery {
  const [start, end] = values.range ?? [];
  return {
    field: values.field,
    start: start ? start.toISOString() : undefined,
    end: end ? end.toISOString() : undefined,
    limit: values.limit
  };
}

function formatTs(ts: string) {
  return dayjs(ts).format("MM-DD HH:mm:ss");
}

function formatRangeDisplay(start?: string, end?: string) {
  if (!start || !end) return "-";
  return `${dayjs(start).format("MM-DD HH:mm")} ~ ${dayjs(end).format("MM-DD HH:mm")}`;
}

function computeBucketMinutes(range: QueryForm["range"], targetPoints?: number) {
  if (!range || !range[0] || !range[1] || !targetPoints) return null;
  const minutes = Math.max(1, range[1].diff(range[0], "minute", true));
  const bucket = Math.floor(minutes / Math.max(1, targetPoints));
  if (bucket < 1) return null;
  return Math.min(bucket, 43200);
}

function mergeChartData(
  base?: SeriesResponse | null,
  compareLeft?: SeriesResponse | null,
  compareRight?: SeriesResponse | null,
  algo?: AlgorithmRunResponse | null
) {
  const map = new Map<string, ChartDataPoint>();

  function upsert(points: SeriesPoint[], key: string) {
    for (const p of points) {
      const ts = p.ts;
      if (!map.has(ts)) {
        map.set(ts, { ts, label: formatTs(ts) });
      }
      map.get(ts)![key] = p.value;
    }
  }

  if (base?.points) upsert(base.points, "base");
  if (compareLeft?.points) upsert(compareLeft.points, "left");
  if (compareRight?.points) upsert(compareRight.points, "right");
  if (algo?.result_series) upsert(algo.result_series, "algo");

  return Array.from(map.values()).sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
}

function seriesToChartData(series?: SeriesResponse | null) {
  if (!series?.points?.length) return [];
  return series.points.map((point) => ({
    ts: point.ts,
    label: formatTs(point.ts),
    value: point.value
  }));
}

function formatKv(data: Record<string, unknown>) {
  return Object.entries(data).map(([k, v]) => ({ key: k, value: typeof v === "number" ? v.toFixed(4) : String(v) }));
}

function resolveParamDefault(param: AlgorithmParam, fieldOptions: FieldOption[]): AlgorithmParamValue {
  if (param.type === "field") {
    if (typeof param.default === "string" && param.default.length > 0) {
      const exists = fieldOptions.some((opt) => opt.value === param.default);
      if (exists) return param.default;
    }
    return fieldOptions[0]?.value ?? "";
  }
  if (param.type === "boolean") {
    return Boolean(param.default);
  }
  if (param.type === "text") {
    return typeof param.default === "string" ? param.default : String(param.default ?? "");
  }
  return Number(param.default ?? 0);
}

function formatAlgorithmXAxis(value: number, axis?: string | null) {
  if (axis === "frequency") {
    return `${value.toFixed(2)} Hz`;
  }
  return value.toFixed(2);
}

export function AnalysisPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);

  const [warehouses, setWarehouses] = useState<DataWarehouseResponse[]>([]);
  const [warehouseId, setWarehouseId] = useState<string | null>(null);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);

  const [fieldOptions, setFieldOptions] = useState<FieldOption[]>([]);
  const [leftFieldOptions, setLeftFieldOptions] = useState<FieldOption[]>([]);
  const [rightFieldOptions, setRightFieldOptions] = useState<FieldOption[]>([]);
  const [algorithms, setAlgorithms] = useState<AlgorithmInfo[]>([]);
  const [selectedAlgorithmId, setSelectedAlgorithmId] = useState<AlgorithmInfo["id"] | null>(null);

  const [downsampleEnabled, setDownsampleEnabled] = useState(true);
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareMode, setCompareMode] = useState<"combined" | "split">("combined");
  const [leftWarehouseId, setLeftWarehouseId] = useState<string | null>(null);
  const [rightWarehouseId, setRightWarehouseId] = useState<string | null>(null);

  const [series, setSeries] = useState<SeriesResponse | null>(null);
  const [compareLeft, setCompareLeft] = useState<SeriesResponse | null>(null);
  const [compareRight, setCompareRight] = useState<SeriesResponse | null>(null);
  const [algoResult, setAlgoResult] = useState<AlgorithmRunResponse | null>(null);

  const [runs, setRuns] = useState<AnalysisRunResponse[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);

  const [aiReport, setAIReport] = useState<string>("");
  const [aiReportId, setAIReportId] = useState<string | null>(null);
  const [loadingSeries, setLoadingSeries] = useState(false);
  const [loadingAlgo, setLoadingAlgo] = useState(false);
  const [loadingAI, setLoadingAI] = useState(false);
  const [chatMessages, setChatMessages] = useState<AIChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

  const [segments, setSegments] = useState<SavedSegment[]>([]);
  const [segmentModalOpen, setSegmentModalOpen] = useState(false);
  const [segmentName, setSegmentName] = useState("");
  const [brushSelection, setBrushSelection] = useState<BrushSelection | null>(null);

  const [queryForm] = Form.useForm<QueryForm>();
  const [compareForm] = Form.useForm<{ left: QueryForm; right: QueryForm }>();
  const [algoForm] = Form.useForm<AlgoForm>();
  const [aiForm] = Form.useForm<AIForm>();
  const [templateForm] = Form.useForm<TemplateForm>();

  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [templateSaving, setTemplateSaving] = useState(false);

  const selectedAlgorithm = useMemo(
    () => algorithms.find((a) => a.id === selectedAlgorithmId) ?? null,
    [algorithms, selectedAlgorithmId]
  );

  const warehouseOptions = useMemo(
    () => warehouses.map((wh) => ({ value: wh.id, label: wh.name })),
    [warehouses]
  );

  const buildSeriesQuery = (
    values: QueryForm,
    warehouse: string | null,
    options?: { preferRaw?: boolean }
  ): SeriesQuery => {
    const base = toSeriesQuery(values);
    const bucketMinutes =
      !options?.preferRaw && downsampleEnabled ? computeBucketMinutes(values.range, values.limit) : null;
    return {
      ...base,
      warehouse_id: warehouse ?? undefined,
      bucket_minutes: bucketMinutes ?? undefined
    };
  };

  const loadFieldOptions = async (
    targetWarehouseId: string | null,
    setter: React.Dispatch<React.SetStateAction<FieldOption[]>>
  ) => {
    const fields = await listFields(2000, targetWarehouseId ?? undefined);
    const options = fields.map((f) => ({ label: `${f.name} (${f.count})`, value: f.name }));
    setter(options);
    return options;
  };

  const canEdit = Boolean(me?.user.is_platform_admin || me?.roles?.some((r) => r === "tenant_admin" || r === "tenant_engineer"));

  async function loadRuns() {
    if (!tenantReady) return;
    setLoadingRuns(true);
    try {
      const data = await listAnalysisRuns({ limit: 120, warehouse_id: warehouseId ?? undefined });
      setRuns(data);
    } finally {
      setLoadingRuns(false);
    }
  }

  useEffect(() => {
    if (!tenantReady) return;

    async function init() {
      try {
        const [warehouseData, algos, templateData] = await Promise.all([
          listWarehouses(),
          listAlgorithms(),
          listReportTemplates()
        ]);
        setWarehouses(warehouseData);
        setTemplates(templateData);
        const defaultWarehouse = warehouseId ?? warehouseData[0]?.id ?? null;
        if (defaultWarehouse && defaultWarehouse !== warehouseId) {
          setWarehouseId(defaultWarehouse);
        }
        setAlgorithms(algos);

        if (algos.length) {
          const defaultAlgo = algos[0];
          setSelectedAlgorithmId(defaultAlgo.id);
          const params: Record<string, AlgorithmParamValue> = {};
          defaultAlgo.params.forEach((p) => {
            params[p.key] = resolveParamDefault(p, fieldOptions);
          });
          algoForm.setFieldsValue({ algorithm_id: defaultAlgo.id, params });
        }

        aiForm.setFieldsValue({ title: "WellVision Analysis Report", save_as_report: false });
      } catch (err) {
        message.error(t("analysis.initFail"));
      }
    }

    void init();
  }, [tenantReady]);

  useEffect(() => {
    if (!tenantReady) return;
    async function reloadByWarehouse() {
      try {
        setSeries(null);
        setCompareLeft(null);
        setCompareRight(null);
        setAlgoResult(null);
        setAIReport("");
        setAIReportId(null);
        setChatMessages([]);
        setChatSessionId(null);
        const options = await loadFieldOptions(warehouseId ?? null, setFieldOptions);
        if (options.length) {
          const defaultField = options[0].value;
          queryForm.setFieldsValue({ field: defaultField, limit: 2000 });
          if (compareEnabled) {
            compareForm.setFieldsValue({
              left: { field: defaultField, limit: 1000 },
              right: { field: defaultField, limit: 1000 }
            });
          }
        }
        await loadRuns();
      } catch (err) {
        message.error(t("analysis.initFail"));
      }
    }
    void reloadByWarehouse();
  }, [tenantReady, warehouseId, compareEnabled]);

  useEffect(() => {
    if (!tenantReady || !compareEnabled) return;
    void loadFieldOptions(leftWarehouseId ?? warehouseId ?? null, setLeftFieldOptions);
  }, [tenantReady, compareEnabled, leftWarehouseId, warehouseId]);

  useEffect(() => {
    if (!tenantReady || !compareEnabled) return;
    void loadFieldOptions(rightWarehouseId ?? warehouseId ?? null, setRightFieldOptions);
  }, [tenantReady, compareEnabled, rightWarehouseId, warehouseId]);

  useEffect(() => {
    const algo = algorithms.find((a) => a.id === selectedAlgorithmId);
    if (!algo || fieldOptions.length === 0) return;
    const existing = algoForm.getFieldValue("params") ?? {};
    let changed = false;
    const nextParams = { ...existing };
    for (const param of algo.params) {
      if (param.type === "field" && !nextParams[param.key]) {
        nextParams[param.key] = resolveParamDefault(param, fieldOptions);
        changed = true;
      }
    }
    if (changed) {
      algoForm.setFieldsValue({ params: nextParams });
    }
  }, [algorithms, selectedAlgorithmId, fieldOptions]);

  const chartData = useMemo(
    () => mergeChartData(series, compareLeft, compareRight, algoResult),
    [series, compareLeft, compareRight, algoResult]
  );

  const leftChartData = useMemo(() => seriesToChartData(compareLeft), [compareLeft]);
  const rightChartData = useMemo(() => seriesToChartData(compareRight), [compareRight]);
  const algoSpectrumData = useMemo(() => {
    if (!algoResult?.result_points?.length) return [];
    return algoResult.result_points.map((p) => ({
      x: p.x,
      value: p.y,
      label: formatAlgorithmXAxis(p.x, algoResult.x_axis)
    }));
  }, [algoResult]);

  const loadBaseSeries = async (options?: { forceRaw?: boolean }) => {
    const values = await queryForm.validateFields();
    setLoadingSeries(true);
    try {
      const res = await loadSeries(buildSeriesQuery(values, warehouseId, { preferRaw: options?.forceRaw }));
      setSeries(res);
      setCompareLeft(null);
      setCompareRight(null);
      setAlgoResult(null);
    } catch (err) {
      message.error(t("analysis.loadFail"));
    } finally {
      setLoadingSeries(false);
    }
  };

  const loadCompare = async () => {
    const values = await compareForm.validateFields();
    setLoadingSeries(true);
    try {
      const left = buildSeriesQuery(values.left, leftWarehouseId ?? warehouseId ?? null);
      const right = buildSeriesQuery(values.right, rightWarehouseId ?? warehouseId ?? null);
      const [leftRes, rightRes] = await Promise.all([loadSeries(left), loadSeries(right)]);
      setSeries(null);
      setAlgoResult(null);
      setCompareLeft(leftRes);
      setCompareRight(rightRes);
    } catch (err) {
      message.error(t("analysis.compareFail"));
    } finally {
      setLoadingSeries(false);
    }
  };

  const onAlgorithmChange = (algorithmId: AlgorithmInfo["id"]) => {
    setSelectedAlgorithmId(algorithmId);
    const algo = algorithms.find((a) => a.id === algorithmId);
    if (!algo) return;
    const params: Record<string, AlgorithmParamValue> = {};
    algo.params.forEach((p) => {
      params[p.key] = resolveParamDefault(p, fieldOptions);
    });
    algoForm.setFieldsValue({ algorithm_id: algorithmId, params });
  };

  const runSelectedAlgorithm = async () => {
    const q = await queryForm.validateFields();
    const a = await algoForm.validateFields();
    setLoadingAlgo(true);
    try {
      const params = a.params ?? {};
      const res = await runAlgorithm({
        algorithm_id: a.algorithm_id,
        series: buildSeriesQuery(q, warehouseId ?? null, { preferRaw: true }),
        params
      });
      setAlgoResult(res);
      message.success(t("analysis.runSuccess"));
      await loadRuns();
    } catch (err) {
      message.error(t("analysis.runFail"));
    } finally {
      setLoadingAlgo(false);
    }
  };

  const createReportFromLatestRun = async () => {
    if (!algoResult?.run_id) {
      message.warning(t("analysis.needRunId"));
      return;
    }
    try {
      const report = await createReportFromRun({ run_id: algoResult.run_id });
      message.success(`${t("analysis.reportFromRunSuccess")}: ${report.title}`);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("analysis.reportFromRunFail"));
    }
  };

  const createReportFromRunRow = async (run: AnalysisRunResponse) => {
    try {
      const title = `${t("analysis.reportTitlePrefix")} ${run.algorithm_id} / ${run.field}`;
      const report = await createReportFromRun({ run_id: run.id, title });
      message.success(`${t("analysis.reportFromRunSuccess")}: ${report.title}`);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("analysis.reportFromRunFail"));
    }
  };

  const runAIReport = async () => {
    const q = await queryForm.validateFields();
    const ai = await aiForm.validateFields();
    setLoadingAI(true);
    try {
      const res = await generateAIReport({
        title: ai.title,
        notes: ai.notes,
        series: buildSeriesQuery(q, warehouseId ?? null, { preferRaw: true }),
        algorithm_result: algoResult,
        save_as_report: Boolean(ai.save_as_report),
        report_title: ai.report_title,
        template_id: ai.template_id
      });
      setAIReport(res.report_markdown);
      setAIReportId(res.report_id ?? null);
      if (res.report_id) {
        message.success(`${t("analysis.aiSaved")} (${res.model})`);
      } else {
        message.success(`${t("analysis.aiSuccess")} (${res.model})`);
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("analysis.aiFail"));
    } finally {
      setLoadingAI(false);
    }
  };

  const handleCreateTemplate = async () => {
    const values = await templateForm.validateFields();
    setTemplateSaving(true);
    try {
      const created = await createReportTemplate({
        name: values.name,
        description: values.description,
        prompt_template: values.prompt_template,
        enabled: values.enabled ?? true
      });
      message.success(t("analysis.templateCreated"));
      setTemplates((prev) => [created, ...prev]);
      aiForm.setFieldsValue({ template_id: created.id });
      setTemplateModalOpen(false);
      templateForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("analysis.templateCreateFail"));
    } finally {
      setTemplateSaving(false);
    }
  };

  const handleSendChat = async (content: string) => {
    if (!content.trim()) return;
    const q = queryForm.getFieldsValue() as QueryForm;
    const [start, end] = q.range ?? [];
    const userMessage: AIChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString()
    };
    const assistantLocalId = `local-assistant-${Date.now()}`;
    setChatMessages((prev) => [
      ...prev,
      userMessage,
      {
        id: assistantLocalId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString()
      }
    ]);
    setChatInput("");
    setChatLoading(true);
    chatAbortRef.current?.abort();
    const controller = new AbortController();
    chatAbortRef.current = controller;
    try {
      await sendChatMessageStream(
        {
          session_id: chatSessionId,
          title: t("analysis.chatSessionTitle"),
          message: content,
          context: {
            warehouse_id: warehouseId ?? undefined,
            field: q.field,
            start: start ? start.toISOString() : undefined,
            end: end ? end.toISOString() : undefined,
            algorithm_result: algoResult ?? undefined
          }
        },
        {
          onDelta: (delta) => {
            setChatMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantLocalId
                  ? { ...msg, content: `${msg.content}${delta}` }
                  : msg
              )
            );
          },
          onFinal: (final) => {
            setChatSessionId(final.session_id);
            setChatMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantLocalId
                  ? {
                      ...msg,
                      id: final.message_id,
                      content: final.reply || msg.content,
                      created_at: new Date().toISOString()
                    }
                  : msg
              )
            );
          },
          onError: (detail) => {
            message.error(detail || t("analysis.chatFail"));
            setChatMessages((prev) => prev.filter((msg) => msg.id !== assistantLocalId));
          }
        },
        { signal: controller.signal }
      );
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        message.error(err?.response?.data?.detail || t("analysis.chatFail"));
      }
    } finally {
      setChatLoading(false);
    }
  };

  const handleStopChat = () => {
    chatAbortRef.current?.abort();
    setChatLoading(false);
  };

  useEffect(() => {
    const node = chatScrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [chatMessages, chatLoading]);

  const handleClearChat = () => {
    setChatMessages([]);
    setChatSessionId(null);
  };

  const handleBrushChange = (data: Array<{ ts: string; label: string }>) => (range: any) => {
    if (!range || range.startIndex === undefined || range.endIndex === undefined) {
      setBrushSelection(null);
      return;
    }
    setBrushSelection({
      startIndex: range.startIndex,
      endIndex: range.endIndex,
      data
    });
  };

  const selectedRange = useMemo(() => {
    if (!brushSelection) return null;
    const { data, startIndex, endIndex } = brushSelection;
    const start = data[Math.max(0, startIndex)];
    const end = data[Math.min(data.length - 1, endIndex)];
    if (!start || !end) return null;
    return { start: dayjs(start.ts), end: dayjs(end.ts) };
  }, [brushSelection]);

  const applySelectedRangeToBase = async () => {
    if (!selectedRange) return;
    queryForm.setFieldsValue({ range: [selectedRange.start, selectedRange.end] });
    await loadBaseSeries({ forceRaw: true });
  };

  const applySelectedRangeToCompare = (side: "left" | "right") => {
    if (!selectedRange) return;
    const existing = compareForm.getFieldValue([side]) || {};
    compareForm.setFieldsValue({
      [side]: {
        ...existing,
        range: [selectedRange.start, selectedRange.end]
      }
    });
  };

  const resetZoom = async () => {
    queryForm.setFieldsValue({ range: undefined });
    setBrushSelection(null);
    await loadBaseSeries();
  };

  const openSegmentModal = () => {
    const values = queryForm.getFieldsValue() as QueryForm;
    if (!values.field) {
      message.warning(t("analysis.fieldPlaceholder"));
      return;
    }
    if (!selectedRange && !values.range) {
      message.warning(t("analysis.segmentNeedRange"));
      return;
    }
    setSegmentName(`${t("analysis.segmentDefaultName")} ${dayjs().format("MMDD-HHmm")}`);
    setSegmentModalOpen(true);
  };

  const handleSaveSegment = async () => {
    const values = queryForm.getFieldsValue() as QueryForm;
    const range = selectedRange
      ? [selectedRange.start, selectedRange.end]
      : values.range
      ? [values.range[0], values.range[1]]
      : null;
    if (!range || !range[0] || !range[1]) {
      message.warning(t("analysis.segmentNeedRange"));
      return;
    }
    const [start, end] = range;
    const name = segmentName.trim() || `${t("analysis.segmentDefaultName")} ${dayjs().format("MMDD-HHmm")}`;
    const next: SavedSegment = {
      id: `seg-${Date.now()}`,
      name,
      warehouse_id: warehouseId ?? null,
      field: values.field,
      start: start.toISOString(),
      end: end.toISOString(),
      limit: values.limit
    };
    setSegments((prev) => [next, ...prev]);
    setSegmentModalOpen(false);
    setSegmentName("");
  };

  const applySegmentToBase = async (segment: SavedSegment) => {
    const range: QueryForm["range"] =
      segment.start && segment.end ? [dayjs(segment.start), dayjs(segment.end)] : undefined;
    queryForm.setFieldsValue({
      field: segment.field,
      range,
      limit: segment.limit
    });
    if (segment.warehouse_id !== warehouseId) {
      setWarehouseId(segment.warehouse_id);
    }
    setLoadingSeries(true);
    try {
      const res = await loadSeries(
        buildSeriesQuery(
          {
            field: segment.field,
            range,
            limit: segment.limit
          },
          segment.warehouse_id ?? null
        )
      );
      setSeries(res);
      setCompareLeft(null);
      setCompareRight(null);
      setAlgoResult(null);
    } catch (err) {
      message.error(t("analysis.loadFail"));
    } finally {
      setLoadingSeries(false);
    }
  };

  const applySegmentToCompare = (segment: SavedSegment, side: "left" | "right") => {
    const range = segment.start && segment.end ? [dayjs(segment.start), dayjs(segment.end)] : undefined;
    compareForm.setFieldsValue({
      [side]: {
        field: segment.field,
        range,
        limit: segment.limit
      }
    });
    if (side === "left") {
      setLeftWarehouseId(segment.warehouse_id ?? null);
    } else {
      setRightWarehouseId(segment.warehouse_id ?? null);
    }
  };

  if (!tenantReady) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("analysis.noTenant")}
        description={t("analysis.noTenantDesc")}
      />
    );
  }

  return (
    <PageShell>
      <PageHeader title={t("analysis.title")} subtitle={t("analysis.subtitle")} />

      <Card className="wv-toolbar-card" size="small">
        <Space wrap align="center" size={[16, 8]}>
          <Space align="center">
            <Typography.Text>{t("analysis.warehouseFilter")}</Typography.Text>
            <Select
              style={{ minWidth: 220 }}
              value={warehouseId ?? "all"}
              options={[{ value: "all", label: t("analysis.allWarehouses") }, ...warehouseOptions]}
              onChange={(value) => setWarehouseId(value === "all" ? null : value)}
            />
          </Space>

          <Form layout="inline" form={queryForm} initialValues={{ limit: 2000 }}>
            <Form.Item name="field" label={t("analysis.field")} rules={[{ required: true }]}>
              <Select
                options={fieldOptions}
                placeholder={t("analysis.fieldPlaceholder")}
                showSearch
                style={{ minWidth: 220 }}
              />
            </Form.Item>
            <Form.Item name="range" label={t("analysis.timeRange")}>
              <RangePicker showTime />
            </Form.Item>
            <Form.Item name="limit" label={t("analysis.limit")}>
              <InputNumber min={100} max={20000} step={100} />
            </Form.Item>
          </Form>

          <Space align="center">
            <Typography.Text>{t("analysis.downsample")}</Typography.Text>
            <Switch checked={downsampleEnabled} onChange={setDownsampleEnabled} />
          </Space>

          <Button type="primary" onClick={() => loadBaseSeries()} loading={loadingSeries}>
            {t("analysis.loadSeries")}
          </Button>
          <Button onClick={openSegmentModal} disabled={!queryForm.getFieldValue("field")}>
            {t("analysis.segmentSave")}
          </Button>

          <Space align="center">
            <Typography.Text>{t("analysis.compareToggle")}</Typography.Text>
            <Switch
              checked={compareEnabled}
              onChange={(checked) => {
                setCompareEnabled(checked);
                if (!checked) {
                  setCompareLeft(null);
                  setCompareRight(null);
                }
              }}
            />
            {compareEnabled ? (
              <Select
                style={{ minWidth: 160 }}
                value={compareMode}
                onChange={(value) => setCompareMode(value as "combined" | "split")}
                options={[
                  { value: "combined", label: t("analysis.compareModeCombined") },
                  { value: "split", label: t("analysis.compareModeSplit") }
                ]}
              />
            ) : null}
          </Space>
        </Space>
        {!warehouses.length ? <Typography.Text type="secondary">{t("analysis.noWarehouses")}</Typography.Text> : null}
      </Card>

      {compareEnabled ? (
        <Card size="small" title={t("analysis.compareConfig")}>
          <Form layout="vertical" form={compareForm}>
            <Row gutter={[16, 16]}>
              <Col xs={24} lg={12}>
                <Typography.Text strong>{t("analysis.leftSegment")}</Typography.Text>
                <Space direction="vertical" size={8} style={{ width: "100%", marginTop: 8 }}>
                  <Space align="center" wrap>
                    <Typography.Text type="secondary">{t("analysis.warehouseFilter")}</Typography.Text>
                    <Select
                      style={{ minWidth: 220 }}
                      value={leftWarehouseId ?? "base"}
                      options={[
                        { value: "base", label: t("analysis.useBaseWarehouse") },
                        ...warehouseOptions
                      ]}
                      onChange={(value) => setLeftWarehouseId(value === "base" ? null : value)}
                    />
                  </Space>
                  <Form.Item name={["left", "field"]} label={t("analysis.field")} rules={[{ required: true }]}>
                    <Select
                      options={leftWarehouseId ? leftFieldOptions : fieldOptions}
                      placeholder={t("analysis.fieldPlaceholder")}
                      showSearch
                    />
                  </Form.Item>
                  <Form.Item name={["left", "range"]} label={t("analysis.range")}>
                    <RangePicker showTime style={{ width: "100%" }} />
                  </Form.Item>
                  <Form.Item name={["left", "limit"]} label={t("analysis.limit")} initialValue={1000}>
                    <InputNumber min={100} max={20000} step={100} style={{ width: "100%" }} />
                  </Form.Item>
                </Space>
              </Col>
              <Col xs={24} lg={12}>
                <Typography.Text strong>{t("analysis.rightSegment")}</Typography.Text>
                <Space direction="vertical" size={8} style={{ width: "100%", marginTop: 8 }}>
                  <Space align="center" wrap>
                    <Typography.Text type="secondary">{t("analysis.warehouseFilter")}</Typography.Text>
                    <Select
                      style={{ minWidth: 220 }}
                      value={rightWarehouseId ?? "base"}
                      options={[
                        { value: "base", label: t("analysis.useBaseWarehouse") },
                        ...warehouseOptions
                      ]}
                      onChange={(value) => setRightWarehouseId(value === "base" ? null : value)}
                    />
                  </Space>
                  <Form.Item name={["right", "field"]} label={t("analysis.field")} rules={[{ required: true }]}>
                    <Select
                      options={rightWarehouseId ? rightFieldOptions : fieldOptions}
                      placeholder={t("analysis.fieldPlaceholder")}
                      showSearch
                    />
                  </Form.Item>
                  <Form.Item name={["right", "range"]} label={t("analysis.range")}>
                    <RangePicker showTime style={{ width: "100%" }} />
                  </Form.Item>
                  <Form.Item name={["right", "limit"]} label={t("analysis.limit")} initialValue={1000}>
                    <InputNumber min={100} max={20000} step={100} style={{ width: "100%" }} />
                  </Form.Item>
                </Space>
              </Col>
            </Row>
            <Button onClick={loadCompare} loading={loadingSeries}>
              {t("analysis.compareAction")}
            </Button>
          </Form>
        </Card>
      ) : null}

      <Card title={t("analysis.chart")}>
        {compareEnabled && compareMode === "split" ? (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <div style={{ width: "100%", height: 320 }}>
                <ResponsiveContainer>
                  <LineChart data={leftChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" minTickGap={24} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="value" name={t("analysis.leftSegment")} dot={false} stroke="#722ed1" />
                    <Brush dataKey="label" height={24} travellerWidth={10} onChange={handleBrushChange(leftChartData)} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Col>
            <Col xs={24} lg={12}>
              <div style={{ width: "100%", height: 320 }}>
                <ResponsiveContainer>
                  <LineChart data={rightChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" minTickGap={24} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="value" name={t("analysis.rightSegment")} dot={false} stroke="#13c2c2" />
                    <Brush dataKey="label" height={24} travellerWidth={10} onChange={handleBrushChange(rightChartData)} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Col>
          </Row>
        ) : (
          <div style={{ width: "100%", height: 360 }}>
            <ResponsiveContainer>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" minTickGap={24} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="base" name={t("analysis.baseSeries")} dot={false} stroke="#1677ff" />
                <Line type="monotone" dataKey="left" name={t("analysis.leftSegment")} dot={false} stroke="#722ed1" />
                <Line type="monotone" dataKey="right" name={t("analysis.rightSegment")} dot={false} stroke="#13c2c2" />
                <Line type="monotone" dataKey="algo" name={t("analysis.algorithm")} dot={false} stroke="#fa8c16" />
                <Brush dataKey="label" height={24} travellerWidth={10} onChange={handleBrushChange(chartData)} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div style={{ marginTop: 12 }}>
          {selectedRange ? (
            <Space wrap>
              <Tag color="blue">
                {t("analysis.selectedRange")}: {selectedRange.start.format("MM-DD HH:mm")} ~{" "}
                {selectedRange.end.format("MM-DD HH:mm")}
              </Tag>
              <Button onClick={applySelectedRangeToBase}>{t("analysis.zoomToRange")}</Button>
              <Button onClick={() => applySelectedRangeToCompare("left")} disabled={!compareEnabled}>
                {t("analysis.applyLeft")}
              </Button>
              <Button onClick={() => applySelectedRangeToCompare("right")} disabled={!compareEnabled}>
                {t("analysis.applyRight")}
              </Button>
              <Button onClick={resetZoom}>{t("analysis.resetZoom")}</Button>
            </Space>
          ) : (
            <Typography.Text type="secondary">{t("analysis.noSelection")}</Typography.Text>
          )}
        </div>
      </Card>

      {segments.length ? (
        <Card className="wv-table-card" size="small" title={t("analysis.segmentFolder")}>
          <Table<SavedSegment>
            rowKey="id"
            dataSource={segments}
            pagination={{ pageSize: 6 }}
            columns={[
              { title: t("analysis.segmentName"), dataIndex: "name" },
              {
                title: t("analysis.segmentWarehouse"),
                dataIndex: "warehouse_id",
                render: (v) => warehouses.find((w) => w.id === v)?.name || t("analysis.useBaseWarehouse")
              },
              { title: t("analysis.field"), dataIndex: "field" },
              {
                title: t("analysis.segmentRange"),
                render: (_, record) => formatRangeDisplay(record.start, record.end)
              },
              {
                title: t("analysis.actions"),
                render: (_, record) => (
                  <Space wrap>
                    <Button size="small" onClick={() => applySegmentToBase(record)}>
                      {t("analysis.segmentApplyBase")}
                    </Button>
                    <Button size="small" onClick={() => applySegmentToCompare(record, "left")} disabled={!compareEnabled}>
                      {t("analysis.segmentApplyLeft")}
                    </Button>
                    <Button size="small" onClick={() => applySegmentToCompare(record, "right")} disabled={!compareEnabled}>
                      {t("analysis.segmentApplyRight")}
                    </Button>
                  </Space>
                )
              }
            ]}
          />
        </Card>
      ) : null}

      <Tabs
        items={[
          {
            key: "stats",
            label: t("analysis.stats"),
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card size="small" title={t("analysis.baseStats")}>
                    {series ? (
                      <Descriptions column={1} size="small">
                        {formatKv(series.stats).map((item) => (
                          <Descriptions.Item key={item.key} label={item.key}>
                            {item.value}
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    ) : (
                      <Typography.Text type="secondary">{t("common.noData")}</Typography.Text>
                    )}
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card size="small" title={t("analysis.compareStats")}>
                    {compareLeft && compareRight ? (
                      <Descriptions column={1} size="small">
                        <Descriptions.Item label={t("analysis.leftCount")}>{compareLeft.stats.count}</Descriptions.Item>
                        <Descriptions.Item label={t("analysis.rightCount")}>{compareRight.stats.count}</Descriptions.Item>
                        <Descriptions.Item label={t("analysis.leftAvg")}>
                          {Number(compareLeft.stats.avg ?? 0).toFixed(4)}
                        </Descriptions.Item>
                        <Descriptions.Item label={t("analysis.rightAvg")}>
                          {Number(compareRight.stats.avg ?? 0).toFixed(4)}
                        </Descriptions.Item>
                      </Descriptions>
                    ) : (
                      <Typography.Text type="secondary">{t("analysis.noCompare")}</Typography.Text>
                    )}
                  </Card>
                </Col>
              </Row>
            )
          },
          {
            key: "algorithm",
            label: t("analysis.algorithms"),
            forceRender: true,
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card size="small" title={t("analysis.runAlgorithm")}>
                    <Form layout="vertical" form={algoForm} initialValues={{ algorithm_id: selectedAlgorithmId ?? undefined }}>
                      <Form.Item name="algorithm_id" label={t("analysis.algorithm")} rules={[{ required: true }]}>
                        <Select
                          options={algorithms.map((a) => ({ label: `${a.name} (${a.id})`, value: a.id }))}
                          placeholder={t("analysis.algorithmPlaceholder")}
                          onChange={onAlgorithmChange}
                        />
                      </Form.Item>

                      {selectedAlgorithm?.params.map((param) => {
                        if (param.type === "field") {
                          return (
                            <Form.Item
                              key={param.key}
                              name={["params", param.key]}
                              label={param.label}
                              tooltip={param.description ?? undefined}
                              rules={[{ required: true }]}
                            >
                              <Select
                                options={fieldOptions}
                                placeholder={t("analysis.fieldPlaceholder")}
                                showSearch
                              />
                            </Form.Item>
                          );
                        }
                        if (param.type === "boolean") {
                          return (
                            <Form.Item
                              key={param.key}
                              name={["params", param.key]}
                              label={param.label}
                              tooltip={param.description ?? undefined}
                              valuePropName="checked"
                            >
                              <Switch />
                            </Form.Item>
                          );
                        }
                        if (param.type === "text") {
                          return (
                            <Form.Item
                              key={param.key}
                              name={["params", param.key]}
                              label={param.label}
                              tooltip={param.description ?? undefined}
                            >
                              <Input />
                            </Form.Item>
                          );
                        }
                        return (
                          <Form.Item
                            key={param.key}
                            name={["params", param.key]}
                            label={param.label}
                            tooltip={param.description ?? undefined}
                          >
                            <InputNumber
                              min={param.min ?? undefined}
                              max={param.max ?? undefined}
                              step={param.step ?? undefined}
                              style={{ width: "100%" }}
                            />
                          </Form.Item>
                        );
                      })}

                      {selectedAlgorithm ? (
                        <Typography.Paragraph type="secondary" style={{ marginTop: -4 }}>
                          {selectedAlgorithm.description}
                        </Typography.Paragraph>
                      ) : null}

                      <Space direction="vertical" style={{ width: "100%" }}>
                        <Button type="primary" onClick={runSelectedAlgorithm} loading={loadingAlgo} block>
                          {t("analysis.runAlgorithm")}
                        </Button>
                        <Button onClick={createReportFromLatestRun} disabled={!canEdit || !algoResult?.run_id} block>
                          {t("analysis.createReportFromRun")}
                        </Button>
                        {algoResult?.run_id ? (
                          <Typography.Text type="secondary">
                            {t("analysis.runIdLabel")}: {algoResult.run_id}
                          </Typography.Text>
                        ) : null}
                      </Space>
                    </Form>
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Space direction="vertical" size={16} style={{ width: "100%" }}>
                    {algoSpectrumData.length ? (
                      <Card size="small" title={t("analysis.algorithmChart")}>
                        <ResponsiveContainer width="100%" height={240}>
                          <LineChart data={algoSpectrumData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="label" minTickGap={24} />
                            <YAxis />
                            <Tooltip />
                            <Line type="monotone" dataKey="value" stroke="#7c3aed" dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </Card>
                    ) : null}
                    <Card size="small" title={t("analysis.algorithmMetrics")}>
                      {algoResult ? (
                        <Descriptions column={1} size="small">
                          <Descriptions.Item label="algorithm">{algoResult.algorithm_id}</Descriptions.Item>
                          {formatKv(algoResult.metrics).map((item) => (
                            <Descriptions.Item key={item.key} label={item.key}>
                              {item.value}
                            </Descriptions.Item>
                          ))}
                        </Descriptions>
                      ) : (
                        <Typography.Text type="secondary">{t("analysis.noAlgo")}</Typography.Text>
                      )}
                    </Card>
                  </Space>
                </Col>
              </Row>
            )
          },
          {
            key: "runs",
            label: t("analysis.runHistory"),
            children: (
              <Card
                className="wv-table-card"
                size="small"
                title={t("analysis.recentRuns")}
                extra={<Button onClick={() => loadRuns()}>{t("analysis.refresh")}</Button>}
                loading={loadingRuns}
              >
                <Table<AnalysisRunResponse>
                  rowKey="id"
                  dataSource={runs}
                  pagination={{ pageSize: 8 }}
                  columns={[
                    {
                      title: t("analysis.runsTime"),
                      dataIndex: "created_at",
                      render: (v) => new Date(v).toLocaleString()
                    },
                    {
                      title: t("analysis.runsAlgorithm"),
                      dataIndex: "algorithm_id",
                      render: (v) => <Tag color="blue">{v}</Tag>
                    },
                    { title: t("analysis.runsField"), dataIndex: "field" },
                    {
                      title: t("analysis.runsMetrics"),
                      dataIndex: "metrics",
                      render: (m) => (
                        <Typography.Text code style={{ maxWidth: 320 }} ellipsis>
                          {JSON.stringify(m)}
                        </Typography.Text>
                      )
                    },
                    {
                      title: t("analysis.runsAction"),
                      render: (_, record) => (
                        <Button size="small" onClick={() => createReportFromRunRow(record)} disabled={!canEdit}>
                          {t("analysis.runsCreateReport")}
                        </Button>
                      )
                    }
                  ]}
                />
              </Card>
            )
          },
          {
            key: "ai",
            label: t("analysis.aiReport"),
            forceRender: true,
            children: (
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={10}>
                  <Card
                    size="small"
                    title={t("analysis.generateAI")}
                    extra={
                      <Button size="small" onClick={() => setTemplateModalOpen(true)} disabled={!canEdit}>
                        {t("analysis.templateNew")}
                      </Button>
                    }
                  >
                    <Form layout="vertical" form={aiForm} initialValues={{ title: "WellVision Analysis Report", save_as_report: false }}>
                      <Form.Item name="template_id" label={t("analysis.reportTemplate")}>
                        <Select
                          allowClear
                          placeholder={t("analysis.reportTemplatePlaceholder")}
                          options={templates
                            .filter((tpl) => tpl.enabled)
                            .map((tpl) => ({ value: tpl.id, label: tpl.name }))}
                        />
                      </Form.Item>
                      <Form.Item name="title" label={t("analysis.reportTitle")} rules={[{ required: true }]}>
                        <Input placeholder={t("analysis.reportTitle")} />
                      </Form.Item>
                      <Form.Item name="notes" label={t("analysis.notes")}>
                        <Input.TextArea rows={6} placeholder={t("analysis.notesPlaceholder")} />
                      </Form.Item>
                      <Form.Item name="save_as_report" label={t("analysis.saveAsReport")} valuePropName="checked">
                        <Switch disabled={!canEdit} />
                      </Form.Item>
                      <Form.Item shouldUpdate noStyle>
                        {() =>
                          aiForm.getFieldValue("save_as_report") ? (
                            <Form.Item name="report_title" label={t("analysis.reportTitle")}>
                              <Input placeholder={t("analysis.reportTitle")} />
                            </Form.Item>
                          ) : null
                        }
                      </Form.Item>
                      <Button type="primary" onClick={runAIReport} loading={loadingAI} block>
                        {t("analysis.generateAI")}
                      </Button>
                    </Form>
                    <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
                      {t("analysis.openAiHint")}
                    </Typography.Paragraph>
                    {aiReportId ? (
                      <Typography.Paragraph type="secondary">
                        {t("analysis.aiSavedInfo")}: {aiReportId}
                      </Typography.Paragraph>
                    ) : null}
                  </Card>
                </Col>
                <Col xs={24} lg={14}>
                  <Card size="small" title={t("analysis.aiOutput")}>
                    <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>
                      {aiReport || t("analysis.aiOutputPlaceholder")}
                    </Typography.Paragraph>
                  </Card>
                </Col>
              </Row>
            )
          }
          ,
          {
            key: "chat",
            label: t("analysis.chatTab"),
            children: (
              <Card
                title={t("analysis.chatTitle")}
                extra={
                  <Button size="small" onClick={handleClearChat}>
                    {t("analysis.chatClear")}
                  </Button>
                }
              >
                <div
                  ref={chatScrollRef}
                  style={{
                    minHeight: 220,
                    maxHeight: 360,
                    overflowY: "auto",
                    background: "#fafafa",
                    padding: 12,
                    borderRadius: 8,
                    border: "1px solid #f0f0f0"
                  }}
                >
                  {chatMessages.length ? (
                    <Space direction="vertical" size={12} style={{ width: "100%" }}>
                      {chatMessages.map((msg) => (
                        <div key={msg.id}>
                          <Tag color={msg.role === "user" ? "blue" : "green"}>
                            {msg.role === "user" ? t("analysis.chatRoleUser") : t("analysis.chatRoleAssistant")}
                          </Tag>
                          <Typography.Paragraph style={{ margin: "4px 0 0 0", whiteSpace: "pre-wrap" }}>
                            {msg.content}
                          </Typography.Paragraph>
                        </div>
                      ))}
                    </Space>
                  ) : (
                    <Typography.Text type="secondary">{t("analysis.chatEmpty")}</Typography.Text>
                  )}
                </div>

                <Space direction="vertical" style={{ width: "100%", marginTop: 12 }}>
                  <Input.TextArea
                    rows={3}
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder={t("analysis.chatPlaceholder")}
                  />
                  <Space>
                    <Button
                      type="primary"
                      onClick={() => handleSendChat(chatInput)}
                      loading={chatLoading}
                      disabled={chatLoading}
                    >
                      {t("analysis.chatSend")}
                    </Button>
                    <Button onClick={handleStopChat} disabled={!chatLoading}>
                      {t("analysis.chatStop")}
                    </Button>
                  </Space>
                  <Space wrap>
                    <Button onClick={() => handleSendChat(t("analysis.chatPrompt1"))}>
                      {t("analysis.chatPrompt1")}
                    </Button>
                    <Button onClick={() => handleSendChat(t("analysis.chatPrompt2"))}>
                      {t("analysis.chatPrompt2")}
                    </Button>
                    <Button onClick={() => handleSendChat(t("analysis.chatPrompt3"))}>
                      {t("analysis.chatPrompt3")}
                    </Button>
                  </Space>
                </Space>
              </Card>
            )
          }
        ]}
      />

      <Modal
        open={segmentModalOpen}
        title={t("analysis.segmentSave")}
        onCancel={() => setSegmentModalOpen(false)}
        onOk={handleSaveSegment}
        okText={t("common.save")}
      >
        <Form layout="vertical">
          <Form.Item label={t("analysis.segmentName")}>
            <Input value={segmentName} onChange={(e) => setSegmentName(e.target.value)} />
          </Form.Item>
          <Typography.Text type="secondary">
            {selectedRange
              ? `${t("analysis.segmentRange")}: ${selectedRange.start.format("MM-DD HH:mm")} ~ ${selectedRange.end.format(
                  "MM-DD HH:mm"
                )}`
              : t("analysis.segmentUseFormRange")}
          </Typography.Text>
        </Form>
      </Modal>

      <Modal
        open={templateModalOpen}
        title={t("analysis.templateModalTitle")}
        onCancel={() => setTemplateModalOpen(false)}
        onOk={handleCreateTemplate}
        confirmLoading={templateSaving}
        okText={t("common.save")}
      >
        <Form layout="vertical" form={templateForm} initialValues={{ enabled: true }}>
          <Form.Item name="name" label={t("analysis.templateName")} rules={[{ required: true }]}>
            <Input placeholder={t("analysis.templateNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="description" label={t("analysis.templateDesc")}>
            <Input placeholder={t("analysis.templateDescPlaceholder")} />
          </Form.Item>
          <Form.Item name="prompt_template" label={t("analysis.templatePrompt")} rules={[{ required: true }]}>
            <Input.TextArea rows={8} placeholder={t("analysis.templatePromptPlaceholder")} />
          </Form.Item>
          <Form.Item name="enabled" label={t("analysis.templateEnabled")} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
