import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import { useTranslation } from "react-i18next";

import { createProject, deleteProject, listProjects, updateProject, type ProjectResponse } from "../api/projects";
import { useAuth } from "../auth/AuthProvider";

const STATUS_OPTIONS = [
  { value: "active", label: "active" },
  { value: "paused", label: "paused" },
  { value: "archived", label: "archived" }
];

type ProjectFormValues = {
  name: string;
  code?: string;
  description?: string;
  background?: string;
  status?: string;
};

function slugify(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function ProjectsPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);

  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ProjectResponse | null>(null);
  const [form] = Form.useForm<ProjectFormValues>();

  const statusOptions = useMemo(
    () => STATUS_OPTIONS.map((opt) => ({ value: opt.value, label: t(`projects.status.${opt.value}`) })),
    [t]
  );

  const load = async () => {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (err) {
      message.error(t("projects.loadFail"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [tenantReady]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ status: "active" });
    setModalOpen(true);
  };

  const openEdit = (record: ProjectResponse) => {
    setEditing(record);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      code: record.code,
      description: record.description ?? undefined,
      background: record.background ?? undefined,
      status: record.status
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateProject(editing.id, values);
        message.success(t("projects.updated"));
      } else {
        await createProject(values);
        message.success(t("projects.created"));
      }
      setModalOpen(false);
      await load();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("projects.saveFail"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (record: ProjectResponse) => {
    try {
      await deleteProject(record.id);
      message.success(t("projects.deleted"));
      await load();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("projects.deleteFail"));
    }
  };

  if (!tenantReady) {
    return (
      <Alert type="warning" showIcon message={t("analysis.noTenant")} description={t("analysis.noTenantDesc")} />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space align="center" style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Space direction="vertical" size={0}>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {t("projects.title")}
          </Typography.Title>
          <Typography.Text type="secondary">{t("projects.subtitle")}</Typography.Text>
        </Space>
        <Button type="primary" onClick={openCreate}>
          {t("projects.create")}
        </Button>
      </Space>

      <Card>
        <Table<ProjectResponse>
          rowKey="id"
          dataSource={projects}
          loading={loading}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: t("projects.name"), dataIndex: "name" },
            { title: t("projects.code"), dataIndex: "code", render: (v) => <Tag>{v}</Tag> },
            { title: t("projects.status.label"), dataIndex: "status", render: (v) => <Tag>{v}</Tag> },
            {
              title: t("projects.description"),
              dataIndex: "description",
              render: (v) => v || "-"
            },
            {
              title: t("projects.updatedAt"),
              dataIndex: "updated_at",
              render: (v) => new Date(v).toLocaleString()
            },
            {
              title: t("common.actions"),
              render: (_, record) => (
                <Space wrap>
                  <Button size="small" onClick={() => openEdit(record)}>
                    {t("common.edit")}
                  </Button>
                  <Button size="small" danger onClick={() => handleDelete(record)}>
                    {t("common.delete")}
                  </Button>
                </Space>
              )
            }
          ]}
        />
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? t("projects.editTitle") : t("projects.createTitle")}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        okText={t("common.save")}
      >
        <Form
          layout="vertical"
          form={form}
          onValuesChange={(changed, all) => {
            if (changed.name && !all.code) {
              form.setFieldsValue({ code: slugify(changed.name) });
            }
          }}
        >
          <Form.Item name="name" label={t("projects.name")} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="code" label={t("projects.code")} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="status" label={t("projects.status.label")}>
            <Select options={statusOptions} />
          </Form.Item>
          <Form.Item name="description" label={t("projects.description")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="background" label={t("projects.background")}>
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
