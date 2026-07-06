import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import { useTranslation } from "react-i18next";

import {
  approveReport,
  createReport,
  listReports,
  rejectReport,
  submitReport,
  type ReportResponse,
  type ReportStatus,
  updateReport
} from "../api/reports";
import { getApiErrorMessage } from "../api/errors";
import { useAuth } from "../auth/AuthProvider";

type ReportFormValues = {
  title: string;
  content_markdown: string;
};

const STATUS_COLORS: Record<ReportStatus, string> = {
  draft: "default",
  in_review: "processing",
  published: "success",
  rejected: "error"
};

export function ReportsPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const tenantReady = Boolean(me?.tenant_id);
  const roles = me?.roles ?? [];
  const canEdit = me?.user.is_platform_admin || roles.includes("tenant_admin") || roles.includes("tenant_engineer");
  const canReview = me?.user.is_platform_admin || roles.includes("tenant_admin") || roles.includes("tenant_reviewer");

  const [statusFilter, setStatusFilter] = useState<ReportStatus | "all">("all");
  const [reports, setReports] = useState<ReportResponse[]>([]);
  const [loading, setLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ReportResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<ReportFormValues>();

  const statusLabels: Record<ReportStatus, string> = {
    draft: t("reports.statusDraft"),
    in_review: t("reports.statusReview"),
    published: t("reports.statusPublished"),
    rejected: t("reports.statusRejected")
  };

  const reviewCounts = useMemo(() => {
    const counts: Record<string, number> = { all: reports.length };
    for (const r of reports) counts[r.status] = (counts[r.status] ?? 0) + 1;
    return counts;
  }, [reports]);

  async function load(nextFilter: ReportStatus | "all" = statusFilter) {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const data = await listReports(nextFilter === "all" ? undefined : nextFilter);
      setReports(data);
    } catch (err) {
      message.error(t("reports.loadFail"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load("all");
  }, [tenantReady]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ title: "", content_markdown: "" });
    setModalOpen(true);
  };

  const openEdit = (report: ReportResponse) => {
    setEditing(report);
    form.setFieldsValue({ title: report.title, content_markdown: report.content_markdown });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updateReport(editing.id, values);
        message.success(t("reports.updated"));
      } else {
        await createReport(values);
        message.success(t("reports.created"));
      }
      setModalOpen(false);
      await load(statusFilter);
    } catch (err) {
      message.error(getApiErrorMessage(err, t("reports.saveFail")));
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async (report: ReportResponse) => {
    try {
      await submitReport(report.id);
      message.success(t("reports.submitted"));
      await load(statusFilter);
    } catch (err) {
      message.error(getApiErrorMessage(err, t("reports.submitFail")));
    }
  };

  const handleApprove = async (report: ReportResponse) => {
    try {
      await approveReport(report.id);
      message.success(t("reports.approved"));
      await load(statusFilter);
    } catch (err) {
      message.error(getApiErrorMessage(err, t("reports.approveFail")));
    }
  };

  const handleReject = async (report: ReportResponse) => {
    let comment = "";
    Modal.confirm({
      title: t("reports.rejectTitle"),
      content: (
        <Input.TextArea
          rows={4}
          placeholder={t("reports.rejectPlaceholder")}
          onChange={(e) => {
            comment = e.target.value;
          }}
        />
      ),
      onOk: async () => {
        try {
          await rejectReport(report.id, comment || undefined);
          message.success(t("reports.rejected"));
          await load(statusFilter);
        } catch (err) {
          message.error(getApiErrorMessage(err, t("reports.rejectFail")));
        }
      }
    });
  };

  if (!tenantReady) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("reports.noTenant")}
        description={t("reports.noTenantDesc")}
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t("reports.title")}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t("reports.subtitle")}
      </Typography.Paragraph>

      <Card size="small">
        <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
          <Segmented
            value={statusFilter}
            onChange={(value) => {
              const next = value as ReportStatus | "all";
              setStatusFilter(next);
              void load(next);
            }}
            options={[
              { label: `${t("reports.statusAll")} (${reviewCounts.all ?? 0})`, value: "all" },
              { label: `${t("reports.statusDraft")} (${reviewCounts.draft ?? 0})`, value: "draft" },
              { label: `${t("reports.statusReview")} (${reviewCounts.in_review ?? 0})`, value: "in_review" },
              { label: `${t("reports.statusPublished")} (${reviewCounts.published ?? 0})`, value: "published" },
              { label: `${t("reports.statusRejected")} (${reviewCounts.rejected ?? 0})`, value: "rejected" }
            ]}
          />

          <Button type="primary" onClick={openCreate} disabled={!canEdit}>
            {t("reports.newDraft")}
          </Button>
        </Space>
      </Card>

      <Card title={t("reports.list")} loading={loading}>
        <Table<ReportResponse>
          rowKey="id"
          dataSource={reports}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: t("reports.titleCol"), dataIndex: "title" },
            {
              title: t("reports.statusCol"),
              dataIndex: "status",
              render: (status: ReportStatus) => <Tag color={STATUS_COLORS[status]}>{statusLabels[status]}</Tag>
            },
            {
              title: t("reports.updatedCol"),
              dataIndex: "updated_at",
              render: (v) => new Date(v).toLocaleString()
            },
            {
              title: t("reports.reviewCommentCol"),
              dataIndex: "review_comment",
              render: (v) => v || "-"
            },
            {
              title: t("reports.sourceCol"),
              dataIndex: "summary_json",
              render: (summary) => (summary?.source ? <Tag>{String(summary.source)}</Tag> : "-")
            },
            {
              title: t("reports.actionsCol"),
              render: (_, record) => {
                const actions: React.ReactNode[] = [];

                if (canEdit && (record.status === "draft" || record.status === "rejected")) {
                  actions.push(
                    <Button key="edit" size="small" onClick={() => openEdit(record)}>
                      {t("reports.edit")}
                    </Button>
                  );
                  actions.push(
                    <Button key="submit" size="small" type="primary" onClick={() => handleSubmit(record)}>
                      {t("reports.submit")}
                    </Button>
                  );
                }

                if (canReview && record.status === "in_review") {
                  actions.push(
                    <Button key="approve" size="small" type="primary" onClick={() => handleApprove(record)}>
                      {t("reports.approve")}
                    </Button>
                  );
                  actions.push(
                    <Button key="reject" size="small" danger onClick={() => handleReject(record)}>
                      {t("reports.reject")}
                    </Button>
                  );
                }

                if (!actions.length) {
                  return <Typography.Text type="secondary">{t("reports.noAction")}</Typography.Text>;
                }

                return <Space wrap>{actions}</Space>;
              }
            }
          ]}
        />
      </Card>

      <Modal
        title={editing ? t("reports.modalEdit") : t("reports.modalCreate")}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        okText={t("common.save")}
      >
        <Form layout="vertical" form={form}>
          <Form.Item name="title" label={t("reports.modalTitle")} rules={[{ required: true, min: 3 }]}>
            <Input placeholder={t("reports.titlePlaceholder")} />
          </Form.Item>
          <Form.Item name="content_markdown" label={t("reports.modalContent")} rules={[{ required: true }]}>
            <Input.TextArea rows={10} placeholder="# Summary\n- Key observations..." />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
