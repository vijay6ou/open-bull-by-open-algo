import axios from "axios";
import {
  broadcastSession,
  goToLogin,
  markStayOnLogin,
} from "@/lib/sessionSync";

const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

const PUBLIC_PATHS = new Set(["/", "/login", "/setup"]);

function isAuthUrl(url: string | undefined): boolean {
  const path = url || "";
  return (
    path.includes("/auth/login") ||
    path.includes("/auth/logout") ||
    path.includes("/auth/check-setup") ||
    path.includes("/auth/setup")
  );
}

let handling401 = false;

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const reqUrl = error.config?.url as string | undefined;
    if (status === 401 && !isAuthUrl(reqUrl)) {
      const currentPath = window.location.pathname;
      if (!PUBLIC_PATHS.has(currentPath) && !handling401) {
        handling401 = true;
        markStayOnLogin();
        // Clear the cookie so /login does not bounce straight back.
        api.post("/auth/logout").catch(() => {}).finally(() => {
          broadcastSession({ type: "logout" });
          goToLogin();
          handling401 = false;
        });
      }
    }
    return Promise.reject(error);
  }
);

export default api;
