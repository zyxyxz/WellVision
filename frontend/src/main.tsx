import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider } from "antd";

import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import "./i18n";
import "./styles.css";

import "antd/dist/reset.css";

if (import.meta.env.DEV) {
  const originalWarn = console.warn;
  console.warn = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("Support for defaultProps")) {
      return;
    }
    originalWarn(...args);
  };
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
);
