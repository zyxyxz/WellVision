import React, { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Input, Modal, Space, Table, Tag, Typography, message } from "antd";
import { useTranslation } from "react-i18next";

import { approveReport, listReports, rejectReport, type ReportResponse } from "../api/reports";
import { getApiErrorMessage } from "../api/errors";
import { useAuth } from "../auth/AuthProvider";

export function ReviewPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);
  const roles = me?.roles ?? [];
  const canReview = Boolean(
    me?.user.is_platform_admin || roles.includes("tenant_admin") || roles.includes("tenant_reviewer")
  );

  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeReport, setActiveReport] = useState<ReportResponse | null>(null);

  const pendingCount = useMemo(() => reports.length, [reports]);

  async function load() {
    if (!tenantReady || !canReview) return;
    setLoading(true);
    try {
      setReports(await listReports("in_review"));
    } catch (error) {
      message.error(getApiErrorMessage(error, t("review.loadFail")));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [tenantReady, canReview]);

  const handleApprove = async (report: ReportResponse) => {
    try {
      await approveReport(report.id);
      message.success(t("review.approved"));
      if (activeReport?.id === report.id) setActiveReport(null);
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error, t("review.approveFail")));
    }
  };

  const handleReject = async (report: ReportResponse) => {
    let comment = "";
    Modal.confirm({
      title: t("review.rejectTitle"),
      content: (
        <Input.TextArea
          rows={4}
          placeholder={t("review.rejectPlaceholder")}
          onChange={(event) => {
            comment = event.target.value;
          }}
        />
      ),
      okText: t("review.reject"),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await rejectReport(report.id, comment || undefined);
          message.success(t("review.rejected"));
          if (activeReport?.id === report.id) setActiveReport(null);
          await load();
        } catch (error) {
          message.error(getApiErrorMessage(error, t("review.rejectFail")));
          throw error;
        }
      }
    });
  };

  if (!tenantReady) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("review.noTenant")}
        description={t("review.noTenantDesc")}
      />
    );
  }

  if (!canReview) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("review.noPermission")}
        description={t("review.noPermissionDesc")}
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space style={{ width: "100%", justifyContent: "space-between" }} align="start" wrap>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {t("review.title")}
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            {t("review.subtitle")}
          </Typography.Paragraph>
        </div>
        <Button onClick={load} loading={loading}>
          {t("review.refresh")}
        </Button>
      </Space>

      <Card size="small">
        <Space>
          <Typography.Text strong>{t("review.pending")}</Typography.Text>
          <Tag color={pendingCount ? "processing" : "success"}>{pendingCount}</Tag>
        </Space>
      </Card>

      <Card title={t("review.queue")} loading={loading}>
        <Table<ReportResponse>
          rowKey="id"
          dataSource={reports}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: t("review.titleCol"), dataIndex: "title" },
            {
              title: t("review.sourceCol"),
              dataIndex: "summary_json",
              render: (summary) => (summary?.source ? <Tag>{String(summary.source)}</Tag> : "-")
            },
            {
              title: t("review.submittedCol"),
              dataIndex: "updated_at",
              render: (value: string) => new Date(value).toLocaleString()
            },
            {
              title: t("review.actionsCol"),
              render: (_, record) => (
                <Space wrap>
                  <Button size="small" onClick={() => setActiveReport(record)}>
                    {t("review.view")}
                  </Button>
                  <Button size="small" type="primary" onClick={() => handleApprove(record)}>
                    {t("review.approve")}
                  </Button>
                  <Button size="small" danger onClick={() => handleReject(record)}>
                    {t("review.reject")}
                  </Button>
                </Space>
              )
            }
          ]}
        />
      </Card>

      <Modal
        title={activeReport?.title}
        open={Boolean(activeReport)}
        onCancel={() => setActiveReport(null)}
        footer={
          activeReport ? (
            <Space>
              <Button onClick={() => setActiveReport(null)}>{t("common.cancel")}</Button>
              <Button danger onClick={() => handleReject(activeReport)}>
                {t("review.reject")}
              </Button>
              <Button type="primary" onClick={() => handleApprove(activeReport)}>
                {t("review.approve")}
              </Button>
            </Space>
          ) : null
        }
        width={860}
      >
        <Typography.Paragraph type="secondary">
          {activeReport ? new Date(activeReport.updated_at).toLocaleString() : ""}
        </Typography.Paragraph>
        <pre
          style={{
            margin: 0,
            padding: 16,
            maxHeight: "60vh",
            overflow: "auto",
            background: "#f6f8fa",
            border: "1px solid #e5e7eb",
            borderRadius: 6,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word"
          }}
        >
          {activeReport?.content_markdown || ""}
        </pre>
      </Modal>
    </Space>
  );
}
