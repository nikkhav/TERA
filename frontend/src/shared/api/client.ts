import axios, { AxiosError } from "axios";
import { tokenStore } from "./token";

export const apiClient = axios.create({
  baseURL: "/api",
  timeout: 30_000,
});

apiClient.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    console.error("[TERA API request failed]", {
      method: error.config?.method?.toUpperCase(),
      url: error.config?.url,
      status: error.response?.status,
      detail: error.response?.data,
      message: error.message,
    });
    if (error.response?.status === 401 && tokenStore.get()) {
      tokenStore.clear();
      window.dispatchEvent(new Event("tera:unauthorized"));
    }
    return Promise.reject(error);
  },
);

export function errorMessage(error: unknown) {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error
      ? error.message
      : "Ein unerwarteter Fehler ist aufgetreten.";
  }
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (typeof detail?.message === "string") return detail.message;
  if (!error.response) return "Der Server ist nicht erreichbar.";
  return "Die Anfrage konnte nicht abgeschlossen werden.";
}
