"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store/auth";
import { Sidebar } from "@/components/layout/Sidebar";
import { Navbar } from "@/components/layout/Navbar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, hasHydrated } = useAuthStore();
  const router = useRouter();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    // Wait for the persisted auth state to rehydrate from storage before
    // deciding to redirect - otherwise a page refresh briefly sees the
    // default (unauthenticated) state and bounces a logged-in user to /login.
    if (hasHydrated && !isAuthenticated) {
      router.push("/login");
    }
  }, [hasHydrated, isAuthenticated, router]);

  if (!hasHydrated) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-background">
        <div
          className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent"
          role="status"
          aria-label="Loading"
        />
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    // 100dvh rather than h-screen: on iOS Safari the latter is measured against
    // the largest viewport and the shell jumps as the browser chrome collapses.
    <div className="flex h-[100dvh] overflow-hidden bg-background">
      <Sidebar mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />

      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
        <Navbar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="scrollbar-slim min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
