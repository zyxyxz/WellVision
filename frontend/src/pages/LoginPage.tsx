import React, { useState } from "react";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthProvider";

export function LoginPage() {
  const { login } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const demoEmail = import.meta.env.VITE_DEMO_EMAIL || "admin@wellvision.io";
  const demoPassword = import.meta.env.VITE_DEMO_PASSWORD || "ChangeMe123!";

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/";

  const onFinish = async (values: { email: string; password: string }) => {
    setSubmitting(true);
    setError(null);
    try {
      await login(values);
      navigate(from, { replace: true });
    } catch (err) {
      setError(t("login.error"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f5f7fb",
        padding: 16
      }}
    >
      <Card style={{ width: 380 }}>
        <Typography.Title level={3} style={{ marginBottom: 8 }}>
          {t("login.title")}
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 24 }}>
          {t("login.subtitle")}
        </Typography.Paragraph>

        {error ? <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} /> : null}

        <Form
          layout="vertical"
          onFinish={onFinish}
          requiredMark={false}
          initialValues={{ email: demoEmail, password: demoPassword }}
        >
          <Form.Item name="email" label={t("login.email")} rules={[{ required: true, message: t("login.email") }]}>
            <Input autoComplete="username" placeholder="admin@wellvision.io" />
          </Form.Item>
          <Form.Item
            name="password"
            label={t("login.password")}
            rules={[{ required: true, message: t("login.password") }, { min: 8, message: t("login.password") }]}
          >
            <Input.Password autoComplete="current-password" placeholder="••••••••" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>
            {t("login.submit")}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
