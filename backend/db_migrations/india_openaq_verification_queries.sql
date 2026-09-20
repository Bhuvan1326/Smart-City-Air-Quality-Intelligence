SELECT COUNT(*) AS total_india_openaq_stations
FROM monitoring_stations
WHERE country = 'India'
  AND station_type = 'OpenAQ'
  AND openaq_location_id IS NOT NULL
  AND is_active = true
  AND is_deleted = false;


SELECT COUNT(DISTINCT s.id) AS stations_with_readings
FROM monitoring_stations s
JOIN aqi_readings r
  ON r.station_id = s.id
 AND r.is_deleted = false
WHERE s.country = 'India'
  AND s.station_type = 'OpenAQ'
  AND s.openaq_location_id IS NOT NULL
  AND s.is_active = true
  AND s.is_deleted = false;


-- C. Stations without any (non-deleted) reading at all.
SELECT COUNT(*) AS stations_without_readings
FROM monitoring_stations s
WHERE s.country = 'India'
  AND s.station_type = 'OpenAQ'
  AND s.openaq_location_id IS NOT NULL
  AND s.is_active = true
  AND s.is_deleted = false
  AND NOT EXISTS (
      SELECT 1 FROM aqi_readings r
      WHERE r.station_id = s.id AND r.is_deleted = false
  );



SELECT station_id, "timestamp", COUNT(*) AS duplicate_count
FROM aqi_readings
WHERE is_deleted = false
GROUP BY station_id, "timestamp"
HAVING COUNT(*) > 1;


SELECT DISTINCT ON (s.id)
    s.id AS station_id,
    s.station_code,
    s.city,
    s.state,
    r.aqi,
    r.quality_flag,
    r."timestamp" AS observed_at
FROM monitoring_stations s
LEFT JOIN aqi_readings r
       ON r.station_id = s.id
      AND r.is_deleted = false
      AND r.quality_flag NOT IN ('invalid', 'synthetic')
WHERE s.country = 'India'
  AND s.station_type = 'OpenAQ'
  AND s.openaq_location_id IS NOT NULL
  AND s.is_active = true
  AND s.is_deleted = false
ORDER BY s.id, r."timestamp" DESC NULLS LAST;


SELECT quality_flag, COUNT(*) AS reading_count
FROM aqi_readings r
JOIN monitoring_stations s ON s.id = r.station_id
WHERE s.country = 'India'
  AND s.station_type = 'OpenAQ'
  AND r.is_deleted = false
GROUP BY quality_flag
ORDER BY quality_flag;


SELECT COUNT(*) AS stations_with_null_observation
FROM monitoring_stations s
WHERE s.country = 'India'
  AND s.station_type = 'OpenAQ'
  AND s.openaq_location_id IS NOT NULL
  AND s.is_active = true
  AND s.is_deleted = false
  AND NOT EXISTS (
      SELECT 1 FROM aqi_readings r
      WHERE r.station_id = s.id
        AND r.is_deleted = false
        AND r.quality_flag NOT IN ('invalid', 'synthetic')
  );


SELECT
    (SELECT COUNT(*) FROM monitoring_stations s
      WHERE s.country = 'India' AND s.station_type = 'OpenAQ'
        AND s.openaq_location_id IS NOT NULL
        AND s.is_active = true AND s.is_deleted = false) AS total_stations,
    (SELECT COUNT(*) FROM monitoring_stations s
      WHERE s.country = 'India' AND s.station_type = 'OpenAQ'
        AND s.openaq_location_id IS NOT NULL
        AND s.is_active = true AND s.is_deleted = false
        AND s.station_code <= :cursor) AS processed_total;

SELECT COUNT(DISTINCT state) AS states_represented
FROM monitoring_stations
WHERE country = 'India'
  AND state IS NOT NULL
  AND is_deleted = false;


SELECT state, COUNT(*) AS station_count
FROM monitoring_stations
WHERE country = 'India'
  AND station_type = 'OpenAQ'
  AND is_deleted = false
GROUP BY state
ORDER BY station_count DESC NULLS LAST;


SELECT COUNT(*) AS stations_with_coordinates
FROM monitoring_stations
WHERE country = 'India'
  AND station_type = 'OpenAQ'
  AND is_deleted = false
  AND latitude IS NOT NULL
  AND longitude IS NOT NULL;


SELECT COUNT(*) AS india_aqi_list_total
FROM monitoring_stations
WHERE is_deleted = false
  AND is_active = true
  AND country = 'India'
  AND station_type = 'OpenAQ';


SELECT COUNT(*) AS india_aqi_heatmap_total
FROM monitoring_stations
WHERE country = 'India'
  AND is_active = true
  AND is_deleted = false
  AND station_type = 'OpenAQ';


(
    SELECT id FROM monitoring_stations
    WHERE country = 'India' AND station_type = 'OpenAQ'
      AND is_active = true AND is_deleted = false
    EXCEPT
    SELECT id FROM monitoring_stations
    WHERE is_deleted = false AND is_active = true
      AND country = 'India' AND station_type = 'OpenAQ'
)
UNION ALL
(
    SELECT id FROM monitoring_stations
    WHERE is_deleted = false AND is_active = true
      AND country = 'India' AND station_type = 'OpenAQ'
    EXCEPT
    SELECT id FROM monitoring_stations
    WHERE country = 'India' AND station_type = 'OpenAQ'
      AND is_active = true AND is_deleted = false
);
