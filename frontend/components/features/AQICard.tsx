"use client";

import { getAQICategory } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface AQICardProps {
  station: string;
  ward?: string;
  aqi: number;
  pm25?: number;
  trend?: string;
  category?: string;
  healthMessage?: string;
  compact?: boolean;
}

export function AQICard({ station, ward, aqi, pm25, trend, healthMessage, compact }: AQICardProps) {
  const { label, bgColor, textColor, color } = getAQICategory(aqi);
  const TrendIcon = trend === "improving" ? TrendingDown : trend === "worsening" ? TrendingUp : Minus;
  const trendColor = trend === "improving" ? "text-green-500" : trend === "worsening" ? "text-red-500" : "text-muted-foreground";

  if (compact) {
    return (
      <div className="flex items-center justify-between p-3 rounded-lg bg-card border border-border hover:border-primary/30 transition-colors">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{ward ?? station}</p>
          <p className="text-sm font-semibold">{station}</p>
        </div>
        <div className="text-right">
          <p className="text-xl font-bold" style={{ color }}>{aqi}</p>
          <p className={`text-xs ${textColor}`}>{label}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs text-muted-foreground font-medium">{ward ? `Ward ${ward}` : "Station"}</p>
          <p className="text-sm font-semibold mt-0.5">{station}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${bgColor} ${textColor}`}>
          {label}
        </span>
      </div>

      <div className="flex items-end gap-3">
        <div>
          <p className="text-3xl font-bold" style={{ color }}>{aqi}</p>
          <p className="text-xs text-muted-foreground">AQI</p>
        </div>
        {pm25 != null && (
          <div className="mb-1">
            <p className="text-lg font-semibold text-foreground">{pm25.toFixed(1)}</p>
            <p className="text-xs text-muted-foreground">PM2.5 μg/m³</p>
          </div>
        )}
        {trend && (
          <div className={`mb-1 ml-auto ${trendColor}`}>
            <TrendIcon className="w-5 h-5" />
            <p className="text-xs capitalize">{trend}</p>
          </div>
        )}
      </div>

      {healthMessage && (
        <p className="mt-2 text-xs text-muted-foreground border-t border-border pt-2">{healthMessage}</p>
      )}
    </div>
  );
}

export function AQICardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-4 animate-pulse">
      <div className="flex justify-between mb-3">
        <div className="space-y-1">
          <div className="h-3 w-16 bg-muted rounded" />
          <div className="h-4 w-28 bg-muted rounded" />
        </div>
        <div className="h-5 w-20 bg-muted rounded-full" />
      </div>
      <div className="flex items-end gap-3">
        <div className="h-9 w-16 bg-muted rounded" />
        <div className="h-7 w-12 bg-muted rounded" />
      </div>
    </div>
  );
}
