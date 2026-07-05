import React from "react";
import { Spin } from "antd";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";

const DashboardPage = React.lazy(async () => {
  const mod = await import("./pages/DashboardPage");
  return { default: mod.DashboardPage };
});

const DataPage = React.lazy(async () => {
  const mod = await import("./pages/DataPage");
  return { default: mod.DataPage };
});

const ProjectsPage = React.lazy(async () => {
  const mod = await import("./pages/ProjectsPage");
  return { default: mod.ProjectsPage };
});

const DataWarehousePage = React.lazy(async () => {
  const mod = await import("./pages/DataWarehousePage");
  return { default: mod.DataWarehousePage };
});

const AlgorithmsPage = React.lazy(async () => {
  const mod = await import("./pages/AlgorithmsPage");
  return { default: mod.AlgorithmsPage };
});

const AlgorithmEditorPage = React.lazy(async () => {
  const mod = await import("./pages/AlgorithmEditorPage");
  return { default: mod.AlgorithmEditorPage };
});

const AnalysisPage = React.lazy(async () => {
  const mod = await import("./pages/AnalysisPage");
  return { default: mod.AnalysisPage };
});

const DrillReplayPage = React.lazy(async () => {
  const mod = await import("./pages/DrillReplayPage");
  return { default: mod.DrillReplayPage };
});

const PlaceholderPage = React.lazy(async () => {
  const mod = await import("./pages/PlaceholderPage");
  return { default: mod.PlaceholderPage };
});

const ReportsPage = React.lazy(async () => {
  const mod = await import("./pages/ReportsPage");
  return { default: mod.ReportsPage };
});

const AdminPage = React.lazy(async () => {
  const mod = await import("./pages/AdminPage");
  return { default: mod.AdminPage };
});

function RouteFallback() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: 120 }}>
      <Spin size="large" />
    </div>
  );
}

function LazyRoute({ children }: { children: React.ReactNode }) {
  return <React.Suspense fallback={<RouteFallback />}>{children}</React.Suspense>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<LazyRoute><DashboardPage /></LazyRoute>} />
        <Route path="/data" element={<LazyRoute><DataPage /></LazyRoute>} />
        <Route path="/projects" element={<LazyRoute><ProjectsPage /></LazyRoute>} />
        <Route path="/data/:warehouseId" element={<LazyRoute><DataWarehousePage /></LazyRoute>} />
        <Route path="/ingestion" element={<Navigate to="/data" replace />} />
        <Route path="/streaming" element={<Navigate to="/data" replace />} />
        <Route path="/algorithms" element={<LazyRoute><AlgorithmsPage /></LazyRoute>} />
        <Route path="/algorithms/new" element={<LazyRoute><AlgorithmEditorPage /></LazyRoute>} />
        <Route path="/algorithms/:algorithmId/edit" element={<LazyRoute><AlgorithmEditorPage /></LazyRoute>} />
        <Route path="/analysis" element={<LazyRoute><AnalysisPage /></LazyRoute>} />
        <Route path="/replay" element={<LazyRoute><DrillReplayPage /></LazyRoute>} />
        <Route path="/curves" element={<Navigate to="/analysis" replace />} />
        <Route path="/reports" element={<LazyRoute><ReportsPage /></LazyRoute>} />
        <Route path="/review" element={<LazyRoute><PlaceholderPage title="Review" /></LazyRoute>} />
        <Route path="/admin" element={<LazyRoute><AdminPage /></LazyRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
