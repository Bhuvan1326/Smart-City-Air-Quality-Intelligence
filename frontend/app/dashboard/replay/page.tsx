"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { replayApi } from "@/lib/api/services";
import type { ReplayFrame } from "@/lib/api/services";
import { useCityStore } from "@/lib/store/city";
import { getAQICategory, getAQIColorHex, AQI_LEGEND } from "@/lib/utils";
import {
  Play, Pause, SkipBack, SkipForward, Clock, Activity
} from "lucide-react";
import { format, parseISO } from "date-fns";

const PUNE_WARD_POSITIONS: Record<string, { x: number; y: number; label: string }> = {
  W01: { x: 200, y: 280, label: "Karve Rd" },
  W02: { x: 270, y: 220, label: "Shivajinagar" },
  W03: { x: 360, y: 290, label: "Hadapsar" },
  W04: { x: 180, y: 120, label: "Pimpri" },
  W05: { x: 230, y: 360, label: "Katraj" },
  W06: { x: 130, y: 190, label: "Wakad" },
  W07: { x: 190, y: 300, label: "Kothrud" },
  W08: { x: 330, y: 200, label: "Yerawada" },
};

/**
 * Named schematic positions only exist for Pune's fixture wards. For any
 * other city, lay out that city's *actual* ward ids (from the replay
 * frame data) on a generic grid instead of reusing Pune's positions/labels
 * — otherwise a non-Pune city would render with Pune place names attached
 * to wards that don't belong to it.
 */
function wardPositionsFor(
  city: string,
  wardIds: string[]
): Record<string, { x: number; y: number; label: string }> {
  if (city === "Pune") return PUNE_WARD_POSITIONS;

  const cols = Math.max(1, Math.ceil(Math.sqrt(wardIds.length)));
  const cellW = 500 / (cols + 1);
  const rows = Math.max(1, Math.ceil(wardIds.length / cols));
  const cellH = 450 / (rows + 1);

  const positions: Record<string, { x: number; y: number; label: string }> = {};
  wardIds.forEach((wardId, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions[wardId] = {
      x: cellW * (col + 1),
      y: cellH * (row + 1),
      label: wardId,
    };
  });
  return positions;
}

export default function ReplayPage() {
  const { selectedCity } = useCityStore();
  const [hours, setHours] = useState(24);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(500);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { data: frames, isLoading } = useQuery({
    queryKey: ["replay", selectedCity, hours],
    queryFn: () => replayApi.aqiHistory(selectedCity, hours, 30),
    refetchOnWindowFocus: false,
  });

  const totalFrames = frames?.length ?? 0;
  const frame: ReplayFrame | undefined = frames?.[currentFrame];

  const stepForward = useCallback(() => {
    setCurrentFrame((f) => {
      if (f >= totalFrames - 1) {
        setPlaying(false);
        return f;
      }
      return f + 1;
    });
  }, [totalFrames]);

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(stepForward, speed);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playing, speed, stepForward]);

  const cityAvgAQI = frame
    ? Math.round(Object.values(frame.wards).reduce((s, w) => s + w.aqi, 0) / Math.max(Object.keys(frame.wards).length, 1))
    : 0;

  const wardPositions = wardPositionsFor(selectedCity, frame ? Object.keys(frame.wards) : []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="w-6 h-6 text-primary" />
            AQI Replay Animation
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Historical AQI spread across {selectedCity} with time scrubbing
          </p>
        </div>
        <div className="flex gap-2">
          {[6, 12, 24, 48, 72].map((h) => (
            <button
              key={h}
              onClick={() => { setHours(h); setCurrentFrame(0); setPlaying(false); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                hours === h ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {h}h
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-96 rounded-xl bg-muted animate-pulse" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* SVG ward map */}
          <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">
                {frame ? format(parseISO(frame.timestamp), "dd MMM yyyy HH:mm") : "No data"}
              </h3>
              {cityAvgAQI > 0 && (
                <span className="text-sm font-bold" style={{ color: getAQIColorHex(cityAvgAQI) }}>
                  City avg AQI: {cityAvgAQI}
                </span>
              )}
            </div>

            <svg viewBox="0 0 500 450" className="w-full h-72 md:h-96">
              {/* Background */}
              <rect width="500" height="450" fill="transparent" />

              {/* Ward circles */}
              {Object.entries(wardPositions).map(([wardId, pos]) => {
                const wardData = frame?.wards[wardId];
                const aqi = wardData?.aqi ?? 0;
                const color = aqi > 0 ? getAQIColorHex(aqi) : "#374151";
                const radius = aqi > 0 ? Math.min(45, 20 + aqi / 10) : 22;
                const opacity = aqi > 0 ? 0.75 : 0.3;

                return (
                  <g key={wardId}>
                    {/* Glow effect for high AQI */}
                    {aqi > 150 && (
                      <circle cx={pos.x} cy={pos.y} r={radius + 8} fill={color} opacity={0.15} />
                    )}
                    <circle
                      cx={pos.x}
                      cy={pos.y}
                      r={radius}
                      fill={color}
                      opacity={opacity}
                      stroke={color}
                      strokeWidth="2"
                    />
                    <text
                      x={pos.x}
                      y={pos.y - 2}
                      textAnchor="middle"
                      fill="white"
                      fontSize="11"
                      fontWeight="bold"
                    >
                      {aqi > 0 ? aqi : "—"}
                    </text>
                    <text
                      x={pos.x}
                      y={pos.y + 11}
                      textAnchor="middle"
                      fill="white"
                      fontSize="8"
                      opacity={0.9}
                    >
                      {wardId}
                    </text>
                    <text
                      x={pos.x}
                      y={pos.y + radius + 14}
                      textAnchor="middle"
                      fill="currentColor"
                      fontSize="9"
                      opacity={0.6}
                    >
                      {pos.label}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* AQI scale */}
            <div className="flex gap-3 justify-center mt-3 flex-wrap">
              {AQI_LEGEND.map(({ key, label, hex }) => (
                <div key={key} className="flex items-center gap-1.5 text-xs">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: hex }} />
                  <span className="text-muted-foreground">{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Ward AQI table for current frame */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="font-semibold text-sm mb-3">Ward Readings</h3>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {Object.entries(wardPositions)
                .map(([wardId, pos]) => {
                  const wardData = frame?.wards[wardId];
                  const aqi = wardData?.aqi ?? 0;
                  const { color, label } = getAQICategory(aqi);
                  return { wardId, label: pos.label, aqi, color, aqiLabel: label };
                })
                .sort((a, b) => b.aqi - a.aqi)
                .map(({ wardId, label, aqi, color, aqiLabel }) => (
                  <div key={wardId} className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/30">
                    <div>
                      <p className="text-sm font-medium">{label}</p>
                      <p className="text-xs text-muted-foreground">{wardId}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold" style={{ color }}>{aqi || "—"}</p>
                      <p className="text-xs" style={{ color }}>{aqiLabel}</p>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* Playback controls */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-4">
          {/* Transport */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setCurrentFrame(0); setPlaying(false); }}
              className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
            >
              <SkipBack className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPlaying((p) => !p)}
              disabled={totalFrames === 0}
              className="p-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </button>
            <button
              onClick={() => { setCurrentFrame(totalFrames - 1); setPlaying(false); }}
              className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
            >
              <SkipForward className="w-4 h-4" />
            </button>
          </div>

          {/* Scrubber */}
          <div className="flex-1">
            <input
              type="range"
              min={0}
              max={Math.max(0, totalFrames - 1)}
              value={currentFrame}
              onChange={(e) => { setCurrentFrame(Number(e.target.value)); setPlaying(false); }}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-xs text-muted-foreground mt-1">
              <span>{frames?.[0] ? format(parseISO(frames[0].timestamp), "dd MMM HH:mm") : "—"}</span>
              <span className="font-medium">
                Frame {currentFrame + 1}/{totalFrames}
              </span>
              <span>{frames?.[totalFrames - 1] ? format(parseISO(frames[totalFrames - 1].timestamp), "dd MMM HH:mm") : "—"}</span>
            </div>
          </div>

          {/* Speed control */}
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
            <select
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="px-2 py-1 text-xs rounded-lg border border-border bg-background"
            >
              <option value={1000}>0.5×</option>
              <option value={500}>1×</option>
              <option value={250}>2×</option>
              <option value={100}>5×</option>
              <option value={50}>10×</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
