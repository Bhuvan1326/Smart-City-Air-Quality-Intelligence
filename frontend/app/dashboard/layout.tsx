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
    <div className="env-atmosphere relative flex h-[100dvh] overflow-hidden bg-background">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-no-repeat opacity-[0.26] dark:opacity-[0.13]"
          style={{
            backgroundImage: "url(/images/air-quality-atmospheric-bg.jpg)",
            backgroundPosition: "78% 100%",
          }}
        />
        {/* Very light top vignette only -- enough to settle the header row,
            without flattening the image the way a fuller mask would. */}
        <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-background/70 to-transparent" />
      </div>

      <Sidebar mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />

      <div className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col">
        <Navbar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="scrollbar-slim relative min-h-0 flex-1 overflow-y-auto">
          <div className="relative px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
