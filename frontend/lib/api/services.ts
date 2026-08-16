import { get, post, patch } from "./client";

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    post<{ access_token: string; refresh_token: string; expires_in: number }>("/auth/login", { email, password }),
  register: (data: { email: string; password: string; full_name: string; role?: string; city?: string }) =>
    post<{ id: string; email: string }>("/auth/register", data),
  me: () => get<{ id: string; email: string; full_name: string; role: string; city: string | null; ward_id: string | null; preferred_language: string }>("/auth/me"),
  logout: () => post("/auth/logout"),
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboardApi = {
  overview: (city: string) => get<DashboardOverview>(`/dashboard/overview?city=${city}`),
};

// ─── AQI ──────────────────────────────────────────────────────────────────────

export const aqiApi = {
  live: (city: string) => get<LiveAQIItem[]>(`/aqi/live?city=${city}`),
  history: (params: {
    station_id?: string;
    city?: string;
    start_time: string;
    end_time: string;
    interval?: string;
  }) => get<AQIHistoryPoint[]>(`/aqi/history`, params as Record<string, unknown>),
  stations: (city?: string, page = 1) =>
    get<PaginatedResponse<Station>>(`/aqi/stations?page=${page}${city ? `&city=${city}` : ""}`),
};

// ─── Forecast ─────────────────────────────────────────────────────────────────

export const forecastApi = {
  city: (city: string, hoursAhead = 24) =>
    get<ForecastItem[]>(`/forecast?city=${city}&hours_ahead=${hoursAhead}`),
  ward: (wardId: string, city: string) =>
    get<WardForecastSummary>(`/forecast/${wardId}?city=${city}`),
};

// ─── Attribution ──────────────────────────────────────────────────────────────

export const attributionApi = {
  live: (city: string) => get<Attribution[]>(`/attribution/live?city=${city}`),
  history: (city: string, wardId?: string, startTime?: string, endTime?: string) =>
    get<Attribution[]>(`/attribution/history?city=${city}${wardId ? `&ward_id=${wardId}` : ""}${startTime ? `&start_time=${startTime}` : ""}${endTime ? `&end_time=${endTime}` : ""}`),
};

// ─── Enforcement ──────────────────────────────────────────────────────────────

export const enforcementApi = {
  list: (params?: { city?: string; status?: string; ward_id?: string; page?: number }) =>
    get<PaginatedResponse<EnforcementAction>>(`/enforcement`, params as Record<string, unknown>),
  create: (data: CreateEnforcementAction) =>
    post<EnforcementAction>("/enforcement", data),
  update: (id: string, data: { status?: string; notes?: string; outcome_score?: number; evidence_urls?: string[] }) =>
    patch<EnforcementAction>(`/enforcement/${id}`, data),
  get: (id: string) => get<EnforcementAction>(`/enforcement/${id}`),
};

// ─── Alerts ───────────────────────────────────────────────────────────────────

export const alertsApi = {
  list: (params?: { city?: string; ward_id?: string; page?: number }) =>
    get<PaginatedResponse<CitizenAlert>>(`/alerts`, params as Record<string, unknown>),
  create: (data: CreateAlert) => post<CitizenAlert>("/alerts", data),
};

// ─── Analytics ────────────────────────────────────────────────────────────────

export const analyticsApi = {
  city: (city: string, days = 30) =>
    get<CityAnalytics>(`/analytics?city=${city}&days=${days}`),
  comparison: (cities: string[], days = 30) =>
    get<ComparisonData>(`/analytics/comparison?cities=${cities.join("&cities=")}&days=${days}`),
};

// ─── AI Assistant ─────────────────────────────────────────────────────────────

export const assistantApi = {
  chat: (message: string, city: string, history: { role: string; content: string }[]) =>
    post<AssistantResponse>("/assistant/chat", { message, city, conversation_history: history }),
};

// ─── Reports ──────────────────────────────────────────────────────────────────

export const reportsApi = {
  list: (city: string) => get<ReportItem[]>(`/reports?city=${city}`),
  exportPdf: (reportType: string, city: string, days: number) =>
    `/api/v1/reports/export?report_type=${reportType}&city=${city}&days=${days}`,
};

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface DashboardOverview {
  city: string;
  timestamp: string;
  active_stations: number;
  avg_aqi: number;
  max_aqi: number;
  max_aqi_ward: string | null;
  unhealthy_wards: number;
  active_alerts: number;
  pending_enforcements: number;
  anomalies_today: number;
  aqi_trend_24h: number;
  top_pollutant: string;
  air_quality_index_summary: Record<string, number>;
}

export interface Station {
  id: string;
  name: string;
  station_code: string;
  city: string;
  ward_id: string | null;
  latitude: number;
  longitude: number;
  is_active: boolean;
  station_type: string;
  last_data_at: string | null;
  maintenance_score: number;
}

export interface AQIReading {
  pm25: number | null;
  pm10: number | null;
  no2: number | null;
  co: number | null;
  o3: number | null;
  aqi: number | null;
  temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  wind_direction: number | null;
  timestamp: string;
  quality_flag: string;
}

export interface LiveAQIItem {
  station: Station;
  reading: AQIReading;
  aqi_category: string;
  health_message: string;
  trend: string;
}

export interface AQIHistoryPoint {
  bucket: string;
  pm25: number;
  pm10: number;
  aqi: number;
  no2: number;
  temperature: number;
  humidity: number;
  reading_count: number;
}

export interface ForecastItem {
  id: string;
  city: string;
  ward_id: string | null;
  forecast_timestamp: string;
  aqi_forecast: number;
  pm25_forecast: number | null;
  confidence_score: number;
  confidence_lower: number | null;
  confidence_upper: number | null;
  model_version: string;
  contributing_factors: Record<string, number> | null;
  feature_importance: Record<string, number> | null;
  aqi_category: string;
}

export interface WardForecastSummary {
  ward_id: string;
  city: string;
  current_aqi: number;
  forecasts: ForecastItem[];
  peak_aqi: number;
  peak_at: string;
  trend: string;
}

export interface Attribution {
  ward_id: string;
  city: string;
  timestamp: string;
  vehicular_pct: number;
  industrial_pct: number;
  construction_pct: number;
  biomass_pct: number;
  secondary_aerosol_pct: number;
  dust_pct: number;
  domestic_pct: number;
  overall_confidence: number;
  contributing_sources: Record<string, unknown> | null;
}

export interface EnforcementAction {
  id: string;
  officer_id: string;
  source_id: string | null;
  ward_id: string | null;
  city: string;
  action_type: string;
  status: string;
  priority_score: number;
  title: string;
  description: string | null;
  evidence_urls: string[] | null;
  latitude: number | null;
  longitude: number | null;
  outcome_score: number | null;
  resolved_at: string | null;
  ai_reasoning: Record<string, unknown> | null;
  created_at: string;
}

export interface CreateEnforcementAction {
  city: string;
  action_type: string;
  title: string;
  description?: string;
  ward_id?: string;
  latitude?: number;
  longitude?: number;
  priority_score?: number;
}

export interface CitizenAlert {
  id: string;
  ward_id: string;
  city: string;
  language: string;
  risk_level: string;
  message_title: string;
  message_text: string;
  aqi_value: number | null;
  sent_at: string | null;
  delivery_status: string;
  created_at: string;
}

export interface CreateAlert {
  ward_id: string;
  city: string;
  language?: string;
  risk_level: string;
  aqi_value?: number;
}

export interface CityAnalytics {
  city: string;
  period_days: number;
  aqi_trend: Array<{ day: string; avg_aqi: number; max_aqi: number; min_aqi: number }>;
  enforcement_summary: Array<{ action_type: string; status: string; count: number }>;
  anomaly_breakdown: Array<{ cause_category: string; count: number; avg_spike: number }>;
  intervention_outcomes: { avg_aqi_improvement: number | null; total_interventions: number | null };
  generated_at: string;
}

export interface ComparisonData {
  cities: Record<string, { avg_aqi: number; max_aqi: number; enforcement_actions: number }>;
  policies: Array<{ city: string; policy_type: string; impact_score: number; aqi_delta: number; implemented_at: string }>;
  period_days: number;
}

export interface AssistantResponse {
  answer: string;
  confidence_score: number;
  data_sources: string[];
  map_data: { type: string; city: string; points: Array<{ ward_id: string; station: string; aqi: number }> } | null;
  supporting_evidence: Array<{ type: string; station: string; aqi: number; timestamp: string }>;
  reasoning_trace: string;
}

export interface ReportItem {
  id: string;
  type: string;
  title: string;
  city: string;
  ward_id: string | null;
  status: string;
  officer: string;
  priority_score: number;
  created_at: string | null;
  resolved_at: string | null;
}

// ─── GIS ──────────────────────────────────────────────────────────────────────

export const gisApi = {
  wardBoundaries: (city: string) => get<Record<string, unknown>>(`/gis/ward-boundaries?city=${city}`),
  bufferAnalysis: (lat: number, lon: number, radiusKm: number) =>
    get<Record<string, unknown>>(`/gis/buffer-analysis?latitude=${lat}&longitude=${lon}&radius_km=${radiusKm}`),
  routeOptimise: (officerLat: number, officerLon: number, city: string) =>
    get<RouteResult>(`/gis/route-optimise?officer_lat=${officerLat}&officer_lon=${officerLon}&city=${city}`),
  hotspotClusters: (city: string, radiusKm = 2.0) =>
    get<HotspotCluster[]>(`/gis/hotspot-clusters?city=${city}&radius_km=${radiusKm}`),
};

// ─── Simulator ────────────────────────────────────────────────────────────────

export const simulatorApi = {
  scenarios: () => get<ScenarioInfo[]>("/simulator/scenarios"),
  whatif: (data: { city: string; scenario: string; ward_id?: string; custom_reduction_pct?: number }) =>
    post<SimulationResult>("/simulator/whatif", data),
  digitalTwin: (city: string, wardId: string, windSpeed?: number, windDir?: number, emissionRate?: number) =>
    get<DigitalTwinResult>(`/simulator/twin/dispersion?city=${city}&ward_id=${wardId}${windSpeed != null ? `&wind_speed=${windSpeed}` : ""}${windDir != null ? `&wind_direction=${windDir}` : ""}${emissionRate != null ? `&emission_rate_kg_hr=${emissionRate}` : ""}`),
};

// ─── Agents ───────────────────────────────────────────────────────────────────

export const agentsApi = {
  run: (city: string, query?: string, wardId?: string, agentList?: string[]) => {
    const params = new URLSearchParams({ city });
    if (query) params.append("query", query);
    if (wardId) params.append("ward_id", wardId);
    if (agentList) agentList.forEach((a) => params.append("agents", a));
    return post<AgentPipelineResult>(`/agents/run?${params}`);
  },
  status: (city: string) => get<AgentStatusResult>(`/agents/status?city=${city}`),
  modelRegistry: () => get<ModelVersion[]>("/agents/model-registry"),
  carbonEstimate: (city: string) => get<CarbonEstimate>(`/agents/carbon-estimate?city=${city}`),
  enforcementCarbonImpact: (sourceType: string, actionType: string, days: number) =>
    get<CarbonEnforcementImpact>(`/agents/carbon-estimate/enforcement?source_type=${sourceType}&action_type=${actionType}&duration_days=${days}`),
};

// ─── Replay ───────────────────────────────────────────────────────────────────

export const replayApi = {
  aqiHistory: (city: string, hours = 24, intervalMin = 30) =>
    get<ReplayFrame[]>(`/replay/aqi-history?city=${city}&hours=${hours}&interval_minutes=${intervalMin}`),
  rootCauseTimeline: (anomalyId: string) =>
    get<RootCauseTimeline>(`/replay/root-cause-timeline/${anomalyId}`),
  anomalies: (city: string, hours = 48, resolved?: boolean) =>
    get<AnomalyEvent[]>(`/replay/anomalies?city=${city}&hours=${hours}${resolved != null ? `&resolved=${resolved}` : ""}`),
};

// ─── Additional Types ─────────────────────────────────────────────────────────

export interface RouteResult {
  waypoints: Array<{ name: string; ward_id: string; latitude: number; longitude: number; priority: number; distance_from_prev_km: number }>;
  total_distance_km: number;
  estimated_duration_min: number;
  optimisation_score: number;
  algorithm: string;
  waypoint_count: number;
}

export interface HotspotCluster {
  centroid: { latitude: number; longitude: number };
  members: Array<{ name: string; source_type: string; violation_count: number }>;
  member_count: number;
  total_violations: number;
  dominant_type: string;
  ward_ids: string[];
  priority_score: number;
}

export interface ScenarioInfo {
  key: string;
  description: string;
  target_source: string;
  reduction_pct: number;
  time_to_effect_hours: number;
}

export interface SimulationResult {
  scenario: string;
  baseline_aqi: number;
  simulated_aqi: number;
  aqi_delta: number;
  pm25_delta: number;
  confidence: number;
  affected_wards: string[];
  co2_impact_kg_day: number;
  time_to_effect_hours: number;
  reasoning: string;
  dispersion_map: Array<{ latitude: number; longitude: number; aqi_delta: number }>;
}

export interface DigitalTwinResult {
  source: { ward_id: string; latitude: number; longitude: number };
  parameters: { wind_speed_ms: number; wind_direction_deg: number; emission_rate_kg_hr: number; model: string };
  grid_points: Array<{ latitude: number; longitude: number; concentration_ug_m3: number; aqi_contribution: number }>;
}

export interface AgentPipelineResult {
  session_id: string;
  city: string;
  overall_confidence: number;
  confidence_scores: Record<string, number>;
  reasoning_traces: Record<string, string>;
  supporting_evidence: Array<Record<string, unknown>>;
  data_sources: string[];
  errors: string[];
  agents_executed: string[];
  ingestion: { success: boolean; data: Record<string, unknown> } | null;
  forecast: { success: boolean; data: Record<string, unknown> } | null;
  attribution: { success: boolean; data: Record<string, unknown> } | null;
  enforcement: { success: boolean; data: Record<string, unknown> } | null;
  advisory: { success: boolean; data: Record<string, unknown> } | null;
  policy: { success: boolean; data: Record<string, unknown> } | null;
  generated_at: string;
}

export interface AgentStatusResult {
  city: string;
  agents: Record<string, { status: string; last_run_min_ago?: number; schedule: string; active_anomalies?: number }>;
}

export interface ModelVersion {
  version: string;
  trained_at: string;
  path: string;
  is_active: boolean;
  feature_names: string[];
}

export interface CarbonEstimate {
  city: string;
  total_co2_kg_per_day: number;
  total_co2_ton_per_year: number;
  total_pm25_kg_per_day: number;
  source_breakdown: Record<string, { co2_kg_per_day: number; share_pct: number; methodology: string }>;
  reduction_scenarios: Array<{ scenario: string; co2_reduction_kg_day: number; aqi_delta_estimate: number; feasibility: string }>;
}

export interface CarbonEnforcementImpact {
  source_type: string;
  action_type: string;
  duration_days: number;
  co2_saved_kg: number;
  pm25_saved_kg: number;
  estimated_aqi_delta: number;
  reduction_pct: number;
}

export interface ReplayFrame {
  timestamp: string;
  wards: Record<string, { aqi: number; pm25: number; max_aqi: number }>;
}

export interface RootCauseTimeline {
  anomaly: {
    id: string; ward_id: string; station: string; detected_at: string;
    aqi_spike: number; baseline_aqi: number; cause: string; confidence: number; is_resolved: boolean;
  };
  root_cause_timeline: Record<string, unknown>;
  contributing_sources: Record<string, unknown>;
  lead_up_readings: Array<{ timestamp: string; aqi: number; pm25: number; wind_speed: number }>;
  attribution_at_spike: Record<string, unknown> | null;
}

export interface AnomalyEvent {
  id: string;
  ward_id: string;
  city: string;
  detected_at: string;
  aqi_spike_value: number;
  baseline_aqi: number;
  probable_cause: string;
  cause_category: string;
  confidence_score: number;
  is_resolved: boolean;
  station_name: string;
}
