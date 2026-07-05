import React, { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message
} from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { listAlgorithms, type AlgorithmInfo } from "../api/analysis";
import { deleteAlgorithmDefinition, listAlgorithmDefinitions, updateAlgorithmDefinition, type AlgorithmDefinition } from "../api/algorithms";
import { useAuth } from "../auth/AuthProvider";

export function AlgorithmsPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const tenantReady = Boolean(me?.tenant_id);
  const canEdit = Boolean(me?.user.is_platform_admin || me?.roles?.some((r) => r === "tenant_admin" || r === "tenant_engineer"));

  const [builtin, setBuiltin] = useState<AlgorithmInfo[]>([]);
  const [custom, setCustom] = useState<AlgorithmDefinition[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const [builtinData, customData] = await Promise.all([listAlgorithms(), listAlgorithmDefinitions()]);
      setBuiltin(builtinData.filter((algo) => algo.kind === "builtin"));
      setCustom(customData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [tenantReady]);

  const handleDelete = async (record: AlgorithmDefinition) => {
    try {
      await deleteAlgorithmDefinition(record.id);
      message.success(t("algorithms.deleted"));
      await load();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("algorithms.deleteFail"));
    }
  };

  const handleToggle = async (record: AlgorithmDefinition, enabled: boolean) => {
    try {
      await updateAlgorithmDefinition(record.id, { enabled });
      message.success(t("algorithms.updated"));
      await load();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || t("algorithms.saveFail"));
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
            {t("algorithms.title")}
          </Typography.Title>
          <Typography.Text type="secondary">{t("algorithms.subtitle")}</Typography.Text>
        </Space>
        <Button type="primary" onClick={() => navigate("/algorithms/new")} disabled={!canEdit}>
          {t("algorithms.create")}
        </Button>
      </Space>

      <Tabs
        items={[
          {
            key: "builtin",
            label: t("algorithms.builtin"),
            children: (
              <Card loading={loading}>
                <Table<AlgorithmInfo>
                  rowKey="id"
                  dataSource={builtin}
                  pagination={{ pageSize: 8 }}
                  columns={[
                    { title: t("algorithms.name"), dataIndex: "name" },
                    { title: t("algorithms.key"), dataIndex: "id" },
                    { title: t("algorithms.description"), dataIndex: "description" },
                    {
                      title: t("algorithms.params"),
                      render: (_, record) => (
                        <Space wrap>
                          {record.params?.length
                            ? record.params.map((p) => <Tag key={p.key}>{p.key}</Tag>)
                            : t("common.noData")}
                        </Space>
                      )
                    }
                  ]}
                />
              </Card>
            )
          },
          {
            key: "custom",
            label: t("algorithms.custom"),
            children: (
              <Card loading={loading}>
                <Table<AlgorithmDefinition>
                  rowKey="id"
                  dataSource={custom}
                  pagination={{ pageSize: 8 }}
                  columns={[
                    { title: t("algorithms.name"), dataIndex: "name" },
                    { title: t("algorithms.key"), dataIndex: "key" },
                    {
                      title: t("algorithms.kind"),
                      dataIndex: "kind",
                      render: (value) => <Tag color="blue">{value}</Tag>
                    },
                    {
                      title: t("algorithms.enabled"),
                      dataIndex: "enabled",
                      render: (value, record) => (
                        <Switch checked={value} onChange={(checked) => handleToggle(record, checked)} />
                      )
                    },
                    {
                      title: t("algorithms.updatedAt"),
                      dataIndex: "updated_at",
                      render: (v) => new Date(v).toLocaleString()
                    },
                    {
                      title: t("common.actions"),
                      render: (_, record) => (
                        <Space wrap>
                          <Button size="small" onClick={() => navigate(`/algorithms/${record.id}/edit`)} disabled={!canEdit}>
                            {t("common.edit")}
                          </Button>
                          <Button size="small" danger onClick={() => handleDelete(record)} disabled={!canEdit}>
                            {t("common.delete")}
                          </Button>
                        </Space>
                      )
                    }
                  ]}
                />
              </Card>
            )
          }
        ]}
      />

    </Space>
  );
}
