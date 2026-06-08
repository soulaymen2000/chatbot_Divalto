/**
 * Axios API client for NovaMind.
 *
 * Features:
 * - Base URL from config.ts (reads /api/config endpoint)
 * - Attaches JWT Bearer token automatically to every request
 * - Auto-refreshes access token on 401 errors
 * - Redirects to /auth on refresh failure (token fully expired)
 */
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import { getAPIBaseURL } from "./config";

// ─── Token Storage Helpers ────────────────────────────────────────────────────

const TOKEN_KEY = "novamind_access_token";
const REFRESH_KEY = "novamind_refresh_token";

export const tokenStorage = {
  getAccess: (): string | null => localStorage.getItem(TOKEN_KEY),
  getRefresh: (): string | null => localStorage.getItem(REFRESH_KEY),
  setTokens: (access: string, refresh: string) => {
    localStorage.setItem(TOKEN_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clearTokens: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

// ─── Axios Instance ───────────────────────────────────────────────────────────

export const apiClient = axios.create({
  get baseURL() {
    return getAPIBaseURL();
  },
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 120000, // 2 minutes — RAG generation on CPU can take 40+ seconds
});

// ─── Request Interceptor — Attach JWT ─────────────────────────────────────────

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = tokenStorage.getAccess();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response Interceptor — Auto Refresh ─────────────────────────────────────

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
}> = [];

const processQueue = (error: AxiosError | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Only attempt refresh on 401 and not already retried
    if (error.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = tokenStorage.getRefresh();
      if (!refreshToken) {
        tokenStorage.clearTokens();
        window.location.href = "/auth";
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Queue requests that come in while a refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return apiClient(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const response = await axios.post(
          "/api/auth/token/refresh/",
          { refresh: refreshToken }
        );
        const { access } = response.data;
        tokenStorage.setTokens(access, refreshToken);
        processQueue(null, access);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${access}`;
        }
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError as AxiosError, null);
        tokenStorage.clearTokens();
        window.location.href = "/auth";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ─── Typed API Methods ────────────────────────────────────────────────────────

export const authAPI = {
  register: (data: { name: string; email: string; password: string; confirm_password: string }) =>
    apiClient.post("/api/auth/register/", data),

  login: (data: { email: string; password: string }) =>
    apiClient.post("/api/auth/login/", data),

  logout: (refresh: string) =>
    apiClient.post("/api/auth/logout/", { refresh }),

  getProfile: () =>
    apiClient.get("/api/auth/profile/"),

  updateProfile: (data: FormData | { name?: string }) =>
    apiClient.patch("/api/auth/profile/", data),

  changePassword: (data: { old_password: string; new_password: string }) =>
    apiClient.post("/api/auth/password/change/", data),
};

export const chatAPI = {
  listConversations: () =>
    apiClient.get("/api/conversations/"),

  createConversation: () =>
    apiClient.post("/api/conversations/"),

  getConversation: (id: string) =>
    apiClient.get(`/api/conversations/${id}/`),

  renameConversation: (id: string, title: string) =>
    apiClient.patch(`/api/conversations/${id}/`, { title }),

  deleteConversation: (id: string) =>
    apiClient.delete(`/api/conversations/${id}/`),

  sendMessage: (conversationId: string, content: string) =>
    apiClient.post(`/api/conversations/${conversationId}/messages/`, { content }),
};

export const feedbackAPI = {
  submitFeedback: (
    messageId: string,
    data: {
      rating?: number;
      sentiment?: "helpful" | "not_helpful";
      issue_type?: string;
      comment?: string;
    }
  ) => apiClient.post(`/api/messages/${messageId}/feedback/`, data),
};
