import axios from "axios";
import { get, post, patch, del, BASE_URL } from "./client";

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

// ─── System / Transparency ──────────────────────────────────────────────────────

export interface ProviderStatus {
  configured: boolean;
  note: string;
}

export interface DataSourcesStatus {
  air_quality: ProviderStatus;
  weather: ProviderStatus;
  satellite_fire: ProviderStatus;
  satellite_imagery: ProviderStatus;
  traffic: ProviderStatus;
  database_engine: string;
}

export interface HealthCheckResponse {
  status: "healthy" | "degraded";
  checks: Record<string, string>;
  version: string;
}

export const systemApi = {
  dataSources: () => get<DataSourcesStatus>(`/system/data-sources`),
  health: async (): Promise<HealthCheckResponse> => {
    const res = await axios.get(`${BASE_URL}/health`, { timeout: 10000, validateStatus: () => true });
    return res.data;
  },
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
  healthRisk: (params: { city?: string; ward_id?: string; station_id?: string }) =>
    get<HealthRiskAssessment>(`/aqi/health-risk`, params as Record<string, unknown>),
  recommendLocations: (params: {
    latitude: number;
    longitude: number;
    city: string;
    radius_km?: number;
    limit?: number;
  }) => get<LocationRecommendation[]>(`/aqi/recommend-locations`, params as Record<string, unknown>),
  routeAnalysis: (params: {
    origin_lat: number;
    origin_lon: number;
    dest_lat: number;
    dest_lon: number;
    city: string;
    num_samples?: number;
  }) => get<RouteAnalysis>(`/aqi/route-analysis`, params as Record<string, unknown>),
  trafficPollution: (params: { city: string; ward_id?: string; hours?: number }) =>
    get<TrafficPollutionAnalysis>(`/aqi/traffic-pollution`, params as Record<string, unknown>),
};

// ─── Forecast ─────────────────────────────────────────────────────────────────

export const forecastApi = {
  city: (city: string, hoursAhead = 24) =>
    get<ForecastItem[]>(`/forecast?city=${city}&hours_ahead=${hoursAhead}`),
  ward: (wardId: string, city: string, live = false) =>
    get<WardForecastSummary>(`/forecast/${wardId}?city=${city}${live ? "&live=true" : ""}`),
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

// ─── Mitigation Recommendations ────────────────────────────────────────────────

export interface RecommendedAction {
  action: string;
  target_source: string;
  rationale: string;
  simulation_scenario_key: string | null;
}

export interface MitigationRecommendation {
  ward_id: string | null;
  city: string;
  aqi: number | null;
  primary_pollutant: string | null;
  overall_risk: RiskLevel;
  contributing_factors: string[];
  recommended_actions: RecommendedAction[];
  impact_disclaimer: string;
  attribution_confidence: number | null;
  attribution_timestamp: string | null;
}

export const mitigationApi = {
  recommendations: (params: { city: string; ward_id?: string }) =>
    get<MitigationRecommendation>(`/mitigation/recommendations`, params as Record<string, unknown>),
};

// ─── Population Exposure ───────────────────────────────────────────────────────

export type ExposureLevel = "low" | "moderate" | "high" | "very_high" | "unavailable";
export type PopulationBand = "low" | "moderate" | "high";

export interface ExposureScore {
  ward_id: string;
  aqi: number | null;
  pollution_risk: RiskLevel;
  primary_pollutant: string | null;
  population: number | null;
  population_band: PopulationBand | null;
  sensitive_sites_count: number | null;
  exposure_level: ExposureLevel;
  is_population_data_configured: boolean;
}

export interface ExposureMap {
  city: string;
  scores: ExposureScore[];
  methodology: string;
  wards_missing_population_data: string[];
}

export interface WardDemographics {
  id: string;
  city: string;
  ward_id: string;
  population: number | null;
  sensitive_sites_count: number | null;
  green_cover_pct: number | null;
  source_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateWardDemographics {
  city: string;
  ward_id: string;
  population?: number | null;
  sensitive_sites_count?: number | null;
  green_cover_pct?: number | null;
  source_note?: string | null;
}

export interface UpdateWardDemographics {
  population?: number | null;
  sensitive_sites_count?: number | null;
  green_cover_pct?: number | null;
  source_note?: string | null;
}

export const exposureApi = {
  map: (city: string) => get<ExposureMap>(`/exposure/map?city=${encodeURIComponent(city)}`),
  listDemographics: (city: string) =>
    get<WardDemographics[]>(`/exposure/demographics?city=${encodeURIComponent(city)}`),
  createDemographics: (data: CreateWardDemographics) =>
    post<WardDemographics>(`/exposure/demographics`, data),
  updateDemographics: (id: string, data: UpdateWardDemographics) =>
    patch<WardDemographics>(`/exposure/demographics/${id}`, data),
};

// ─── Construction & Dust Intelligence ──────────────────────────────────────────

export type DustRiskLevel = "low" | "moderate" | "high";

export interface ConstructionDustSite {
  source_id: string;
  source_name: string;
  source_type: string;
  ward_id: string | null;
  latitude: number;
  longitude: number;
  permit_status: string;
  violation_count: number;
  last_inspected_at: string | null;
  nearest_station_name: string | null;
  nearest_station_distance_km: number | null;
  pm10: number | null;
  risk_level: DustRiskLevel;
  supporting_observations: string[];
  requires_verification: boolean;
}

export interface ConstructionDustReport {
  city: string;
  sites: ConstructionDustSite[];
  disclaimer: string;
}

export const constructionDustApi = {
  risk: (city: string) => get<ConstructionDustReport>(`/sources/construction-dust-risk?city=${encodeURIComponent(city)}`),
};

// ─── Green Infrastructure Optimization ─────────────────────────────────────────

export type GreenPriority = "low" | "moderate" | "high";
export type InterventionType = "roadside_green_buffer" | "urban_forest_or_park" | "general_tree_planting";

export interface GreenInfrastructureScore {
  ward_id: string;
  aqi: number | null;
  pollution_risk: RiskLevel;
  exposure_level: ExposureLevel;
  traffic_level: TrafficLevel;
  green_cover_pct: number | null;
  is_green_cover_configured: boolean;
  priority: GreenPriority;
  priority_score: number;
  recommended_intervention: InterventionType;
  rationale: string[];
}

export interface GreenInfrastructureReport {
  city: string;
  scores: GreenInfrastructureScore[];
  methodology: string;
  impact_disclaimer: string;
  wards_missing_green_cover_data: string[];
}

export const greenInfrastructureApi = {
  priority: (city: string) => get<GreenInfrastructureReport>(`/green-infrastructure/priority?city=${encodeURIComponent(city)}`),
};

// ─── Waste-Burning & Circular Economy Intelligence ─────────────────────────────

export type WasteBurningConfidence = "none" | "low" | "moderate" | "high";

export interface WasteBurningEvent {
  ward_id: string | null;
  station_name: string | null;
  current_pm25: number | null;
  baseline_pm25: number | null;
  detected: string;
  supporting_observations: string[];
  confidence: WasteBurningConfidence;
  status: string;
  circular_economy_recommendations: string[];
}

export interface WasteBurningReport {
  city: string;
  events: WasteBurningEvent[];
  satellite_configured: boolean;
  disclaimer: string;
}

export const wasteBurningApi = {
  events: (city: string) => get<WasteBurningReport>(`/waste-burning/events?city=${encodeURIComponent(city)}`),
};

// ─── Smart Mobility Intelligence (Route Comparison) ────────────────────────────

export interface RouteWaypoint {
  latitude: number;
  longitude: number;
}

export interface RouteCandidateInput {
  name: string;
  waypoints: RouteWaypoint[];
  duration_minutes?: number | null;
}

export interface CompareRoutesRequest {
  city: string;
  routes: RouteCandidateInput[];
  num_samples?: number;
}

export interface RouteExposureResult {
  name: string;
  total_distance_km: number;
  duration_minutes: number | null;
  estimated_aqi_exposure: number | null;
  peak_aqi: number | null;
  samples_used: number;
  freshness_summary: string;
}

export interface RouteComparison {
  routes: RouteExposureResult[];
  recommended_route_name: string | null;
  recommendation_text: string;
  routing_data_source: string;
  exposure_disclaimer: string;
}

export const smartMobilityApi = {
  compareRoutes: (data: CompareRoutesRequest) => post<RouteComparison>(`/aqi/compare-routes`, data),
};

// ─── Industrial Pollution Intelligence ─────────────────────────────────────────

export type DeviationLevel = "normal" | "moderate" | "significant";

export interface IndustrialZone {
  source_id: string;
  source_name: string;
  ward_id: string | null;
  latitude: number;
  longitude: number;
  permit_status: string;
  violation_count: number;
  current_aqi: number | null;
  current_risk: RiskLevel;
  historical_baseline_aqi: number | null;
  deviation_level: DeviationLevel;
  status: string;
  possible_contributing_source: boolean;
  supporting_observations: string[];
}

export interface IndustrialPollutionReport {
  city: string;
  zones: IndustrialZone[];
  disclaimer: string;
}

export const industrialPollutionApi = {
  risk: (city: string) => get<IndustrialPollutionReport>(`/sources/industrial-risk?city=${encodeURIComponent(city)}`),
};

// ─── Alerts ───────────────────────────────────────────────────────────────────

export const alertsApi = {
  list: (params?: { city?: string; ward_id?: string; page?: number }) =>
    get<PaginatedResponse<CitizenAlert>>(`/alerts`, params as Record<string, unknown>),
  create: (data: CreateAlert) => post<CitizenAlert>("/alerts", data),
};

// ─── Alert Thresholds ──────────────────────────────────────────────────────────

export const alertThresholdsApi = {
  list: (city: string) =>
    get<AlertThreshold[]>(`/alerts/thresholds?city=${encodeURIComponent(city)}`),
  create: (data: CreateAlertThreshold) =>
    post<AlertThreshold>(`/alerts/thresholds`, data),
  update: (id: string, data: UpdateAlertThreshold) =>
    patch<AlertThreshold>(`/alerts/thresholds/${id}`, data),
  remove: (id: string) => del<null>(`/alerts/thresholds/${id}`),
};

// ─── Analytics ────────────────────────────────────────────────────────────────

export const analyticsApi = {
  city: (city: string, days = 30) =>
    get<CityAnalytics>(`/analytics?city=${city}&days=${days}`),
  comparison: (
    cities: string[],
    days = 30,
    customRange?: { start: string; end: string },
  ) =>
    get<ComparisonData>(
      `/analytics/comparison?cities=${cities.join("&cities=")}&days=${days}` +
        (customRange
          ? `&start_date=${customRange.start}&end_date=${customRange.end}`
          : ""),
    ),
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
  /** "openaq" = real ground-station reading, "synthetic" = statistical fallback (no live provider data available for this station). */
  data_source: "openaq" | "synthetic";
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

export type RiskLevel = "low" | "moderate" | "high" | "very_high";

export interface PollutantRisk {
  pollutant: string;
  label: string;
  value: number;
  unit: string;
  risk_level: RiskLevel;
  reason: string;
}

export interface HealthRiskAssessment {
  overall_risk: RiskLevel;
  aqi: number | null;
  station_id: string | null;
  ward_id: string | null;
  pollutant_risks: PollutantRisk[];
  precautions: string[];
  sensitive_group_note: string;
  generated_at: string;
  is_estimate: boolean;
  disclaimer: string;
}

export type FreshnessStatus = "live" | "recent" | "stale" | "demo" | "unavailable";

export interface LocationRecommendation {
  rank: number;
  station_id: string;
  station_name: string;
  ward_id: string | null;
  latitude: number;
  longitude: number;
  distance_km: number;
  aqi: number | null;
  aqi_category: string | null;
  freshness: FreshnessStatus;
  reason: string;
  observed_at: string | null;
}

export interface RouteSample {
  sequence: number;
  latitude: number;
  longitude: number;
  distance_from_origin_km: number;
  nearest_station_name: string | null;
  nearest_station_distance_km: number | null;
  aqi: number | null;
  aqi_category: string | null;
  freshness: FreshnessStatus;
  observed_at: string | null;
}

export interface RouteAnalysis {
  total_distance_km: number;
  samples: RouteSample[];
  average_aqi: number | null;
  peak_aqi: number | null;
  peak_sample_index: number | null;
  overall_exposure: "low" | "moderate" | "high" | "very_high" | "unknown";
  high_pollution_segments: number[];
  alternative_route_note: string;
  routing_data_source: string;
  data_disclaimer: string;
}

export type TrafficLevel = "low" | "moderate" | "high";
export type TrafficDataSource = "demo" | "csv";

export interface TrafficPeriodStats {
  traffic_level: TrafficLevel;
  reading_count: number;
  avg_aqi: number | null;
  avg_pm25: number | null;
  avg_pm10: number | null;
  avg_no2: number | null;
}

export interface TrafficPollutionAnalysis {
  city: string;
  ward_id: string | null;
  window_hours: number;
  period_stats: TrafficPeriodStats[];
  high_vs_low_aqi_ratio: number | null;
  observation: string;
  traffic_data_source: TrafficDataSource;
  traffic_data_note: string;
  sample_size: number;
}

export interface ForecastItem {
  id: string;
  city: string;
  ward_id: string | null;
  forecast_timestamp: string;
  generated_at: string;
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

export type ThresholdMetric = "aqi" | "pm25" | "pm10" | "no2" | "co" | "o3" | "so2";

export interface AlertThreshold {
  id: string;
  city: string;
  alert_type: ThresholdMetric;
  threshold_value: number;
  cooldown_minutes: number;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateAlertThreshold {
  city: string;
  alert_type: ThresholdMetric;
  threshold_value: number;
  cooldown_minutes?: number;
  is_enabled?: boolean;
}

export interface UpdateAlertThreshold {
  threshold_value?: number;
  cooldown_minutes?: number;
  is_enabled?: boolean;
}

export interface CityAnalytics {
  city: string;
  period_days: number;
  aqi_trend: Array<{ day: string; avg_aqi: number; max_aqi: number; min_aqi: number }>;
  recent_p95_aqi: number | null;
  enforcement_summary: Array<{ action_type: string; status: string; count: number }>;
  anomaly_breakdown: Array<{ cause_category: string; count: number; avg_spike: number }>;
  intervention_outcomes: {
    avg_aqi_improvement: number | null;
    total_interventions: number | null;
    avg_carbon_saved: number | null;
  };
  generated_at: string;
}

export interface CityComparisonEntry {
  has_data: boolean;
  current_aqi: number | null;
  avg_aqi: number | null;
  max_aqi: number | null;
  min_aqi: number | null;
  avg_pm25: number | null;
  avg_pm10: number | null;
  avg_no2: number | null;
  avg_so2: number | null;
  avg_o3: number | null;
  trend: "worsening" | "improving" | "stable" | null;
  unhealthy_days: number;
  active_hotspots: number;
  enforcement_actions: number;
}

export interface ComparisonData {
  cities: Record<string, CityComparisonEntry>;
  policies: Array<{ city: string; policy_type: string; impact_score: number; aqi_delta: number; implemented_at: string | null }>;
  period_days: number;
  period_start: string;
  period_end: string;
  generated_at: string;
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
  resolved_at: string | null;
  station_name: string;
  latitude: number;
  longitude: number;
  severity: "moderate" | "high" | "severe" | "critical";
  pollutant: string;
  observed_value: number;
  expected_value: number;
  anomaly_score: number;
  detection_method: string;
}

// ─── Model Performance ────────────────────────────────────────────────────────

export interface ModelPerformanceRecord {
  model_version: string;
  model_name: string;
  target: string;
  city: string;
  trained_at: string;
  training_period_start: string;
  training_period_end: string;
  test_sample_count: number;
  features: string[];
  is_active: boolean;
  mae: number;
  rmse: number;
  r2: number;
  mape: number | null;
}

export const modelPerformanceApi = {
  history: (city: string, target = "aqi") =>
    get<ModelPerformanceRecord[]>(`/model-performance/history?city=${city}&target=${target}`),
  active: (city: string, target = "aqi") =>
    get<ModelPerformanceRecord | null>(`/model-performance/active?city=${city}&target=${target}`),
};

// ─── Traffic (Demo) ───────────────────────────────────────────────────────────

export interface TrafficReading {
  road_name: string;
  latitude: number;
  longitude: number;
  traffic_level: number;
  congestion_category: "free_flow" | "light" | "moderate" | "heavy" | "gridlock";
  is_simulated: boolean;
  timestamp: string;
}

export interface TrafficCorrelation {
  city: string;
  is_simulated: boolean;
  correlation_coefficient: number | null;
  strength: "insufficient_data" | "weak" | "moderate" | "strong";
  sample_count: number;
  insight: string;
  samples: Array<{ traffic_level: number; aqi: number }>;
}

export const trafficApi = {
  current: (city: string) => get<TrafficReading[]>(`/traffic/current?city=${city}`),
  correlation: (city: string, hours = 720) =>
    get<TrafficCorrelation>(`/traffic/correlation?city=${city}&hours=${hours}`),
};

// ─── Pollution Hotspots ───────────────────────────────────────────────────────

export interface PollutionHotspot {
  centroid_latitude: number;
  centroid_longitude: number;
  avg_aqi: number;
  peak_aqi: number;
  point_count: number;
  dominant_pollutant: string | null;
  approx_radius_m: number;
  trend: "worsening" | "improving" | "stable";
  aqi_category: string;
}

export const pollutionHotspotsApi = {
  list: (city: string, radiusKm = 1.5) =>
    get<PollutionHotspot[]>(`/gis/pollution-hotspots?city=${city}&radius_km=${radiusKm}`),
};

// ─── Anomalies (map/replay) ────────────────────────────────────────────────────

export const anomaliesApi = {
  list: (
    city: string,
    hours = 48,
    minSeverity?: string,
    pollutant?: string,
    resolved?: boolean,
  ) =>
    get<AnomalyEvent[]>(
      `/replay/anomalies?city=${city}&hours=${hours}` +
        (minSeverity ? `&min_severity=${minSeverity}` : "") +
        (pollutant ? `&pollutant=${pollutant}` : "") +
        (resolved != null ? `&resolved=${resolved}` : ""),
    ),
};
