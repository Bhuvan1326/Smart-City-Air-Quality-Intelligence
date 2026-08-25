"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Next.js App Router error boundary. Catches unhandled render/runtime
 * errors anywhere below this level and shows a scoped fallback instead of
 * letting a single broken component take down the whole page/app — this is
 * the client-side half of "a single external API failure should not crash
 * the entire dashboard."
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("Unhandled UI error:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
      <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-8 max-w-md">
        <AlertTriangle className="w-8 h-8 mx-auto mb-3 text-red-600 dark:text-red-400" />
        <h2 className="font-semibold text-sm mb-1">Something went wrong on this page</h2>
        <p className="text-xs text-muted-foreground mb-4">
          This section couldn&apos;t load correctly. The rest of the app is unaffected — try
          reloading just this page.
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
