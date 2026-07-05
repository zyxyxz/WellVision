import React, { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
  message
} from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { createWarehouse, listWarehouses, updateWarehouse, type DataWarehouseResponse } from "../api/warehouses";
import { listProjects, type ProjectResponse } from "../api/projects";
import { useAuth } from "../auth/AuthProvider";

type WarehouseFormValues = {
  name: string;
  description?: string;
  project_id?: string;
};

export function DataPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const tenantReady = Boolean(me?.tenant_id);

  const [warehouses, setWarehouses] = useState<DataWarehouseResponse[]>([]);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<DataWarehouseResponse | null>(null);
  const [form] = Form.useForm<WarehouseFormValues>();

  async function load() {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const [warehouseData, projectData] = await Promise.all([listWarehouses(), listProjects()]);
      setWarehouses(warehouseData);
      setProjects(projectData);
    } catch (err) {
      message.error(t("data.warehouseLoadFail"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [tenantReady]);

  const handleCreate = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        const warehouse = await updateWarehouse(editing.id, {
          name: values.name,
          description: values.description,
          project_id: values.project_id ?? null
        });
        message.success(t("data.warehouseUpdateSuccess"));
        setModalOpen(false);
        setEditing(null);
        form.resetFields();
        await load();
        navigate(`/data/${warehouse.id}`);
      } else {
        const warehouse = await createWarehouse({
          name: values.name,
          description: values.description,
          project_id: values.project_id,
          sources: []
        });
        message.success(t("data.warehouseCreateSuccess"));
        setModalOpen(false);
        form.resetFields();
        navigate(`/data/${warehouse.id}`);
      }
    } catch (err) {
      message.error(editing ? t("data.warehouseUpdateFail") : t("data.warehouseCreateFail"));
    } finally {
      setSaving(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: DataWarehouseResponse) => {
    setEditing(record);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      description: record.description ?? undefined,
      project_id: record.project_id ?? undefined
    });
    setModalOpen(true);
  };

  if (!tenantReady) {
    return (
      <Alert type="warning" showIcon message={t("data.noTenant")} description={t("data.noTenantDesc")} />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space align="center" style={{ width: "100%", justifyContent: "space-between" }} wrap>
        <Space direction="vertical" size={0}>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {t("data.warehouseListTitle")}
          </Typography.Title>
          <Typography.Text type="secondary">{t("data.warehouseSubtitle")}</Typography.Text>
        </Space>
        <Button type="primary" onClick={openCreate}>
          {t("data.warehouseCreateAction")}
        </Button>
      </Space>

      <Card>
        {warehouses.length ? (
          <Table<DataWarehouseResponse>
            rowKey="id"
            dataSource={warehouses}
            loading={loading}
            pagination={{ pageSize: 8, showSizeChanger: true }}
            columns={[
              {
                title: t("projects.title"),
                dataIndex: "project_id",
                render: (v) => projects.find((p) => p.id === v)?.name || "-"
              },
              { title: t("data.warehouseName"), dataIndex: "name" },
              {
                title: t("data.warehouseDesc"),
                dataIndex: "description",
                render: (v) => v || "-"
              },
              {
                title: t("data.created"),
                dataIndex: "created_at",
                render: (v) => new Date(v).toLocaleString()
              },
              {
                title: t("data.actions"),
                render: (_, record) => (
                  <Space>
                    <Button
                      size="small"
                      onClick={(event) => {
                        event.stopPropagation();
                        navigate(`/data/${record.id}`);
                      }}
                    >
                      {t("data.manage")}
                    </Button>
                    <Button
                      size="small"
                      onClick={(event) => {
                        event.stopPropagation();
                        openEdit(record);
                      }}
                    >
                      {t("common.edit")}
                    </Button>
                  </Space>
                )
              }
            ]}
          />
        ) : (
          <Empty description={t("data.warehouseEmpty")} />
        )}
      </Card>

      <Modal
        open={modalOpen}
        title={editing ? t("data.warehouseEditTitle") : t("data.warehouseCreateTitle")}
        onCancel={() => setModalOpen(false)}
        onOk={handleCreate}
        confirmLoading={saving}
        okText={t("common.save")}
      >
        <Form layout="vertical" form={form}>
          <Form.Item name="project_id" label={t("projects.title")}>
            <Select
              allowClear
              options={projects.map((p) => ({ value: p.id, label: `${p.name} (${p.code})` }))}
              placeholder={t("data.warehouseSelectProject")}
            />
          </Form.Item>
          <Form.Item name="name" label={t("data.warehouseName")} rules={[{ required: true }]}
          >
            <Input placeholder={t("data.warehouseNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="description" label={t("data.warehouseDesc")}>
            <Input placeholder={t("data.warehouseDescPlaceholder")} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
