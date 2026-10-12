"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Scoped to the /dashboard route segment — a crash in one dashboard page
 * shows this fallback in place of that page's content while the sidebar
 * and shell (rendered by dashboard/layout.tsx) stay intact and navigable,
 * rather than the whole app going down.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("Unhandled dashboard page error:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] p-6 text-center">
      <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-8 max-w-md">
        <AlertTriangle className="w-8 h-8 mx-auto mb-3 text-red-600 dark:text-red-400" />
        <h2 className="font-semibold text-sm mb-1">This page couldn&apos;t load</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Something went wrong loading this dashboard section. The rest of the app — including
          navigation — is unaffected.
        </p>
        <button
          onClick={reset}
          className="inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
          Try again
        </button>
      </div>
    </div>
  );
}
