-- Pune live station verification. The eight canonical codes are the ones in
-- app/services/aqi_providers/pune_stations.py (REQUIRED_STATIONS).

-- 1. Current Pune live station count. Expected: 8 once every station has
--    been resolved through OpenAQ (fewer means some are still unresolved).
SELECT COUNT(*) AS current_pune_live_stations
FROM monitoring_stations
WHERE station_code IN (
        'PUNE_LIVE_SPPU', 'PUNE_LIVE_DHANKAWADI', 'PUNE_LIVE_HADAPSAR',
        'PUNE_LIVE_NIGDI', 'PUNE_LIVE_PARK_STREET_WAKAD',
        'PUNE_LIVE_KATRAJ_DAIRY', 'PUNE_LIVE_GAVALINAGAR',
        'PUNE_LIVE_BHUMKAR_NAGAR'
      )
  AND is_active = true
  AND is_deleted = false;


-- 2. Current Pune live station list.
SELECT station_code, name, city, state, country, station_type,
       openaq_location_id, latitude, longitude, ward_id, last_data_at
FROM monitoring_stations
WHERE station_code IN (
        'PUNE_LIVE_SPPU', 'PUNE_LIVE_DHANKAWADI', 'PUNE_LIVE_HADAPSAR',
        'PUNE_LIVE_NIGDI', 'PUNE_LIVE_PARK_STREET_WAKAD',
        'PUNE_LIVE_KATRAJ_DAIRY', 'PUNE_LIVE_GAVALINAGAR',
        'PUNE_LIVE_BHUMKAR_NAGAR'
      )
  AND is_active = true
  AND is_deleted = false
ORDER BY station_code;


-- 3. and 4. Alandi and Karve Road must not be active. Expected: zero rows
--    with is_active = true (rows may exist as inactive history).
SELECT station_code, name, openaq_location_id, is_active
FROM monitoring_stations
WHERE (station_code IN ('PUNE_LIVE_ALANDI', 'PUNE_LIVE_KARVE_ROAD')
       OR openaq_location_id IN (12042, 5661))
ORDER BY station_code;

SELECT COUNT(*) AS active_retired_stations
FROM monitoring_stations
WHERE (station_code IN ('PUNE_LIVE_ALANDI', 'PUNE_LIVE_KARVE_ROAD')
       OR openaq_location_id IN (12042, 5661))
  AND is_active = true;


-- 5. The four new stations exist. Expected: 4 rows once discovery has
--    resolved them; a missing code means OpenAQ could not verify it.
SELECT station_code, name, openaq_location_id, latitude, longitude, is_active
FROM monitoring_stations
WHERE station_code IN (
        'PUNE_LIVE_PARK_STREET_WAKAD', 'PUNE_LIVE_KATRAJ_DAIRY',
        'PUNE_LIVE_GAVALINAGAR', 'PUNE_LIVE_BHUMKAR_NAGAR'
      )
ORDER BY station_code;


-- 6. Every current station has an OpenAQ location id. Expected: 0 rows.
SELECT station_code, name
FROM monitoring_stations
WHERE station_code LIKE 'PUNE_LIVE_%'
  AND is_active = true
  AND is_deleted = false
  AND openaq_location_id IS NULL;


-- 7. No duplicate OpenAQ location ids. Expected: 0 rows.
SELECT openaq_location_id, COUNT(*) AS station_rows
FROM monitoring_stations
WHERE openaq_location_id IS NOT NULL
GROUP BY openaq_location_id
HAVING COUNT(*) > 1;


-- 8. Every current station has coordinates. Expected: 0 rows.
SELECT station_code, name
FROM monitoring_stations
WHERE station_code LIKE 'PUNE_LIVE_%'
  AND is_active = true
  AND is_deleted = false
  AND (latitude IS NULL OR longitude IS NULL OR geometry IS NULL);


-- 9. Latest reading per current station. A NULL reading_timestamp means no
--    observation has been stored yet (never shown as AQI 0).
SELECT s.station_code, s.name, r.timestamp AS reading_timestamp,
       r.aqi, r.pm25, r.pm10, r.quality_flag
FROM monitoring_stations s
LEFT JOIN LATERAL (
    SELECT timestamp, aqi, pm25, pm10, quality_flag
    FROM aqi_readings
    WHERE station_id = s.id
      AND is_deleted = false
      AND quality_flag NOT IN ('invalid', 'synthetic')
    ORDER BY timestamp DESC
    LIMIT 1
) r ON true
WHERE s.station_code IN (
        'PUNE_LIVE_SPPU', 'PUNE_LIVE_DHANKAWADI', 'PUNE_LIVE_HADAPSAR',
        'PUNE_LIVE_NIGDI', 'PUNE_LIVE_PARK_STREET_WAKAD',
        'PUNE_LIVE_KATRAJ_DAIRY', 'PUNE_LIVE_GAVALINAGAR',
        'PUNE_LIVE_BHUMKAR_NAGAR'
      )
  AND s.is_active = true
  AND s.is_deleted = false
ORDER BY s.station_code;


-- 10. Retired stations are outside every current live query. Expected: 0 rows.
SELECT s.station_code, s.is_active
FROM monitoring_stations s
WHERE s.station_code IN ('PUNE_LIVE_ALANDI', 'PUNE_LIVE_KARVE_ROAD')
  AND s.is_active = true
  AND s.is_deleted = false;

-- Historical Alandi / Karve Road readings are kept, not deleted.
SELECT s.station_code, COUNT(r.id) AS preserved_readings
FROM monitoring_stations s
LEFT JOIN aqi_readings r ON r.station_id = s.id AND r.is_deleted = false
WHERE s.station_code IN ('PUNE_LIVE_ALANDI', 'PUNE_LIVE_KARVE_ROAD')
GROUP BY s.station_code;
