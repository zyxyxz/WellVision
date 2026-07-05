import React, { useEffect, useState } from "react";
import { Alert, Button, Card, Form, Input, Space, Table, Tag, Typography, message } from "antd";
import { useTranslation } from "react-i18next";

import { ingestEvent, listEvents } from "../api/events";
import type { EventResponse } from "../api/events";
import { useAuth } from "../auth/AuthProvider";

export function StreamingPage() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const [events, setEvents] = useState<EventResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<{ source: string; topic?: string; payload: string }>();

  const tenantReady = Boolean(me?.tenant_id);

  async function load() {
    if (!tenantReady) return;
    setLoading(true);
    try {
      const data = await listEvents();
      setEvents(data);
    } catch (err) {
      message.error(t("streaming.loadFail"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [tenantReady]);

  const onFinish = async (values: { source: string; topic?: string; payload: string }) => {
    if (!tenantReady) return;
    setSubmitting(true);
    try {
      const parsed = JSON.parse(values.payload);
      await ingestEvent({ source: values.source || "http", topic: values.topic, payload: parsed });
      message.success(t("streaming.submitSuccess"));
      form.resetFields(["payload", "topic"]);
      await load();
    } catch (err) {
      message.error(t("streaming.submitFail"));
    } finally {
      setSubmitting(false);
    }
  };

  if (!tenantReady) {
    return (
      <Alert
        type="warning"
        showIcon
        message={t("streaming.noTenant")}
        description={t("streaming.noTenantDesc")}
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>
        {t("streaming.title")}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t("streaming.subtitle")}
      </Typography.Paragraph>

      <Card title={t("streaming.ingestTitle")}>
        <Form layout="vertical" form={form} onFinish={onFinish} initialValues={{ source: "http" }}>
          <Form.Item name="source" label={t("streaming.source")} rules={[{ required: true }]}>
            <Input placeholder="http / mqtt / edge-gateway" />
          </Form.Item>
          <Form.Item name="topic" label={t("streaming.topic")}>
            <Input placeholder="rig/alpha/torque" />
          </Form.Item>
          <Form.Item
            name="payload"
            label={t("streaming.payload")}
            rules={[{ required: true, message: t("streaming.payloadError") }]}
          >
            <Input.TextArea rows={6} placeholder='{"timestamp":"2026-01-27T15:30:00Z","wob":12.3}' />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting}>
            {t("streaming.submit")}
          </Button>
        </Form>
      </Card>

      <Card title={t("streaming.recent")} loading={loading}>
        <Table<EventResponse>
          rowKey="id"
          dataSource={events}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: t("streaming.tableCreated"), dataIndex: "created_at", render: (v) => new Date(v).toLocaleString() },
            { title: t("streaming.tableSource"), dataIndex: "source", render: (v) => <Tag>{v}</Tag> },
            { title: t("streaming.tableTopic"), dataIndex: "topic", render: (v) => v ?? "-" },
            {
              title: t("streaming.tablePayload"),
              dataIndex: "payload",
              render: (payload) => (
                <Typography.Text code style={{ maxWidth: 420 }} ellipsis>
                  {JSON.stringify(payload)}
                </Typography.Text>
              )
            }
          ]}
        />
      </Card>
    </Space>
  );
}
