import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import { useTranslation } from "react-i18next";

import {
  assignMembership,
  createTenant,
  createUser,
  listAdminChatMessages,
  listAdminChatSessions,
  listTenants,
  listUsers
} from "../api/admin";
import type { AdminChatMessage, AdminChatSession, TenantResponse, UserResponse } from "../api/admin";
import { getSystemSetting, upsertSystemSetting } from "../api/systemSettings";
import { useAuth } from "../auth/AuthProvider";
import { CodeEditor } from "../components/CodeEditor";

const ROLE_OPTIONS = [
  { label: "tenant_admin", value: "tenant_admin" },
  { label: "tenant_engineer", value: "tenant_engineer" },
  { label: "tenant_reviewer", value: "tenant_reviewer" },
  { label: "tenant_viewer", value: "tenant_viewer" }
];

const AI_PROVIDER_OPTIONS = [
  { label: "OpenAI", value: "openai" },
  { label: "Qwen (阿里千问)", value: "qwen" },
  { label: "DeepSeek", value: "deepseek" },
  { label: "Kimi (Moonshot)", value: "kimi" }
];

const AI_PROVIDER_DEFAULTS: Record<string, { base_url?: string }> = {
  qwen: { base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  deepseek: { base_url: "https://api.deepseek.com/v1" },
  kimi: { base_url: "https://api.moonshot.cn/v1" }
};

type MembershipFormValues = {
  user_id: string;
  tenant_id: string;
  role: string;
};

type AIConfigFormValues = {
  provider: "openai" | "qwen" | "deepseek" | "kimi";
  api_key?: string;
  base_url?: string;
  model?: string;
  temperature?: number;
  max_output_tokens?: number;
  timeout_seconds?: number;
  enabled?: boolean;
};

export function AdminPage() {
  const { me, refreshMe } = useAuth();
  const { t } = useTranslation();
  const [tenants, setTenants] = useState<TenantResponse[]>([]);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [generalConfig, setGeneralConfig] = useState("{}");
  const [storedAIConfig, setStoredAIConfig] = useState<Record<string, unknown>>({});
  const [chatSessions, setChatSessions] = useState<AdminChatSession[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<AdminChatMessage[]>([]);
  const [chatModalOpen, setChatModalOpen] = useState(false);
  const [chatSessionActive, setChatSessionActive] = useState<AdminChatSession | null>(null);

  const [tenantModalOpen, setTenantModalOpen] = useState(false);
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [membershipModalOpen, setMembershipModalOpen] = useState(false);

  const [tenantForm] = Form.useForm();
  const [userForm] = Form.useForm();
  const [membershipForm] = Form.useForm<MembershipFormValues>();
  const [aiForm] = Form.useForm<AIConfigFormValues>();

  const isPlatformAdmin = Boolean(me?.user.is_platform_admin);

  const tenantOptions = useMemo(
    () => tenants.map((t) => ({ label: `${t.name} (${t.slug})`, value: t.id })),
    [tenants]
  );
  const userOptions = useMemo(
    () => users.map((u) => ({ label: u.email, value: u.id })),
    [users]
  );

  async function loadAll() {
    if (!isPlatformAdmin) return;
    setLoading(true);
    try {
      const [tenantData, userData] = await Promise.all([listTenants(), listUsers()]);
      setTenants(tenantData);
      setUsers(userData);
    } finally {
      setLoading(false);
    }
  }

  async function loadChatSessions() {
    if (!isPlatformAdmin) return;
    setChatLoading(true);
    try {
      const sessions = await listAdminChatSessions({ limit: 100 });
      setChatSessions(sessions);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("admin.chatLoadFail"));
    } finally {
      setChatLoading(false);
    }
  }

  async function loadSystemSettings() {
    if (!isPlatformAdmin) return;
    setSettingsLoading(true);
    try {
      const aiSetting = await getSystemSetting("ai_config").catch(() => null);
      const generalSetting = await getSystemSetting("system_general").catch(() => null);

      const aiValue = (aiSetting?.value as Record<string, unknown>) || {};
      setStoredAIConfig(aiValue);
      aiForm.setFieldsValue({
        provider: (aiValue.provider as AIConfigFormValues["provider"]) || "openai",
        api_key: (aiValue.api_key as string) || "",
        base_url: (aiValue.base_url as string) || "",
        model: (aiValue.model as string) || "",
        temperature: typeof aiValue.temperature === "number" ? aiValue.temperature : undefined,
        max_output_tokens: typeof aiValue.max_output_tokens === "number" ? aiValue.max_output_tokens : undefined,
        timeout_seconds: typeof aiValue.timeout_seconds === "number" ? aiValue.timeout_seconds : undefined,
        enabled: aiValue.enabled !== false
      });

      const generalValue = (generalSetting?.value as Record<string, unknown>) || {};
      setGeneralConfig(JSON.stringify(generalValue, null, 2));
    } finally {
      setSettingsLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
    void loadSystemSettings();
    void loadChatSessions();
  }, [isPlatformAdmin]);

  const handleCreateTenant = async () => {
    const values = await tenantForm.validateFields();
    await createTenant(values);
    message.success(t("admin.tenantCreated"));
    setTenantModalOpen(false);
    tenantForm.resetFields();
    await loadAll();
    await refreshMe();
  };

  const handleCreateUser = async () => {
    const values = await userForm.validateFields();
    await createUser(values);
    message.success(t("admin.userCreated"));
    setUserModalOpen(false);
    userForm.resetFields();
    await loadAll();
  };

  const handleAssignMembership = async () => {
    const values = await membershipForm.validateFields();
    await assignMembership(values);
    message.success(t("admin.membershipUpdated"));
    setMembershipModalOpen(false);
    membershipForm.resetFields();
    await loadAll();
  };

  const handleSaveAIConfig = async () => {
    try {
      const values = await aiForm.validateFields();
      const next: Record<string, unknown> = {
        provider: values.provider,
        base_url: values.base_url || undefined,
        model: values.model || undefined,
        temperature: values.temperature ?? undefined,
        max_output_tokens: values.max_output_tokens ?? undefined,
        timeout_seconds: values.timeout_seconds ?? undefined,
        enabled: values.enabled !== false
      };
      const incomingKey = values.api_key?.trim();
      if (incomingKey) {
        next.api_key = incomingKey;
      } else if (storedAIConfig.api_key) {
        next.api_key = storedAIConfig.api_key;
      }
      await upsertSystemSetting("ai_config", next);
      message.success(t("admin.systemSaved"));
      setStoredAIConfig(next);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("admin.systemConfigInvalid"));
    }
  };

  const handleSaveGeneralConfig = async () => {
    try {
      const parsed = generalConfig ? JSON.parse(generalConfig) : {};
      await upsertSystemSetting("system_general", parsed);
      message.success(t("admin.systemSaved"));
    } catch (err) {
      message.error(t("admin.systemConfigInvalid"));
    }
  };

  const openChatSession = async (session: AdminChatSession) => {
    setChatSessionActive(session);
    setChatModalOpen(true);
    try {
      const messages = await listAdminChatMessages(session.id);
      setChatMessages(messages);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("admin.chatLoadFail"));
    }
  };

  if (!isPlatformAdmin) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("admin.needAdmin")}
        description={t("admin.needAdminDesc")}
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row justify="space-between" align="middle">
        <Col>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {t("admin.title")}
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {t("admin.subtitle")}
          </Typography.Paragraph>
        </Col>
        <Col>
          <Space>
            <Button onClick={() => setTenantModalOpen(true)}>{t("admin.createTenant")}</Button>
            <Button onClick={() => setUserModalOpen(true)}>{t("admin.createUser")}</Button>
            <Button type="primary" onClick={() => setMembershipModalOpen(true)}>
              {t("admin.assignMembership")}
            </Button>
          </Space>
        </Col>
      </Row>

      <Card title={t("admin.tenantsTitle")} loading={loading}>
        <Table<TenantResponse>
          rowKey="id"
          dataSource={tenants}
          pagination={{ pageSize: 5 }}
          columns={[
            { title: t("admin.tableName"), dataIndex: "name" },
            { title: t("admin.tableSlug"), dataIndex: "slug", render: (slug) => <Tag>{slug}</Tag> },
            {
              title: t("admin.tableTenantId"),
              dataIndex: "id",
              render: (id) => <Typography.Text code>{id.slice(0, 8)}...</Typography.Text>
            }
          ]}
        />
      </Card>

      <Card title={t("admin.usersTitle")} loading={loading}>
        <Table<UserResponse>
          rowKey="id"
          dataSource={users}
          pagination={{ pageSize: 5 }}
          columns={[
            { title: t("admin.tableEmail"), dataIndex: "email" },
            { title: t("admin.tableFullName"), dataIndex: "full_name" },
            {
              title: t("admin.tableStatus"),
              render: (_, record) =>
                record.is_active ? <Tag color="green">{t("admin.statusActive")}</Tag> : <Tag>{t("admin.statusInactive")}</Tag>
            },
            {
              title: t("admin.tablePlatformAdmin"),
              render: (_, record) =>
                record.is_platform_admin ? (
                  <Tag color="gold">{t("admin.platformAdminYes")}</Tag>
                ) : (
                  <Tag>{t("admin.platformAdminNo")}</Tag>
                )
            }
          ]}
        />
      </Card>

      <Divider />

      <Card title={t("admin.systemTitle")} loading={settingsLoading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card size="small" title={t("admin.aiConfigTitle")}>
              <Form
                layout="vertical"
                form={aiForm}
                onValuesChange={(changed) => {
                  if (changed.provider) {
                    const preset = AI_PROVIDER_DEFAULTS[changed.provider as string];
                    const currentBase = aiForm.getFieldValue("base_url");
                    if (!currentBase && preset?.base_url) {
                      aiForm.setFieldsValue({ base_url: preset.base_url });
                    }
                  }
                }}
              >
                <Form.Item name="provider" label={t("admin.aiProvider")} rules={[{ required: true }]}>
                  <Select options={AI_PROVIDER_OPTIONS} />
                </Form.Item>
                <Form.Item name="enabled" label={t("admin.aiEnabled")} valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name="api_key" label={t("admin.aiApiKey")} extra={t("admin.aiApiKeyHint")}>
                  <Input.Password placeholder={t("admin.aiApiKeyHint")} />
                </Form.Item>
                <Form.Item name="base_url" label={t("admin.aiBaseUrl")}>
                  <Input placeholder="https://api.openai.com/v1" />
                </Form.Item>
                <Form.Item name="model" label={t("admin.aiModel")}>
                  <Input placeholder="gpt-4o-mini / qwen-plus / deepseek-chat / moonshot-v1-8k" />
                </Form.Item>
                <Form.Item name="temperature" label={t("admin.aiTemperature")}>
                  <InputNumber min={0} max={2} step={0.1} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="max_output_tokens" label={t("admin.aiMaxTokens")}>
                  <InputNumber min={64} max={8000} step={64} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="timeout_seconds" label={t("admin.aiTimeout")}>
                  <InputNumber min={5} max={120} step={1} style={{ width: "100%" }} />
                </Form.Item>
                <Space>
                  <Button type="primary" onClick={handleSaveAIConfig}>
                    {t("common.save")}
                  </Button>
                </Space>
              </Form>
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card size="small" title={t("admin.generalConfigTitle")}>
              <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
                {t("admin.generalConfigHint")}
              </Typography.Paragraph>
              <CodeEditor value={generalConfig} onChange={setGeneralConfig} minRows={16} />
              <Space style={{ marginTop: 12 }}>
                <Button type="primary" onClick={handleSaveGeneralConfig}>
                  {t("common.save")}
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>
      </Card>

      <Card
        title={t("admin.chatHistoryTitle")}
        extra={
          <Button size="small" onClick={loadChatSessions} loading={chatLoading}>
            {t("admin.chatRefresh")}
          </Button>
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          {t("admin.chatHistoryDesc")}
        </Typography.Paragraph>
        <Table<AdminChatSession>
          rowKey="id"
          dataSource={chatSessions}
          loading={chatLoading}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: t("admin.chatSessionTitleCol"), dataIndex: "title", render: (v) => v || "-" },
            {
              title: t("admin.chatSessionTenant"),
              dataIndex: "tenant_id",
              render: (v) => <Typography.Text code>{v?.slice(0, 8)}...</Typography.Text>
            },
            {
              title: t("admin.chatSessionUser"),
              dataIndex: "user_id",
              render: (v) => (v ? <Typography.Text code>{v.slice(0, 8)}...</Typography.Text> : "-")
            },
            {
              title: t("admin.chatSessionWarehouse"),
              dataIndex: "warehouse_id",
              render: (v) => (v ? <Typography.Text code>{v.slice(0, 8)}...</Typography.Text> : "-")
            },
            {
              title: t("admin.chatSessionUpdated"),
              dataIndex: "updated_at",
              render: (v) => new Date(v).toLocaleString()
            },
            {
              title: t("admin.chatSessionActions"),
              render: (_, record) => (
                <Button size="small" onClick={() => openChatSession(record)}>
                  {t("admin.chatView")}
                </Button>
              )
            }
          ]}
        />
      </Card>

      <Modal
        title={t("admin.tenantModalTitle")}
        open={tenantModalOpen}
        onCancel={() => setTenantModalOpen(false)}
        onOk={handleCreateTenant}
        okText={t("common.create")}
      >
        <Form layout="vertical" form={tenantForm}>
          <Form.Item name="name" label={t("admin.formTenantName")} rules={[{ required: true }]}>
            <Input placeholder="WellVision Oilfield A" />
          </Form.Item>
          <Form.Item
            name="slug"
            label={t("admin.formTenantSlug")}
            rules={[
              { required: true },
              { pattern: /^[a-z0-9-]+$/, message: t("admin.formTenantSlugRule") }
            ]}
          >
            <Input placeholder="oilfield-a" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("admin.userModalTitle")}
        open={userModalOpen}
        onCancel={() => setUserModalOpen(false)}
        onOk={handleCreateUser}
        okText={t("common.create")}
      >
        <Form layout="vertical" form={userForm}>
          <Form.Item name="email" label={t("admin.formEmail")} rules={[{ required: true, type: "email" }]}>
            <Input placeholder="engineer@client.com" />
          </Form.Item>
          <Form.Item name="full_name" label={t("admin.formFullName")}>
            <Input placeholder={t("admin.formFullNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="password" label={t("admin.formPassword")} rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder={t("admin.formPasswordHint")} />
          </Form.Item>
          <Form.Item name="is_platform_admin" label={t("admin.formIsPlatformAdmin")} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("admin.membershipModalTitle")}
        open={membershipModalOpen}
        onCancel={() => setMembershipModalOpen(false)}
        onOk={handleAssignMembership}
        okText={t("common.save")}
      >
        <Form layout="vertical" form={membershipForm}>
          <Form.Item name="user_id" label={t("admin.formUser")} rules={[{ required: true }]}>
            <Select showSearch options={userOptions} placeholder={t("admin.formUser")} />
          </Form.Item>
          <Form.Item name="tenant_id" label={t("admin.formTenant")} rules={[{ required: true }]}>
            <Select showSearch options={tenantOptions} placeholder={t("admin.formTenant")} />
          </Form.Item>
          <Form.Item name="role" label={t("admin.formRole")} rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} placeholder={t("admin.formRole")} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t("admin.chatMessagesTitle")}
        open={chatModalOpen}
        onCancel={() => setChatModalOpen(false)}
        footer={null}
        width={720}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Typography.Text type="secondary">
            {chatSessionActive?.title || "-"} · {chatSessionActive?.id}
          </Typography.Text>
          {chatMessages.length ? (
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              {chatMessages.map((msg) => (
                <div key={msg.id}>
                  <Tag color={msg.role === "user" ? "blue" : "green"}>{msg.role}</Tag>
                  <Typography.Paragraph style={{ margin: "4px 0 0 0", whiteSpace: "pre-wrap" }}>
                    {msg.content}
                  </Typography.Paragraph>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(msg.created_at).toLocaleString()}
                  </Typography.Text>
                </div>
              ))}
            </Space>
          ) : (
            <Typography.Text type="secondary">{t("admin.chatMessagesEmpty")}</Typography.Text>
          )}
        </Space>
      </Modal>

      <Divider />
      <Typography.Paragraph type="secondary">
        {t("admin.tip")}
      </Typography.Paragraph>
    </Space>
  );
}
