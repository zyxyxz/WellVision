import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Typography,
  message
} from "antd";
import { useTranslation } from "react-i18next";

import { CodeEditor } from "../components/CodeEditor";
import {
  createAlgorithmDefinition,
  generateAlgorithmByAI,
  getAlgorithmDefinition,
  updateAlgorithmDefinition,
  type AlgorithmDefinition
} from "../api/algorithms";
import { useAuth } from "../auth/AuthProvider";
import { PageActions, PageHeader, PageShell } from "../components/PageShell";

type AlgorithmKind = "python" | "http" | "workflow";

type AlgorithmFormValues = {
  name: string;
  key?: string;
  kind: AlgorithmKind;
  description?: string;
  enabled?: boolean;
};

const CONFIG_TEMPLATES: Record<AlgorithmKind, Record<string, unknown>> = {
  python: {
    code: "def run(points, params):\n    # points: [{\"ts\": \"...\", \"value\": 1.23}, ...]\n    # return {'result_series': [...], 'metrics': {...}}\n    window = int(params.get('window', 10))\n    values = [p['value'] for p in points]\n    result = []\n    for i, p in enumerate(points):\n        start = max(0, i - window + 1)\n        avg = sum(values[start:i+1]) / (i - start + 1)\n        result.append({'ts': p['ts'], 'value': avg})\n    return {'result_series': result, 'metrics': {'window': window}}",
    params: [{ key: "window", label: "Window", default: 10, min: 2, max: 200, step: 1 }]
  },
  http: {
    url: "https://example.com/algorithm",
    method: "POST",
    timeout_seconds: 15,
    headers: { "X-API-Key": "replace-me" },
    params: [{ key: "threshold", label: "Threshold", default: 3, min: 1, max: 10, step: 0.5 }]
  },
  workflow: {
    steps: [
      { algorithm_id: "moving_average", params: { window: 20 } },
      { algorithm_id: "zscore_anomaly", params: { threshold: 3 } }
    ],
    params: []
  }
};

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function prettyJson(value: unknown, fallback = "{}") {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return fallback;
  }
}

function parseJson(value: string, errorMessage: string) {
  if (!value) return {};
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(errorMessage);
  }
}

export function AlgorithmEditorPage() {
  const { algorithmId } = useParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);
  const canEdit = Boolean(
    me?.user.is_platform_admin || me?.roles?.some((r) => r === "tenant_admin" || r === "tenant_engineer")
  );

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<AlgorithmFormValues>();
  const [kind, setKind] = useState<AlgorithmKind>("python");
  const [pythonCode, setPythonCode] = useState("");
  const [pythonParamsJson, setPythonParamsJson] = useState("");
  const [httpConfigJson, setHttpConfigJson] = useState("");
  const [workflowConfigJson, setWorkflowConfigJson] = useState("");
  const [editing, setEditing] = useState<AlgorithmDefinition | null>(null);
  const [aiModalOpen, setAiModalOpen] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiForm] = Form.useForm();

  const kindOptions = useMemo(
    () => [
      { value: "python", label: "Python" },
      { value: "http", label: "HTTP" },
      { value: "workflow", label: t("algorithms.workflow") }
    ],
    [t]
  );

  const loadEditor = async () => {
    if (!tenantReady) return;
    if (!algorithmId) {
      form.resetFields();
      form.setFieldsValue({ kind: "python", enabled: true });
      const pythonTemplate = CONFIG_TEMPLATES.python as { code: string; params: unknown };
      setKind("python");
      setPythonCode(pythonTemplate.code);
      setPythonParamsJson(prettyJson(pythonTemplate.params, "[]"));
      setHttpConfigJson(prettyJson(CONFIG_TEMPLATES.http));
      setWorkflowConfigJson(prettyJson(CONFIG_TEMPLATES.workflow));
      setEditing(null);
      return;
    }

    setLoading(true);
    try {
      const record = await getAlgorithmDefinition(algorithmId);
      setEditing(record);
      form.setFieldsValue({
        name: record.name,
        key: record.key,
        kind: record.kind,
        description: record.description ?? undefined,
        enabled: record.enabled
      });
      setKind(record.kind);
      if (record.kind === "python") {
        const code = typeof record.config?.code === "string" ? record.config.code : "";
        setPythonCode(code || String((CONFIG_TEMPLATES.python as any).code || ""));
        setPythonParamsJson(prettyJson(record.config?.params ?? [] , "[]"));
      } else if (record.kind === "http") {
        setHttpConfigJson(prettyJson({ ...(CONFIG_TEMPLATES.http as any), ...(record.config || {}) }));
      } else {
        setWorkflowConfigJson(prettyJson({ ...(CONFIG_TEMPLATES.workflow as any), ...(record.config || {}) }));
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("algorithms.saveFail"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadEditor();
  }, [tenantReady, algorithmId]);

  const handleKindChange = (nextKind: AlgorithmKind) => {
    setKind(nextKind);
    form.setFieldsValue({ kind: nextKind });
    if (nextKind === "python") {
      const template = CONFIG_TEMPLATES.python as any;
      setPythonCode(String(template.code || ""));
      setPythonParamsJson(prettyJson(template.params ?? [], "[]"));
    } else if (nextKind === "http") {
      setHttpConfigJson(prettyJson(CONFIG_TEMPLATES.http));
    } else {
      setWorkflowConfigJson(prettyJson(CONFIG_TEMPLATES.workflow));
    }
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      let config: Record<string, unknown> = {};
      if (values.kind === "python") {
        if (!pythonCode.trim()) {
          message.error(t("algorithms.codeRequired"));
          return;
        }
        if (!pythonCode.includes("def run")) {
          message.error(t("algorithms.codeInvalid"));
          return;
        }
        const params = parseJson(pythonParamsJson || "[]", t("algorithms.configInvalid"));
        config = {
          code: pythonCode,
          params: Array.isArray(params) ? params : []
        };
      } else if (values.kind === "http") {
        config = parseJson(httpConfigJson, t("algorithms.configInvalid"));
      } else {
        config = parseJson(workflowConfigJson, t("algorithms.configInvalid"));
      }

      if (editing) {
        await updateAlgorithmDefinition(editing.id, {
          name: values.name,
          key: values.key,
          kind: values.kind,
          description: values.description,
          enabled: values.enabled,
          config
        });
        message.success(t("algorithms.updated"));
      } else {
        await createAlgorithmDefinition({
          name: values.name,
          key: values.key,
          kind: values.kind,
          description: values.description,
          enabled: values.enabled,
          config
        });
        message.success(t("algorithms.created"));
      }
      navigate("/algorithms");
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err?.message || t("algorithms.saveFail"));
    } finally {
      setSaving(false);
    }
  };

  const formatJsonField = (setter: (value: string) => void, currentValue: string, fallback = "{}") => {
    try {
      const parsed = currentValue ? JSON.parse(currentValue) : {};
      setter(JSON.stringify(parsed, null, 2));
    } catch {
      setter(fallback);
    }
  };

  const handleAIGenerate = async () => {
    const values = await aiForm.validateFields();
    setAiLoading(true);
    try {
      const data = await generateAlgorithmByAI({
        requirement: values.requirement,
        field: values.field || undefined
      });
      setKind("python");
      form.setFieldsValue({ kind: "python" });
      setPythonCode(data.code || "");
      setPythonParamsJson(JSON.stringify(data.params || [], null, 2));
      setAiModalOpen(false);
      message.success(t("algorithms.aiGenerated"));
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("algorithms.aiFailed"));
    } finally {
      setAiLoading(false);
    }
  };

  if (!tenantReady) {
    return (
      <Alert type="warning" showIcon message={t("analysis.noTenant")} description={t("analysis.noTenantDesc")} />
    );
  }

  return (
    <PageShell>
      <PageHeader
        title={editing ? t("algorithms.editorTitleEdit") : t("algorithms.editorTitleCreate")}
        subtitle={t("algorithms.subtitle")}
        extra={
          <PageActions>
          <Button onClick={() => navigate("/algorithms")}>{t("algorithms.backToList")}</Button>
          <Button type="primary" onClick={handleSave} loading={saving} disabled={!canEdit}>
            {t("common.save")}
          </Button>
          </PageActions>
        }
      />

      <Card loading={loading}>
        <Form
          layout="vertical"
          form={form}
          initialValues={{ kind: "python", enabled: true }}
          onValuesChange={(changed, all) => {
            if (changed.name && !all.key) {
              form.setFieldsValue({ key: slugify(changed.name) });
            }
            if (changed.kind) {
              handleKindChange(changed.kind as AlgorithmKind);
            }
          }}
        >
          <Form.Item name="name" label={t("algorithms.name")} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="key" label={t("algorithms.key")} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="kind" label={t("algorithms.kind")} rules={[{ required: true }]}>
            <Select options={kindOptions} />
          </Form.Item>
          <Form.Item name="description" label={t("algorithms.description")}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="enabled" label={t("algorithms.enabled")} valuePropName="checked">
            <Switch />
          </Form.Item>

          {kind === "python" ? (
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <Card
                size="small"
                title={t("algorithms.code")}
                extra={
                  <Button size="small" onClick={() => setAiModalOpen(true)} disabled={!canEdit}>
                    {t("algorithms.aiGenerate")}
                  </Button>
                }
              >
                <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
                  {t("algorithms.codeHint")}
                </Typography.Paragraph>
                <CodeEditor value={pythonCode} onChange={setPythonCode} minRows={16} language="python" />
              </Card>

              <Card size="small" title={t("algorithms.paramsJson")}>
                <Space align="center" wrap style={{ marginBottom: 8 }}>
                  <Typography.Text type="secondary">{t("algorithms.configHint")}</Typography.Text>
                  <Button size="small" onClick={() => formatJsonField(setPythonParamsJson, pythonParamsJson, "[]")}
                  >
                    {t("algorithms.formatJson")}
                  </Button>
                </Space>
                <CodeEditor value={pythonParamsJson} onChange={setPythonParamsJson} minRows={10} language="json" />
              </Card>
            </Space>
          ) : null}

          {kind === "http" ? (
            <Card size="small" title={t("algorithms.httpConfig")}
            >
              <Space align="center" wrap style={{ marginBottom: 8 }}>
                <Typography.Text type="secondary">{t("algorithms.configHint")}</Typography.Text>
                <Button size="small" onClick={() => formatJsonField(setHttpConfigJson, httpConfigJson)}>
                  {t("algorithms.formatJson")}
                </Button>
              </Space>
              <CodeEditor value={httpConfigJson} onChange={setHttpConfigJson} minRows={14} language="json" />
            </Card>
          ) : null}

          {kind === "workflow" ? (
            <Card size="small" title={t("algorithms.workflowConfig")}
            >
              <Space align="center" wrap style={{ marginBottom: 8 }}>
                <Typography.Text type="secondary">{t("algorithms.configHint")}</Typography.Text>
                <Button size="small" onClick={() => formatJsonField(setWorkflowConfigJson, workflowConfigJson)}>
                  {t("algorithms.formatJson")}
                </Button>
              </Space>
              <CodeEditor value={workflowConfigJson} onChange={setWorkflowConfigJson} minRows={14} language="json" />
            </Card>
          ) : null}
        </Form>
      </Card>

      <Modal
        open={aiModalOpen}
        title={t("algorithms.aiGenerate")}
        onCancel={() => setAiModalOpen(false)}
        onOk={handleAIGenerate}
        confirmLoading={aiLoading}
        okText={t("algorithms.aiGenerate")}
      >
        <Form layout="vertical" form={aiForm}>
          <Form.Item
            name="requirement"
            label={t("algorithms.aiRequirement")}
            rules={[{ required: true, message: t("algorithms.aiRequirementHint") }]}
          >
            <Input.TextArea rows={4} placeholder={t("algorithms.aiRequirementHint")} />
          </Form.Item>
          <Form.Item name="field" label={t("algorithms.aiField")}>
            <Input placeholder="rpm / torque / pressure" />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
