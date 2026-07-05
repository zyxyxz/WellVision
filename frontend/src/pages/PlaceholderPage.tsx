import React from "react";
import { Card, Typography } from "antd";
import { useTranslation } from "react-i18next";

export function PlaceholderPage({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <Card>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        {title}
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        {t("placeholder.subtitle")}
      </Typography.Paragraph>
    </Card>
  );
}
