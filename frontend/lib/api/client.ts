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


apiClient.interceptors.response.use(
  (response) => response,

  async (error: AxiosError) => {
    const original = error.config as
      | (AxiosRequestConfig & { _retry?: boolean })
      | undefined;

    if (!original) {
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;

      const refreshToken = Cookies.get("refresh_token");

      if (refreshToken) {
        try {
          const { data } = await axios.post(
            `${BASE_URL}/api/v1/auth/refresh`,
            {
              refresh_token: refreshToken,
            },
            {
              headers: {
                "Content-Type": "application/json",
              },
            }
          );

          const {
            access_token,
            refresh_token,
          } = data.data;

          Cookies.set("access_token", access_token, secureCookieOptions(1 / 48));
          Cookies.set("refresh_token", refresh_token, secureCookieOptions(7));

          original.headers = original.headers ?? {};
          original.headers.Authorization = `Bearer ${access_token}`;

          return apiClient(original);
        } catch {
          Cookies.remove("access_token", {
            path: "/",
          });

          Cookies.remove("refresh_token", {
            path: "/",
          });

          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
        }
      } else {
        Cookies.remove("access_token", {
          path: "/",
        });

        Cookies.remove("refresh_token", {
          path: "/",
        });

        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
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