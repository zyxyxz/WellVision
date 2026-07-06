import React, { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
} from "antd";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { listFields, type FieldSummary } from "../api/analysis";
import { listDatasets, type DatasetResponse } from "../api/ingestion";
import { listEvents, type EventResponse } from "../api/events";
import { listReports, type ReportResponse, type ReportStatus } from "../api/reports";
import { listWarehouses, type DataWarehouseResponse } from "../api/warehouses";
import { useAuth } from "../auth/AuthProvider";
import { PageActions, PageHeader, PageShell } from "../components/PageShell";

const STATUS_COLORS: Record<ReportStatus, string> = {
  draft: "default",
  in_review: "processing",
  published: "success",
  rejected: "error"
};

function formatBytes(value?: number | null) {
  if (!value) return "-";
  const mb = value / (1024 * 1024);
  if (mb < 1) return `${(value / 1024).toFixed(1)} KB`;
  return `${mb.toFixed(2)} MB`;
}

export function DashboardPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);

  const [warehouses, setWarehouses] = useState<DataWarehouseResponse[]>([]);
  const [warehouseId, setWarehouseId] = useState<string | null>(null);

  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [events, setEvents] = useState<EventResponse[]>([]);
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [fields, setFields] = useState<FieldSummary[]>([]);

  const [loading, setLoading] = useState(false);

  async function loadStatic() {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const [warehouseData, reportData] = await Promise.all([listWarehouses(), listReports()]);
      setWarehouses(warehouseData);
      setReports(reportData);
      if (!warehouseId && warehouseData.length) {
        setWarehouseId(warehouseData[0].id);
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadWarehouseScoped() {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const [datasetData, eventData, fieldData] = await Promise.all([
        listDatasets(warehouseId ? { warehouse_id: warehouseId } : undefined),
        listEvents({ warehouse_id: warehouseId ?? undefined, limit: 1000 }),
        listFields(1200, warehouseId ?? undefined)
      ]);
      setDatasets(datasetData);
      setEvents(eventData);
      setFields(fieldData.slice(0, 12));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatic();
  }, [tenantReady]);

  useEffect(() => {
    void loadWarehouseScoped();
  }, [tenantReady, warehouseId]);

  if (!tenantReady) {
    return (
      <Alert type="warning" showIcon message={t("data.noTenant")} description={t("data.noTenantDesc")} />
    );
  }

  const reportCounts = reports.reduce(
    (acc, report) => {
      acc.total += 1;
      acc[report.status] = (acc[report.status] ?? 0) + 1;
      return acc;
    },
    { total: 0, draft: 0, in_review: 0, published: 0, rejected: 0 }
  );

  const now = Date.now();
  const hours = Array.from({ length: 24 }, (_, idx) => {
    const hour = new Date(now - (23 - idx) * 3600 * 1000);
    const key = `${hour.getHours().toString().padStart(2, "0")}:00`;
    return { key, ts: hour.getTime(), count: 0 };
  });

  events.forEach((event) => {
    const ts = new Date(event.created_at).getTime();
    const diffHours = Math.floor((now - ts) / (3600 * 1000));
    if (diffHours >= 0 && diffHours < 24) {
      const bucket = hours[23 - diffHours];
      if (bucket) bucket.count += 1;
    }
  });

  const events24h = events.filter((event) => now - new Date(event.created_at).getTime() < 24 * 3600 * 1000).length;

  return (
    <PageShell>
      <PageHeader
        title={t("dashboard.title")}
        subtitle={`${t("dashboard.tenantContext")}: ${me?.tenant_id ?? "-"}`}
        extra={
          <PageActions>
          <Select
            style={{ minWidth: 240 }}
            value={warehouseId ?? "all"}
            options={[
              { value: "all", label: t("dashboard.allWarehouses") },
              ...warehouses.map((w) => ({ value: w.id, label: w.name }))
            ]}
            onChange={(value) => setWarehouseId(value === "all" ? null : value)}
          />
          <Button onClick={() => loadWarehouseScoped()}>{t("dashboard.refresh")}</Button>
          </PageActions>
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card loading={loading}>
            <Statistic title={t("dashboard.warehouseCount")} value={warehouses.length} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card loading={loading}>
            <Statistic title={t("dashboard.datasetCount")} value={datasets.length} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card loading={loading}>
            <Statistic title={t("dashboard.events24h")} value={events24h} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card loading={loading}>
            <Statistic title={t("dashboard.pendingReviews")} value={reportCounts.in_review} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title={t("dashboard.eventsTrend")} loading={loading}>
            {events.length ? (
              <div style={{ height: 260 }}>
                <ResponsiveContainer>
                  <LineChart data={hours.map((h) => ({ time: h.key, count: h.count }))}>
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="count" stroke="#1677ff" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty description={t("dashboard.noEvents")} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title={t("dashboard.topFields")} loading={loading}>
            {fields.length ? (
              <Space wrap>
                {fields.map((field) => (
                  <Tag key={field.name} color="blue">
                    {field.name} · {field.count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description={t("dashboard.noFields")} />
            )}
          </Card>
          <Card title={t("dashboard.reportStatus")} style={{ marginTop: 16 }}>
            <Space wrap>
              <Tag color={STATUS_COLORS.draft}>{t("reports.statusDraft")}: {reportCounts.draft}</Tag>
              <Tag color={STATUS_COLORS.in_review}>{t("reports.statusReview")}: {reportCounts.in_review}</Tag>
              <Tag color={STATUS_COLORS.published}>{t("reports.statusPublished")}: {reportCounts.published}</Tag>
              <Tag color={STATUS_COLORS.rejected}>{t("reports.statusRejected")}: {reportCounts.rejected}</Tag>
            </Space>
            <div style={{ marginTop: 12 }}>
              <Link to="/reports">{t("dashboard.goReports")}</Link>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card className="wv-table-card" title={t("dashboard.recentDatasets")} loading={loading}>
            {datasets.length ? (
              <Table<DatasetResponse>
                rowKey="id"
                dataSource={datasets}
                pagination={{ pageSize: 5 }}
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
                  }
                ]}
              />
            ) : (
              <Empty description={t("dashboard.noDatasets")} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card className="wv-table-card" title={t("dashboard.recentReports")} loading={loading}>
            {reports.length ? (
              <Table<ReportResponse>
                rowKey="id"
                dataSource={reports}
                pagination={{ pageSize: 5 }}
                columns={[
                  { title: t("reports.titleCol"), dataIndex: "title" },
                  {
                    title: t("reports.statusCol"),
                    dataIndex: "status",
                    render: (status: ReportStatus) => <Tag color={STATUS_COLORS[status]}>{status}</Tag>
                  },
                  {
                    title: t("reports.updatedCol"),
                    dataIndex: "updated_at",
                    render: (v) => new Date(v).toLocaleString()
                  }
                ]}
              />
            ) : (
              <Empty description={t("dashboard.noReports")} />
            )}
          </Card>
        </Col>
      </Row>
    </PageShell>
  );
}
