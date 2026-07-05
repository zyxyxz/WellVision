import React from "react";
import { Layout, Menu, Typography, Button, Space, Tag, Select, message } from "antd";
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
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div style={{ height: 56, padding: 16, color: "white", fontWeight: 600 }}>WellVision</div>
        <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]} items={menuItems} />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            paddingInline: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between"
          }}
        >
          <Space>
            <Typography.Text strong>{me?.user.email}</Typography.Text>
            {me?.tenant_id ? <Tag color="blue">{t("layout.tenantTag")}: {me.tenant_id.slice(0, 8)}</Tag> : null}
            {me?.context?.tenants?.length ? (
              <Select
                size="small"
                style={{ minWidth: 220 }}
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
          <Button onClick={logout}>{t("nav.logout")}</Button>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
