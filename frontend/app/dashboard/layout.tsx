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
        <main className="dashboard-atmosphere scrollbar-slim relative min-h-0 flex-1 overflow-y-auto">
          {/* Atmospheric background layer -- subtle, non-interactive, sits
              behind all dashboard content. Positioned toward the lower-right
              with a gradient fade so it never competes with cards/charts,
              and never intercepts clicks. Reuses the existing skyline+forest
              asset rather than shipping a second large image. */}
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
            <div
              className="absolute inset-0 bg-cover bg-no-repeat opacity-[0.18] dark:opacity-[0.10]"
              style={{
                backgroundImage: "url(/images/air-quality-atmospheric-bg.jpg)",
                backgroundPosition: "85% 100%",
              }}
            />
            <div className="absolute inset-0 bg-gradient-to-tl from-transparent via-background/70 to-background" />
          </div>

          <div className="relative px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
