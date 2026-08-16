"use client";

import { useState, useRef } from "react";
import {
  CheckCircle,
  Camera,
  X,
  MapPin,
  Loader2,
  CloudOff,
} from "lucide-react";
import { queueEvidence } from "@/lib/offline/db";
import {
  flushEvidenceQueue,
  registerBackgroundSync,
} from "@/lib/offline/sync-manager";
import type { EnforcementAction } from "@/lib/api/services";

interface Props {
  action: EnforcementAction;
  onSubmitted?: () => void;
}

/** Resizes/compresses a captured photo client-side before it's queued — keeps IndexedDB and upload payloads small on a mobile data connection. */
async function compressPhoto(
  file: File,
  maxDimension = 1280,
  quality = 0.72,
): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(
    1,
    maxDimension / Math.max(bitmap.width, bitmap.height),
  );
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported");
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", quality);
}

function getCurrentPosition(): Promise<GeolocationPosition | null> {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) {
      resolve(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(pos),
      () => resolve(null),
      { timeout: 5000, maximumAge: 60_000 },
    );
  });
}

export function InspectionEvidenceForm({ action, onSubmitted }: Props) {
  const [status, setStatus] = useState<"completed" | "in_progress">(
    "completed",
  );
  const [notes, setNotes] = useState("");
  const [outcomeScore, setOutcomeScore] = useState<string>("");
  const [photos, setPhotos] = useState<string[]>([]);
  const [isProcessingPhoto, setIsProcessingPhoto] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<"online" | "queued" | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handlePhotoCapture = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setIsProcessingPhoto(true);
    try {
      const compressed = await Promise.all(files.map((f) => compressPhoto(f)));
      setPhotos((prev) => [...prev, ...compressed].slice(0, 10));
    } catch (err) {
      console.error("Photo processing failed:", err);
    } finally {
      setIsProcessingPhoto(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removePhoto = (index: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      const position = await getCurrentPosition();
      const clientId = crypto.randomUUID();

      await queueEvidence({
        id: clientId,
        actionId: action.id,
        status,
        notes,
        outcomeScore: outcomeScore ? Number(outcomeScore) : null,
        photos,
        latitude: position?.coords.latitude ?? null,
        longitude: position?.coords.longitude ?? null,
        capturedAt: new Date().toISOString(),
        syncStatus: "pending",
        retryCount: 0,
      });

      // Always queue first (so nothing is lost if the network drops mid-submit),
      // then attempt an immediate sync if we appear to be online.
      if (navigator.onLine) {
        await flushEvidenceQueue();
        setSubmitted("online");
      } else {
        await registerBackgroundSync();
        setSubmitted("queued");
      }

      onSubmitted?.();
    } catch (err) {
      console.error("Failed to queue inspection evidence:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-4 flex items-start gap-3">
        {submitted === "online" ? (
          <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
        ) : (
          <CloudOff className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
        )}
        <div>
          <p className="text-sm font-medium">
            {submitted === "online" ? "Inspection submitted" : "Saved offline"}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {submitted === "online"
              ? "Your report has been sent."
              : "No connection — this will sync automatically once you're back online."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Complete Inspection</p>
        <div className="flex rounded-lg border border-border overflow-hidden text-xs">
          {(["in_progress", "completed"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 font-medium transition-colors ${
                status === s
                  ? "bg-primary text-primary-foreground"
                  : "bg-transparent text-muted-foreground"
              }`}
            >
              {s === "in_progress" ? "Still in progress" : "Completed"}
            </button>
          ))}
        </div>
      </div>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Inspection notes — what did you find on site?"
        rows={3}
        maxLength={5000}
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-primary"
      />

      {status === "completed" && (
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">
            Outcome score (0-100)
          </label>
          <input
            type="number"
            min={0}
            max={100}
            value={outcomeScore}
            onChange={(e) => setOutcomeScore(e.target.value)}
            className="w-24 rounded-lg border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      )}

      <div>
        <div className="flex items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isProcessingPhoto || photos.length >= 10}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border hover:border-primary/50 transition-colors disabled:opacity-50"
          >
            {isProcessingPhoto ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Camera className="w-3.5 h-3.5" />
            )}
            Add photo evidence
          </button>
          <span className="text-xs text-muted-foreground">
            {photos.length}/10
          </span>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          className="hidden"
          onChange={handlePhotoCapture}
        />
        {photos.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {photos.map((photo, i) => (
              <div
                key={i}
                className="relative w-16 h-16 rounded-lg overflow-hidden border border-border"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={photo}
                  alt={`Evidence ${i + 1}`}
                  className="w-full h-full object-cover"
                />
                <button
                  onClick={() => removePhoto(i)}
                  className="absolute top-0.5 right-0.5 bg-black/60 rounded-full p-0.5"
                >
                  <X className="w-3 h-3 text-white" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-1">
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <MapPin className="w-3 h-3" />
          GPS location will be attached automatically
        </span>
        <button
          onClick={handleSubmit}
          disabled={isSubmitting}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
        >
          {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          Submit Report
        </button>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Works offline — your report saves on this device instantly and uploads
        automatically once you have a connection.
      </p>
    </div>
  );
}
