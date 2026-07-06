import React from "react";
import { Space, Typography } from "antd";

type PageShellProps = {
  children: React.ReactNode;
};

type PageHeaderProps = {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  extra?: React.ReactNode;
};

export function PageShell({ children }: PageShellProps) {
  return (
    <main className="wv-page-shell">
      <div className="wv-page-stack">{children}</div>
    </main>
  );
}

export function PageHeader({ title, subtitle, extra }: PageHeaderProps) {
  return (
    <div className="wv-page-header">
      <div className="wv-page-header-main">
        <Typography.Title level={3} className="wv-page-title">
          {title}
        </Typography.Title>
        {subtitle ? <Typography.Text className="wv-page-subtitle">{subtitle}</Typography.Text> : null}
      </div>
      {extra ? <div className="wv-page-header-extra">{extra}</div> : null}
    </div>
  );
}

export function PageActions({ children }: { children: React.ReactNode }) {
  return (
    <Space wrap align="center">
      {children}
    </Space>
  );
}
