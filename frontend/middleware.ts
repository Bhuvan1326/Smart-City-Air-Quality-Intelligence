import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const ROUTE_MAP: Record<string, { newPath: string; module: string }> = {
  "/dashboard/live-aqi": { newPath: "/dashboard/air-quality", module: "live" },
  "/dashboard/india-aqi": { newPath: "/dashboard/air-quality", module: "india" },
  "/dashboard/forecast": { newPath: "/dashboard/air-quality", module: "forecast" },
  "/dashboard/heatmap": { newPath: "/dashboard/air-quality", module: "heatmap" },
  "/dashboard/sources": { newPath: "/dashboard/air-quality", module: "sources" },
  "/dashboard/transparency": { newPath: "/dashboard/air-quality", module: "transparency" },
  // The Replay module id no longer exists on the Air Quality page — the
  // AQI Replay Animation tab was removed there (requirement 5). Land on
  // Air Quality's default (Live AQI) tab instead of a dead module id.
  "/dashboard/replay": { newPath: "/dashboard/air-quality", module: "live" },
  "/dashboard/analytics": { newPath: "/dashboard/intelligence", module: "analytics" },
  "/dashboard/recommendations": { newPath: "/dashboard/intelligence", module: "recommendations" },
  "/dashboard/simulator": { newPath: "/dashboard/intelligence", module: "simulator" },
  "/dashboard/traffic-pollution": { newPath: "/dashboard/mobility", module: "traffic" },
  "/dashboard/route-analysis": { newPath: "/dashboard/mobility", module: "routes" },
  "/dashboard/smart-mobility": { newPath: "/dashboard/mobility", module: "smart" },
  "/dashboard/exposure": { newPath: "/dashboard/environmental", module: "exposure" },
  "/dashboard/construction-dust": { newPath: "/dashboard/environmental", module: "construction" },
  "/dashboard/green-infrastructure": { newPath: "/dashboard/environmental", module: "green" },
  "/dashboard/waste-burning": { newPath: "/dashboard/environmental", module: "waste-burning" },
  "/dashboard/energy": { newPath: "/dashboard/environmental", module: "energy" },
  "/dashboard/heat": { newPath: "/dashboard/environmental", module: "heat" },
  "/dashboard/waste-circularity": { newPath: "/dashboard/environmental", module: "circularity" },
  "/dashboard/water": { newPath: "/dashboard/environmental", module: "water" },
  "/dashboard/industrial-pollution": { newPath: "/dashboard/environmental", module: "industrial" },
  "/dashboard/civic": { newPath: "/dashboard/operations", module: "civic" },
  "/dashboard/enforcement": { newPath: "/dashboard/operations", module: "enforcement" },
  "/dashboard/officer": { newPath: "/dashboard/operations", module: "officer" },
  "/dashboard/citizen": { newPath: "/dashboard/operations", module: "alerts" },
  "/dashboard/alert-thresholds": { newPath: "/dashboard/operations", module: "thresholds" },
  "/dashboard/assistant": { newPath: "/dashboard/ai", module: "assistant" },
  "/dashboard/agents": { newPath: "/dashboard/ai", module: "agents" },
  "/dashboard/admin": { newPath: "/dashboard/administration", module: "admin" },
  "/dashboard/settings": { newPath: "/dashboard/administration", module: "settings" },
};

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const mapping = ROUTE_MAP[pathname];

  if (!mapping) return NextResponse.next();

  const url = request.nextUrl.clone();
  url.pathname = mapping.newPath;

  const existingParams = request.nextUrl.searchParams;
  url.searchParams.set("module", mapping.module);
  existingParams.forEach((value, key) => {
    if (key !== "module") url.searchParams.set(key, value);
  });

  return NextResponse.redirect(url, { status: 308 });
}

export const config = {
  matcher: [
    "/dashboard/live-aqi",
    "/dashboard/india-aqi",
    "/dashboard/forecast",
    "/dashboard/heatmap",
    "/dashboard/sources",
    "/dashboard/transparency",
    "/dashboard/replay",
    "/dashboard/analytics",
    "/dashboard/recommendations",
    "/dashboard/simulator",
    "/dashboard/traffic-pollution",
    "/dashboard/route-analysis",
    "/dashboard/smart-mobility",
    "/dashboard/exposure",
    "/dashboard/construction-dust",
    "/dashboard/green-infrastructure",
    "/dashboard/waste-burning",
    "/dashboard/energy",
    "/dashboard/heat",
    "/dashboard/waste-circularity",
    "/dashboard/water",
    "/dashboard/industrial-pollution",
    "/dashboard/civic",
    "/dashboard/enforcement",
    "/dashboard/officer",
    "/dashboard/citizen",
    "/dashboard/alert-thresholds",
    "/dashboard/assistant",
    "/dashboard/agents",
    "/dashboard/admin",
    "/dashboard/settings",
  ],
};
