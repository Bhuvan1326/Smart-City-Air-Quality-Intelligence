import Cookies from "js-cookie";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { secureCookieOptions } from "@/lib/api/cookie-options";

export type UserRole =
  | "city_administrator"
  | "pollution_control_officer"
  | "field_inspector"
  | "citizen";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  city: string | null;
  ward_id: string | null;
  preferred_language: string;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  hasHydrated: boolean;

  /**
   * Persists the access/refresh tokens (cookies + store) WITHOUT marking the
   * user as authenticated yet. This must run before any authenticated
   * request (e.g. GET /auth/me) is made, otherwise the request interceptor
   * has no cookie to read and the call fails with 401.
   */
  setTokens: (accessToken: string, refreshToken: string) => void;

  /** Marks the session as authenticated once the user profile is known. */
  setUser: (user: User) => void;

  /** Convenience helper that sets tokens + user in one call. */
  setAuth: (
    user: User,
    accessToken: string,
    refreshToken: string
  ) => void;

  clearAuth: () => void;
  setHasHydrated: (value: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      hasHydrated: false,

      setTokens: (accessToken, refreshToken) => {
        Cookies.set("access_token", accessToken, secureCookieOptions(1 / 48));
        Cookies.set("refresh_token", refreshToken, secureCookieOptions(7));

        set({
          accessToken,
          refreshToken,
        });
      },

      setUser: (user) => {
        set({
          user,
          isAuthenticated: true,
        });
      },

      setAuth: (user, accessToken, refreshToken) => {
        Cookies.set("access_token", accessToken, secureCookieOptions(1 / 48));
        Cookies.set("refresh_token", refreshToken, secureCookieOptions(7));

        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
        });
      },

      clearAuth: () => {
        Cookies.remove("access_token", {
          path: "/",
        });

        Cookies.remove("refresh_token", {
          path: "/",
        });

        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        });
      },

      setHasHydrated: (value) => {
        set({ hasHydrated: value });
      },
    }),

    {
      name: "auth-store",

      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),

      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);