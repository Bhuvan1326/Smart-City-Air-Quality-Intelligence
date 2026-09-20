import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchAllIndiaAQIObservations,
  isValidCoordinate,
  observationsWithAqiIntensity,
  observationsWithValidCoordinates,
  escapeHtml,
  freshnessLabel,
  markerDiameterForZoom,
  MAX_INDIA_AQI_PAGE_SIZE,
} from "../lib/india-aqi.ts";

function makeObservation(overrides = {}) {
  return {
    station_id: "s1",
    station_name: "Test Station",
    station_code: "OPENAQ_IN_1",
    station_type: "OpenAQ",
    openaq_location_id: 1,
    city: "Delhi",
    state: null,
    country: "India",
    latitude: 28.6,
    longitude: 77.2,
    aqi: 120,
    aqi_category: "Moderate",
    aqi_method: "CPCB_PM25_NAAQS_INTERPOLATED",
    pm25: 55,
    pm10: 90,
    no2: 30,
    so2: 10,
    co: 1.2,
    o3: 25,
    observed_at: new Date().toISOString(),
    fetched_at: new Date().toISOString(),
    data_source: "openaq",
    quality_flag: "good",
    freshness: "live",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// fetchAllIndiaAQIObservations — pagination must walk every page, not stop
// at page 1 or an arbitrary station count (the bug this replaces capped the
// India AQI page at 200 stations / six curated Pune stations).
// ---------------------------------------------------------------------------

test("fetchAllIndiaAQIObservations walks every page until the API reports no more", async () => {
  const pages = [
    { items: [makeObservation({ station_id: "a" }), makeObservation({ station_id: "b" })], total: 5, page: 1, page_size: 2, pages: 3 },
    { items: [makeObservation({ station_id: "c" }), makeObservation({ station_id: "d" })], total: 5, page: 2, page_size: 2, pages: 3 },
    { items: [makeObservation({ station_id: "e" })], total: 5, page: 3, page_size: 2, pages: 3 },
  ];
  let calls = 0;
  const fetchPage = async (params) => {
    assert.equal(params.page, calls + 1);
    return pages[calls++];
  };

  const all = await fetchAllIndiaAQIObservations(fetchPage, {}, 2);

  assert.equal(calls, 3);
  assert.deepEqual(
    all.map((o) => o.station_id),
    ["a", "b", "c", "d", "e"],
  );
});

test("fetchAllIndiaAQIObservations stops as soon as a short page comes back", async () => {
  let calls = 0;
  const fetchPage = async () => {
    calls += 1;
    return { items: [makeObservation({ station_id: "only" })], total: 1, page: 1, page_size: 200, pages: 1 };
  };

  const all = await fetchAllIndiaAQIObservations(fetchPage, {}, 200);

  assert.equal(calls, 1);
  assert.equal(all.length, 1);
});

test("fetchAllIndiaAQIObservations dedupes a station id seen on more than one page", async () => {
  const pages = [
    { items: [makeObservation({ station_id: "dup" }), makeObservation({ station_id: "b" })], total: 3, page: 1, page_size: 2, pages: 2 },
    { items: [makeObservation({ station_id: "dup" })], total: 3, page: 2, page_size: 2, pages: 2 },
  ];
  let calls = 0;
  const fetchPage = async () => pages[calls++];

  const all = await fetchAllIndiaAQIObservations(fetchPage, {}, 2);

  assert.equal(all.filter((o) => o.station_id === "dup").length, 1);
});

test("fetchAllIndiaAQIObservations passes filters through on every page", async () => {
  const seenParams = [];
  const fetchPage = async (params) => {
    seenParams.push(params);
    return { items: [], total: 0, page: params.page, page_size: params.page_size, pages: 1 };
  };

  await fetchAllIndiaAQIObservations(fetchPage, { state: "Maharashtra", source: "openaq" }, 50);

  assert.equal(seenParams.length, 1);
  assert.equal(seenParams[0].state, "Maharashtra");
  assert.equal(seenParams[0].source, "openaq");
  assert.ok(seenParams[0].page_size <= MAX_INDIA_AQI_PAGE_SIZE);
});

// ---------------------------------------------------------------------------
// Coordinate validation / heatmap intensity filtering
// ---------------------------------------------------------------------------

test("isValidCoordinate accepts real coordinates and rejects out-of-range/NaN/missing", () => {
  assert.equal(isValidCoordinate(28.6, 77.2), true);
  assert.equal(isValidCoordinate(-90, -180), true);
  assert.equal(isValidCoordinate(91, 0), false);
  assert.equal(isValidCoordinate(0, 181), false);
  assert.equal(isValidCoordinate(Number.NaN, 0), false);
  assert.equal(isValidCoordinate(null, undefined), false);
});

test("observationsWithAqiIntensity excludes unavailable stations instead of coercing aqi to 0", () => {
  const observations = [
    makeObservation({ station_id: "has-reading", aqi: 150 }),
    makeObservation({ station_id: "unavailable", aqi: null, freshness: "unavailable" }),
  ];

  const withIntensity = observationsWithAqiIntensity(observations);

  assert.equal(withIntensity.length, 1);
  assert.equal(withIntensity[0].station_id, "has-reading");
  assert.ok(withIntensity.every((o) => o.aqi !== 0 || o.station_id === "has-reading"));
});

test("observationsWithAqiIntensity excludes a station with an invalid coordinate even if it has a reading", () => {
  const observations = [makeObservation({ station_id: "bad-coords", latitude: 999, aqi: 150 })];
  assert.equal(observationsWithAqiIntensity(observations).length, 0);
});

test("observationsWithValidCoordinates keeps unavailable stations (for markers), unlike observationsWithAqiIntensity", () => {
  const observations = [makeObservation({ station_id: "unavailable", aqi: null, freshness: "unavailable" })];
  assert.equal(observationsWithValidCoordinates(observations).length, 1);
  assert.equal(observationsWithAqiIntensity(observations).length, 0);
});

// ---------------------------------------------------------------------------
// HTML escaping — station metadata is OpenAQ (third-party) data and must
// never be interpolated into a Mapbox popup unescaped.
// ---------------------------------------------------------------------------

test("escapeHtml neutralizes script/tag injection in station metadata", () => {
  const malicious = `<img src=x onerror="alert('xss')">`;
  const escaped = escapeHtml(malicious);
  assert.ok(!escaped.includes("<img"));
  assert.ok(!escaped.includes('"'));
  assert.equal(escaped, "&lt;img src=x onerror=&quot;alert(&#39;xss&#39;)&quot;&gt;");
});

test("escapeHtml handles null/undefined safely", () => {
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
});

test("escapeHtml leaves ordinary station names unchanged", () => {
  assert.equal(escapeHtml("Alandi, Pune"), "Alandi, Pune");
});

// ---------------------------------------------------------------------------
// Freshness labeling
// ---------------------------------------------------------------------------

test("freshnessLabel covers every backend freshness status", () => {
  assert.equal(freshnessLabel("live"), "Live");
  assert.equal(freshnessLabel("recent"), "Recent");
  assert.equal(freshnessLabel("stale"), "Stale");
  assert.equal(freshnessLabel("unavailable"), "Unavailable");
});

// ---------------------------------------------------------------------------
// Marker sizing — country-wide zoom levels must render substantially
// smaller circles than city/station-level zoom, so hundreds of India-wide
// stations don't overlap into an unreadable mass at the default zoom.
// ---------------------------------------------------------------------------

test("markerDiameterForZoom shrinks circles at country-level zoom", () => {
  const countryZoom = markerDiameterForZoom(4.2); // INDIA_DEFAULT_ZOOM
  assert.ok(countryZoom < 40, "must be smaller than the old fixed 40px circle");
  assert.ok(countryZoom >= 14, "must stay large enough to remain clickable");
});

test("markerDiameterForZoom grows as the person zooms in", () => {
  const country = markerDiameterForZoom(4);
  const city = markerDiameterForZoom(9);
  const station = markerDiameterForZoom(13);
  assert.ok(country < city);
  assert.ok(city < station);
});

test("markerDiameterForZoom never returns a diameter too small to click", () => {
  for (const zoom of [0, 2, 4, 5]) {
    assert.ok(markerDiameterForZoom(zoom) >= 14);
  }
});
