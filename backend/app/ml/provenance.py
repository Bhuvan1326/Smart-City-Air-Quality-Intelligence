"""Forecast provenance + training/serving feature-time alignment (Week 2 F1/F2).

Pure functions (no I/O) shared by the worker, the registry, the response schema
and the tests, so labels and behaviour cannot drift apart.

Allowed `source` values (and ONLY these):
  trained_model            model output used at full weight
  model_statistical_blend  model output blended with the statistical estimate
  statistical_fallback     purely statistical (no model, model failed, or the
                           blend weight has decayed to zero)
"""

SOURCE_TRAINED = "trained_model"
SOURCE_BLEND = "model_statistical_blend"
SOURCE_STATISTICAL = "statistical_fallback"
ALLOWED_SOURCES = (SOURCE_TRAINED, SOURCE_BLEND, SOURCE_STATISTICAL)

BLEND_DECAY_HOURS = 24


def model_weight_for_horizon(hours_ahead: int) -> float:
    """Weight of the model in the blend at lookahead h (h=1 -> 1.0, decays
    linearly to 0.0 at h=25). Used by the worker AND by forecast_source."""
    return max(0.0, 1.0 - (hours_ahead - 1) / BLEND_DECAY_HOURS)


def forecast_source(model_version: str | None, horizon_hours: int | None) -> str:
    """Derive how a forecast value was actually produced.

    A model-based version (prefix 'xgb') produced by the worker is blended
    according to model_weight_for_horizon; anything else (statistical-*, empty,
    unknown) is statistical. Never reports a model source for a version that
    is not model-based."""
    if not model_version or not model_version.startswith("xgb"):
        return SOURCE_STATISTICAL
    if horizon_hours is None:
        return SOURCE_BLEND  # model-based version but horizon unknown: do not claim full model
    w = model_weight_for_horizon(max(1, horizon_hours))
    if w >= 1.0:
        return SOURCE_TRAINED
    return SOURCE_BLEND if w > 0.0 else SOURCE_STATISTICAL


def feature_time_parts(
    hour: int, day_of_week: int, hours_ahead: int, aligned: bool
) -> tuple[int, int]:
    """(hour_of_day, day_of_week) fed to the 1-step model.

    Training pairs an observation at time t (with ITS OWN hour/dow) with the
    AQI at t+1. At lookahead h the observation being fed in is the value at
    t0+h-1, so the aligned features are those of t0+h-1. The legacy behaviour
    passed the TARGET hour (t0+h) and never advanced day_of_week across
    midnight (training/serving skew M4)."""
    if not aligned:
        return (hour + hours_ahead) % 24, day_of_week
    steps = hour + hours_ahead - 1
    return steps % 24, (day_of_week + steps // 24) % 7
