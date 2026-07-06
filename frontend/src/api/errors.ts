import axios from "axios";

type ErrorPayload = {
  detail?: unknown;
  message?: unknown;
};

function stringifyDetail(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter(Boolean);
    return messages.length ? messages.join("; ") : null;
  }
  return null;
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError<ErrorPayload>(error)) return fallback;
  const payload = error.response?.data;
  return stringifyDetail(payload?.detail) || stringifyDetail(payload?.message) || fallback;
}
