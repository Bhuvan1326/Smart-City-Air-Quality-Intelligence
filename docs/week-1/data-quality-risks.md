# Data Quality Risks (ranked)

| Rank | Risk | Impact | Evidence | Mitigation / owner |
|---|---|---|---|---|
| 1 | Pollutant unit mismatch (D3), esp. CO, can drive AQI to 500 | False hazardous alerts, corrupted training data | Code: no unit handling | Parse and validate units, reject unknown; Vinyak |
| 2 | Legacy ingestion stamps ingestion time as observation time (D1) | Stale data shown as fresh; wrong freshness KPI; duplicate rows | Code | Use `observed_at`; Vinyak |
| 3 | "No data" encoded as AQI 500 (D4) | Spurious worst-case readings | Code | Return invalid/None; Vinyak |
| 4 | Training on synthetic/stale rows (M3) | Model learns seed patterns | Code; fixed in training SQL | Done; add data-lineage column check; Bhuvan |
| 5 | Mislabelled training target (M1) and random split (M2) | Meaningless metrics, unreliable forecasts | Code + synthetic repro; fixed | Retrain/evaluate; Bhuvan |
| 6 | Future timestamps treated as LIVE (D2) | Wrong freshness | Fixed + test | Done |
| 7 | Instantaneous AQI vs CPCB averaging (D5) | AQI differs from official values | Code | Document or implement; Vinyak |
| 8 | Time-zone conventions (UTC vs IST) inconsistent (D7, M7) | Diurnal features shifted 5.5 h | Code | Single documented convention; Bhuvan/Vinyak |
| 9 | Scheduler duplication when Redis lock fails open | Duplicate ingestion/forecasts | Code | Fail-closed lock or single scheduler process; Aryan |
| 10 | Invalid/outlier handling beyond `invalid` flag unverified (negatives, spikes) | Outliers enter training | Not verified | Add range checks + tests; Vinyak |
| 11 | Sample vs live labelling in UI not verified end-to-end | Synthetic data mistaken for live | Not verified | UI audit of `quality_flag`/freshness; Adwait |
