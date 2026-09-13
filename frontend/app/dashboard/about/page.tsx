"use client";

import Link from "next/link";
import {
  Wind,
  BarChart2,
  Bot,
  Car,
  TreePine,
  ClipboardList,
  Bell,
  ShieldCheck,
  Leaf,
  Users,
  Globe,
  Zap,
  Database,
  Map,
  ChevronRight,
  Activity,
  CloudRain,
  Flame,
  Eye,
} from "lucide-react";

const CAPABILITIES = [
  {
    icon: Wind,
    title: "Air Quality Monitoring",
    description:
      "Real-time AQI, PM2.5, PM10, NO₂, SO₂, CO, and O₃ readings from CAAQMS stations across the city.",
    color: "text-aqi-good",
    bg: "bg-aqi-good/10",
  },
  {
    icon: CloudRain,
    title: "Weather Intelligence",
    description:
      "Meteorological data including temperature, humidity, wind speed, and atmospheric pressure correlated with air quality.",
    color: "text-primary",
    bg: "bg-primary/10",
  },
  {
    icon: BarChart2,
    title: "Analytics & Forecasting",
    description:
      "Predictive AQI forecasting up to 24 hours ahead using XGBoost ML models trained on historical station data.",
    color: "text-aqi-moderate",
    bg: "bg-aqi-moderate/10",
  },
  {
    icon: TreePine,
    title: "Environmental Intelligence",
    description:
      "Satellite fire detection (FIRMS), vegetation health indices (NDVI), and land use analysis for environmental awareness.",
    color: "text-aqi-good",
    bg: "bg-aqi-good/10",
  },
  {
    icon: Car,
    title: "Mobility & Traffic",
    description:
      "Traffic density correlation with air quality, identifying emission hotspots and peak pollution windows.",
    color: "text-aqi-unhealthy-sensitive",
    bg: "bg-aqi-unhealthy-sensitive/10",
  },
  {
    icon: Bot,
    title: "AI-Powered Insights",
    description:
      "Claude AI integration for natural language Q&A, anomaly explanation, and intelligent report generation.",
    color: "text-primary",
    bg: "bg-primary/10",
  },
  {
    icon: Bell,
    title: "Smart Alerts",
    description:
      "Configurable threshold alerts with real-time WebSocket push notifications for AQI breaches and station anomalies.",
    color: "text-aqi-unhealthy",
    bg: "bg-aqi-unhealthy/10",
  },
  {
    icon: ClipboardList,
    title: "Operations Hub",
    description:
      "Incident management, enforcement actions, evidence collection, and resolution tracking for field officers.",
    color: "text-aqi-very-unhealthy",
    bg: "bg-aqi-very-unhealthy/10",
  },
];

const USE_CASES = [
  {
    role: "Citizens",
    icon: Users,
    color: "text-aqi-good",
    border: "border-aqi-good/30",
    bg: "bg-aqi-good/5",
    items: [
      "Check real-time AQI for your ward before stepping outside",
      "Receive personalized alerts when air quality drops near you",
      "Plan outdoor activities using 24-hour AQI forecasts",
      "Explore historical trends to understand seasonal patterns",
      "Report pollution incidents directly through the Operations module",
    ],
  },
  {
    role: "Pollution Control Officers",
    icon: ShieldCheck,
    color: "text-primary",
    border: "border-primary/30",
    bg: "bg-primary/5",
    items: [
      "Monitor all CAAQMS stations from a single dashboard",
      "Investigate AQI anomalies with AI-assisted root-cause analysis",
      "Log enforcement actions with geo-tagged evidence",
      "Generate compliance reports and export data for regulatory submissions",
      "Set dynamic alert thresholds per pollutant per zone",
    ],
  },
  {
    role: "City Administrators",
    icon: Globe,
    color: "text-aqi-moderate",
    border: "border-aqi-moderate/30",
    bg: "bg-aqi-moderate/5",
    items: [
      "System-wide service health and data ingestion monitoring",
      "Manage user accounts, roles, and ward assignments",
      "Configure platform-wide alert thresholds and escalation rules",
      "Track pending verifications and outstanding officer actions",
      "Access analytics for evidence-based urban planning decisions",
    ],
  },
];

const HOW_TO_STEPS = [
  {
    step: "01",
    title: "Select Your City",
    description:
      "Use the city selector in the top navigation bar to switch between supported cities. Your preference is saved automatically.",
    icon: Map,
  },
  {
    step: "02",
    title: "Explore the Overview",
    description:
      "The main dashboard gives you a live snapshot — current AQI, active alerts, station health, and 24-hour trends at a glance.",
    icon: Activity,
  },
  {
    step: "03",
    title: "Drill Into Air Quality",
    description:
      "Navigate to Air Quality for per-station breakdowns, pollutant-level analysis, and the AQI forecast timeline.",
    icon: Wind,
  },
  {
    step: "04",
    title: "Ask the AI",
    description:
      'Visit AI Center and ask questions in plain English — \"Why is AQI high today?\" or \"Which station has the worst PM2.5 trend?\"',
    icon: Bot,
  },
  {
    step: "05",
    title: "Set Up Alerts",
    description:
      "Go to Administration → Alert Thresholds to configure notifications that fire when pollutants breach safe limits.",
    icon: Bell,
  },
];

const DATA_SOURCES = [
  { name: "CAAQMS", detail: "Central Air Quality Monitoring Stations", icon: Activity },
  { name: "Open-Meteo", detail: "Global weather & meteorological data", icon: CloudRain },
  { name: "OpenAQ", detail: "Global historical air quality records", icon: Database },
  { name: "FIRMS / NASA", detail: "Satellite fire & thermal anomaly data", icon: Flame },
  { name: "Mapbox", detail: "Geospatial visualisation & mapping", icon: Map },
  { name: "Claude AI", detail: "Natural language intelligence layer", icon: Eye },
];

export default function AboutPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-12 pb-12">

      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary/10 via-card to-aqi-good/10 p-8 sm:p-12 shadow-panel">
        <Leaf
          aria-hidden
          className="pointer-events-none absolute -right-8 -top-8 h-48 w-48 text-aqi-good/10 dark:text-aqi-good/15"
          strokeWidth={0.75}
        />
        <div className="relative">
          <div className="flex items-center gap-2 mb-4">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-aqi-good/30 bg-aqi-good/10 px-3 py-1 text-xs font-medium text-aqi-good">
              <span className="h-1.5 w-1.5 rounded-full bg-aqi-good" />
              Live Platform · v1.0
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground leading-tight mb-3">
            AirIQ Urban Intelligence
            <br />
            <span className="text-primary">Platform</span>
          </h1>
          <p className="text-base sm:text-lg text-muted-foreground max-w-2xl leading-relaxed">
            A unified real-time air quality monitoring and intelligence system built for
            smart cities — giving citizens, officers, and administrators the data they
            need to breathe easier and act smarter.
          </p>
          <div className="flex flex-wrap gap-3 mt-6">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Go to Dashboard
              <ChevronRight className="h-3.5 w-3.5" />
            </Link>
            <Link
              href="/dashboard/air-quality"
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground hover:bg-accent transition-colors"
            >
              View Air Quality
            </Link>
          </div>
        </div>
      </div>

      {/* What is AirIQ */}
      <section>
        <h2 className="text-xl font-bold mb-2">What is AirIQ?</h2>
        <p className="text-muted-foreground text-sm leading-relaxed max-w-3xl mb-6">
          AirIQ is a smart city air quality intelligence platform designed for Indian urban municipalities.
          It aggregates data from multiple real-world sources — CAAQMS monitoring stations, satellite
          imagery, weather APIs, and traffic feeds — into a single, unified operational view.
        </p>
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            { icon: Zap, title: "Real-Time", desc: "WebSocket-powered live updates from stations across the city, no page refresh needed." },
            { icon: Database, title: "Multi-Source", desc: "Fuses air quality, weather, satellite, and traffic data into one coherent picture." },
            { icon: Bot, title: "AI-Augmented", desc: "Claude AI layer answers questions, explains anomalies, and generates intelligent summaries." },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-2">
                <Icon className="h-4 w-4 text-primary" strokeWidth={1.5} />
                <h3 className="text-sm font-semibold">{title}</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Capabilities */}
      <section>
        <h2 className="text-xl font-bold mb-1">What It Shows</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Eight interconnected modules, each designed for a specific dimension of urban air intelligence.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {CAPABILITIES.map(({ icon: Icon, title, description, color, bg }) => (
            <div
              key={title}
              className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3 hover:border-border/80 hover:shadow-sm transition-[border-color,box-shadow]"
            >
              <div className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${bg}`}>
                <Icon className={`h-4 w-4 ${color}`} strokeWidth={1.5} />
              </div>
              <div>
                <h3 className="text-sm font-semibold leading-snug mb-1">{title}</h3>
                <p className="text-[11px] text-muted-foreground leading-relaxed">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Use Cases */}
      <section>
        <h2 className="text-xl font-bold mb-1">Who Uses It & How</h2>
        <p className="text-sm text-muted-foreground mb-6">
          AirIQ serves three distinct audiences, each with tailored capabilities and access levels.
        </p>
        <div className="grid lg:grid-cols-3 gap-4">
          {USE_CASES.map(({ role, icon: Icon, color, border, bg, items }) => (
            <div key={role} className={`rounded-xl border ${border} ${bg} p-5`}>
              <div className={`flex items-center gap-2 mb-4 ${color}`}>
                <Icon className="h-4 w-4" strokeWidth={1.5} />
                <h3 className="text-sm font-semibold">{role}</h3>
              </div>
              <ul className="space-y-2">
                {items.map((item) => (
                  <li key={item} className="flex items-start gap-2 text-xs text-muted-foreground">
                    <ChevronRight className={`h-3 w-3 mt-0.5 shrink-0 ${color}`} strokeWidth={2} />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* How to Use */}
      <section>
        <h2 className="text-xl font-bold mb-1">How to Use</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Get started in five steps — from selecting your city to setting up intelligent alerts.
        </p>
        <div className="relative">
          <div className="absolute left-6 top-8 bottom-8 w-px bg-border hidden sm:block" aria-hidden />
          <div className="space-y-4">
            {HOW_TO_STEPS.map(({ step, title, description, icon: Icon }) => (
              <div key={step} className="flex gap-4 items-start">
                <div className="relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-card shadow-sm">
                  <Icon className="h-4 w-4 text-primary" strokeWidth={1.5} />
                </div>
                <div className="rounded-xl border border-border bg-card p-4 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-mono font-semibold text-muted-foreground/60">{step}</span>
                    <h3 className="text-sm font-semibold">{title}</h3>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Data Sources & Tech */}
      <section>
        <h2 className="text-xl font-bold mb-1">Data Sources</h2>
        <p className="text-sm text-muted-foreground mb-6">
          AirIQ ingests from six authoritative data pipelines, refreshed continuously.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {DATA_SOURCES.map(({ name, detail, icon: Icon }) => (
            <div
              key={name}
              className="flex items-center gap-3 rounded-xl border border-border bg-card p-4"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                <Icon className="h-4 w-4 text-primary" strokeWidth={1.5} />
              </div>
              <div>
                <p className="text-sm font-semibold">{name}</p>
                <p className="text-[11px] text-muted-foreground">{detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer callout */}
      <div className="relative overflow-hidden rounded-2xl border border-aqi-good/30 bg-gradient-to-br from-aqi-good/10 via-card to-primary/10 p-6 text-center">
        <Leaf
          aria-hidden
          className="pointer-events-none absolute -left-4 -bottom-4 h-24 w-24 text-aqi-good/10"
          strokeWidth={0.75}
        />
        <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground/70 mb-2">
          People · Planet · Progress
        </p>
        <h3 className="text-lg font-bold text-foreground mb-1">
          Cleaner Air. Smarter Cities.
        </h3>
        <p className="text-sm text-muted-foreground max-w-md mx-auto">
          Built for the communities that breathe this air every day — data for a healthier tomorrow.
        </p>
      </div>
    </div>
  );
}
