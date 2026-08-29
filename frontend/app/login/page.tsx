"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Wind, Eye, EyeOff, Loader2, AlertCircle } from "lucide-react";
import { authApi } from "@/lib/api/services";
import { useAuthStore, type UserRole } from "@/lib/store/auth";

const schema = z.object({
  email: z.string().email("Valid email required"),
  password: z.string().min(6, "Password required"),
});
type FormData = z.infer<typeof schema>;

interface ApiErrorShape {
  response?: {
    status?: number;
    data?: {
      detail?: string;
      message?: string;
    };
  };
}

function getApiErrorDetail(err: unknown): { status?: number; message?: string } {
  if (err && typeof err === "object" && "response" in err) {
    const response = (err as ApiErrorShape).response;
    return {
      status: response?.status,
      message: response?.data?.detail ?? response?.data?.message,
    };
  }
  return {};
}

const DEMO_ACCOUNTS: { role: string; label: string; email: string; password: string }[] = [
  { role: "admin", label: "Admin", email: "admin@pune.gov.in", password: "Admin@123" },
  { role: "officer", label: "Officer", email: "officer@mpcb.gov.in", password: "Officer@123" },
  { role: "inspector", label: "Inspector", email: "inspector@pune.gov.in", password: "Inspector@123" },
  { role: "citizen", label: "Citizen", email: "citizen@pune.in", password: "Citizen@123" },
];

export default function LoginPage() {
  const router = useRouter();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (data: FormData) => {
    setError(null);

    // Step 1: authenticate and obtain tokens.
    let loginResult: { access_token: string; refresh_token: string };
    try {
      loginResult = await authApi.login(data.email.trim(), data.password);
    } catch (err: unknown) {
      const { status, message } = getApiErrorDetail(err);
      if (status === 401) {
        setError(message ?? "Invalid email or password.");
      } else {
        setError(message ?? "Login failed. Please try again.");
      }
      return;
    }

    // Step 2: persist tokens BEFORE calling any authenticated endpoint.
    // The axios request interceptor reads the access_token cookie to attach
    // the Authorization header, so /auth/me must not fire until this has run.
    setTokens(loginResult.access_token, loginResult.refresh_token);

    // Step 3: fetch the authenticated user profile.
    try {
      const me = await authApi.me();
      setUser({ ...me, role: me.role as UserRole });
      router.push("/dashboard");
    } catch (err: unknown) {
      // Login succeeded but session initialization failed - don't strand the
      // user with valid-looking tokens and no user object.
      clearAuth();
      const { message } = getApiErrorDetail(err);
      setError(
        message
          ? `Login succeeded, but your session could not be initialized: ${message}`
          : "Login succeeded, but your session could not be initialized. Please try again."
      );
    }
  };

  const fillDemo = (email: string, password: string) => {
    setValue("email", email, { shouldValidate: true, shouldDirty: true, shouldTouch: true });
    setValue("password", password, { shouldValidate: true, shouldDirty: true, shouldTouch: true });
    setError(null);
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-blue-600 mb-4">
            <Wind className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">AirIQ Platform</h1>
          <p className="text-slate-500 text-sm mt-1">Urban Air Quality Intelligence</p>
        </div>

        {/* Card */}
        <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 mb-1">Sign in to your account</h2>
          <p className="text-sm text-slate-500 mb-6">Enter your credentials to access the dashboard</p>

          {error && (
            <div
              role="alert"
              className="mb-5 flex items-start gap-2 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                {...register("email")}
                aria-invalid={errors.email ? "true" : "false"}
                aria-describedby={errors.email ? "email-error" : undefined}
                className="w-full px-3.5 py-2.5 rounded-lg bg-white border border-slate-300 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors text-sm"
                placeholder="you@city.gov.in"
              />
              {errors.email && (
                <p id="email-error" className="mt-1.5 text-xs text-red-600">
                  {errors.email.message}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPass ? "text" : "password"}
                  autoComplete="current-password"
                  {...register("password")}
                  aria-invalid={errors.password ? "true" : "false"}
                  aria-describedby={errors.password ? "password-error" : undefined}
                  className="w-full px-3.5 py-2.5 pr-10 rounded-lg bg-white border border-slate-300 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors text-sm"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  aria-label={showPass ? "Hide password" : "Show password"}
                  aria-pressed={showPass}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.password && (
                <p id="password-error" className="mt-1.5 text-xs text-red-600">
                  {errors.password.message}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 text-white font-medium text-sm transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
              {isSubmitting ? "Signing in..." : "Sign in"}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="mt-6 pt-6 border-t border-slate-200">
            <p className="text-xs font-medium text-slate-500 mb-3 text-center">Demo accounts (autofill)</p>
            <div className="grid grid-cols-4 gap-2">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.role}
                  type="button"
                  onClick={() => fillDemo(account.email, account.password)}
                  className="py-1.5 px-2 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {account.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-2 text-center">Click to autofill, then Sign in</p>
          </div>
        </div>

        <p className="text-center text-xs text-slate-400 mt-6">
          Urban Air Quality Intelligence Platform
        </p>
      </div>
    </div>
  );
}
