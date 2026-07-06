import React from "react";
import { Layout, Menu, Typography, Button, Space, Tag, Select, message, FloatButton } from "antd";
import type { MenuProps } from "antd";
import {
  DashboardOutlined,
  LineChartOutlined,
  FileTextOutlined,
  SafetyOutlined,
  TeamOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined
} from "@ant-design/icons";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthProvider";
import i18n from "../i18n";

const { Header, Sider, Content } = Layout;

export function AppLayout() {
  const location = useLocation();
  const { me, logout, switchTenant } = useAuth();
  const { t } = useTranslation();
  const contentRef = React.useRef<HTMLDivElement>(null);

  const menuItems: MenuProps["items"] = [
    {
      type: "group",
      key: "group-workspace",
      label: t("nav.groupWorkspace"),
      children: [
        { key: "/", icon: <DashboardOutlined />, label: <Link to="/">{t("nav.dashboard")}</Link> }
      ]
    },
    {
      type: "group",
      key: "group-data",
      label: t("nav.groupData"),
      children: [
        { key: "/data", icon: <DatabaseOutlined />, label: <Link to="/data">{t("nav.data")}</Link> },
        { key: "/projects", icon: <FolderOpenOutlined />, label: <Link to="/projects">{t("nav.projects")}</Link> },
        { key: "/replay", icon: <PlayCircleOutlined />, label: <Link to="/replay">{t("nav.replay")}</Link> }
      ]
    },
    {
      type: "group",
      key: "group-analysis",
      label: t("nav.groupAnalysis"),
      children: [
        { key: "/analysis", icon: <LineChartOutlined />, label: <Link to="/analysis">{t("nav.analysis")}</Link> },
        { key: "/algorithms", icon: <DeploymentUnitOutlined />, label: <Link to="/algorithms">{t("nav.algorithms")}</Link> }
      ]
    },
    {
      type: "group",
      key: "group-delivery",
      label: t("nav.groupDelivery"),
      children: [
        { key: "/reports", icon: <FileTextOutlined />, label: <Link to="/reports">{t("nav.reports")}</Link> },
        { key: "/review", icon: <SafetyOutlined />, label: <Link to="/review">{t("nav.review")}</Link> }
      ]
    },
    ...(me?.user.is_platform_admin
      ? [
          {
            type: "group" as const,
            key: "group-system",
            label: t("nav.groupSystem"),
            children: [
              { key: "/admin", icon: <TeamOutlined />, label: <Link to="/admin">{t("nav.admin")}</Link> }
            ]
          }
        ]
      : [])
  ];

  const selectedKey = (() => {
    const path = location.pathname;
    if (path.startsWith("/data")) return "/data";
    if (path.startsWith("/projects")) return "/projects";
    if (path.startsWith("/replay")) return "/replay";
    if (path.startsWith("/analysis")) return "/analysis";
    if (path.startsWith("/algorithms")) return "/algorithms";
    if (path.startsWith("/reports")) return "/reports";
    if (path.startsWith("/review")) return "/review";
    if (path.startsWith("/admin")) return "/admin";
    return "/";
  })();

  return (
    <Layout className="wv-app-layout">
      <Sider className="wv-sider" breakpoint="lg" collapsedWidth="0" width={220}>
        <div className="wv-brand">WellVision</div>
        <Menu className="wv-nav-menu" theme="dark" mode="inline" selectedKeys={[selectedKey]} items={menuItems} />
      </Sider>
      <Layout className="wv-main-layout">
        <Header className="wv-header">
          <Space className="wv-header-left" wrap>
            <Typography.Text strong ellipsis>
              {me?.user.email}
            </Typography.Text>
            {me?.tenant_id ? <Tag color="blue">{t("layout.tenantTag")}: {me.tenant_id.slice(0, 8)}</Tag> : null}
            {me?.context?.tenants?.length ? (
              <Select
                size="small"
                style={{ minWidth: 220, maxWidth: "100%" }}
                value={me.tenant_id ?? undefined}
                options={me.context.tenants.map((t) => ({
                  value: t.tenant_id,
                  label: `${t.tenant_id.slice(0, 8)}... (${t.role})`
                }))}
                onChange={async (tenantId) => {
                  try {
                    await switchTenant(tenantId);
                    message.success(t("layout.tenantSwitchSuccess"));
                  } catch (err) {
                    message.error(t("layout.tenantSwitchFail"));
                  }
                }}
              />
            ) : null}
            <Select
              size="small"
              style={{ width: 120 }}
              value={i18n.language}
              options={[
                { value: "zh-CN", label: t("common.chinese") },
                { value: "en-US", label: t("common.english") }
              ]}
              onChange={(lng) => {
                i18n.changeLanguage(lng);
              }}
            />
            {me?.roles?.map((role) => (
              <Tag key={role}>{role}</Tag>
            ))}
          </Space>
          <div className="wv-header-right">
            <Button onClick={logout}>{t("nav.logout")}</Button>
          </div>
        </Header>
        <Content ref={contentRef} className="wv-content">
          <Outlet />
          <FloatButton.BackTop target={() => contentRef.current ?? window} />
        </Content>
      </Layout>
    </Layout>
  );
}
