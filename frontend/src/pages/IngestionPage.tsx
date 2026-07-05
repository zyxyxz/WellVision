import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Space, Table, Tag, Typography, Upload, message } from "antd";
import type { UploadProps } from "antd";
import { useTranslation } from "react-i18next";

import { listDatasets, uploadDataset } from "../api/ingestion";
import type { DatasetResponse } from "../api/ingestion";
import { useAuth } from "../auth/AuthProvider";

function formatBytes(value?: number | null) {
  if (!value) return "-";
  const mb = value / (1024 * 1024);
  if (mb < 1) return `${(value / 1024).toFixed(1)} KB`;
  return `${mb.toFixed(2)} MB`;
}

export function IngestionPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const tenantReady = Boolean(me?.tenant_id);

  const canUpload = useMemo(() => {
    const roles = me?.roles ?? [];
    return roles.includes("tenant_admin") || roles.includes("tenant_engineer");
  }, [me?.roles]);

  async function load() {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const data = await listDatasets();
      setDatasets(data);
    } catch (err) {
      message.error(t("ingestion.loadFail"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [tenantReady]);

  const uploadProps: UploadProps = {
    accept: ".csv,.parquet",
    maxCount: 1,
    showUploadList: false,
    customRequest: async (options) => {
      const file = options.file as File;
      setUploading(true);
      try {
        await uploadDataset(file);
        message.success(t("ingestion.uploadSuccess"));
        options.onSuccess?.({}, file);
        await load();
      } catch (error) {
        message.error(t("ingestion.uploadFail"));
        options.onError?.(error as Error);
      } finally {
        setUploading(false);
      }
    }
  };

  if (!tenantReady) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("data.noTenant")}
        description={t("data.noTenantDesc")}
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t("ingestion.title")}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t("ingestion.subtitle")}
      </Typography.Paragraph>

      <Card>
        {canUpload ? (
          <Upload {...uploadProps}>
            <Button type="primary" loading={uploading}>
              {t("ingestion.upload")}
            </Button>
          </Upload>
        ) : (
          <Alert
            type="info"
            showIcon
            message={t("ingestion.noPermission")}
            description={t("ingestion.needRoles")}
          />
        )}
      </Card>

      <Card title={t("ingestion.datasetsTitle")} loading={loading}>
        <Table<DatasetResponse>
          rowKey="id"
          dataSource={datasets}
          pagination={{ pageSize: 8 }}
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
                <Typography.Text code style={{ maxWidth: 320 }} ellipsis>
                  {v}
                </Typography.Text>
              )
            }
          ]}
        />
      </Card>
    </Space>
  );
}
