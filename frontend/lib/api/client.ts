import axios, {
  type AxiosError,
  type AxiosRequestConfig,
} from "axios";
import Cookies from "js-cookie";
import { secureCookieOptions } from "./cookie-options";

export const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

apiClient.interceptors.request.use((config) => {
  const token = Cookies.get("access_token");

  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});


// Single-flight refresh state: ensures concurrent 401s trigger exactly one
// refresh request. Because the backend uses refresh-token rotation, reusing
// a stale refresh token would revoke the whole token family, so every
// request that hits a 401 while a refresh is already underway must wait for
// that same in-flight promise instead of starting its own.
let refreshPromise: Promise<{ access_token: string; refresh_token: string }> | null = null;

function performLogout() {
  Cookies.remove("access_token", { path: "/" });
  Cookies.remove("refresh_token", { path: "/" });

  // BUG 014 defense-in-depth: wipe the service worker's cached API
  // responses so a different user signing in on this browser afterward
  // can never be served this user's cached data.
  if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
    navigator.serviceWorker.controller.postMessage({ type: "CLEAR_API_CACHE" });
  }

  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

function refreshTokens(): Promise<{ access_token: string; refresh_token: string }> {
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = Cookies.get("refresh_token");

  if (!refreshToken) {
    performLogout();
    return Promise.reject(new Error("No refresh token available"));
  }

  refreshPromise = axios
    .post(
      `${BASE_URL}/api/v1/auth/refresh`,
      { refresh_token: refreshToken },
      { headers: { "Content-Type": "application/json" } }
    )
    .then(({ data }) => {
      const { access_token, refresh_token } = data.data;

      Cookies.set("access_token", access_token, secureCookieOptions(1 / 48));
      Cookies.set("refresh_token", refresh_token, secureCookieOptions(7));

      return { access_token, refresh_token };
    })
    .catch((err) => {
      performLogout();
      throw err;
    })
    .finally(() => {
      // Clear so the next 401 (e.g. after this access token also expires)
      // starts a fresh refresh cycle rather than reusing a resolved promise.
      refreshPromise = null;
    });

  return refreshPromise;
}

apiClient.interceptors.response.use(
  (response) => response,

  async (error: AxiosError) => {
    const original = error.config as
      | (AxiosRequestConfig & { _retry?: boolean })
      | undefined;

    if (!original) {
      return Promise.reject(error);
    }

    const isUnauthenticated =
      error.response?.status === 401 ||
      (error.response?.status === 403 &&
        (error.response?.data as { detail?: string } | undefined)?.detail ===
          "Not authenticated");

    if (isUnauthenticated && !original._retry) {
      original._retry = true;

      try {
        const { access_token } = await refreshTokens();

        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${access_token}`;

        return apiClient(original);
      } catch (refreshError) {
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export async function get<T>(
  url: string,
  params?: Record<string, unknown>
): Promise<T> {
  const { data } = await apiClient.get<{ data: T }>(
    url,
    {
      params,
    }
  );

  return data.data;
}

export async function post<T>(
  url: string,
  body?: unknown
): Promise<T> {
  const { data } = await apiClient.post<{ data: T }>(
    url,
    body
  );

  return data.data;
}


export async function patch<T>(
  url: string,
  body?: unknown
): Promise<T> {
  const { data } = await apiClient.patch<{ data: T }>(
    url,
    body
  );

  return data.data;
}

export async function del<T>(
  url: string
): Promise<T> {
  const { data } = await apiClient.delete<{ data: T }>(
    url
  );

  return data.data;
}