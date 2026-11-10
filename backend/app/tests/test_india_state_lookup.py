"""Tests for coordinate-derived India state lookup."""

from app.services.india_state_lookup import lookup_state


class TestLookupState:
    def test_known_capitals(self):
        cases = [
            (19.076, 72.877, "Maharashtra"),  # Mumbai
            (28.704, 77.102, "Delhi"),
            (13.083, 80.270, "Tamil Nadu"),  # Chennai
            (22.572, 88.363, "West Bengal"),  # Kolkata
            (12.971, 77.594, "Karnataka"),  # Bengaluru
            (17.385, 78.486, "Telangana"),  # Hyderabad
            (23.022, 72.571, "Gujarat"),  # Ahmedabad
            (26.144, 91.736, "Assam"),  # Guwahati
            (25.594, 85.137, "Bihar"),  # Patna
            (26.912, 75.787, "Rajasthan"),  # Jaipur
        ]
        for lat, lon, expected in cases:
            assert lookup_state(lat, lon) == expected, (lat, lon)

    def test_delhi_not_attributed_to_haryana(self):
        # Delhi is an enclave UT inside Haryana's bounding region —
        # polygon containment must win over proximity.
        assert lookup_state(28.744, 77.120) == "Delhi"

    def test_coastal_station_fallback(self):
        # Real OpenAQ coords for Worli, Mumbai sit ~1km outside the
        # coarse coastline polygon — bounded fallback assigns Maharashtra.
        assert lookup_state(19.000083, 72.813993) == "Maharashtra"

    def test_no_maharashtra_fallback_for_far_points(self):
        assert lookup_state(48.8566, 2.3522) is None  # Paris
        assert lookup_state(0.0, 0.0) is None  # Null island

    def test_invalid_inputs(self):
        assert lookup_state(None, None) is None
        assert lookup_state(91.0, 0.0) is None
        assert lookup_state("x", "y") is None
        assert lookup_state(18.5, None) is None

    def test_fallback_disabled(self):
        assert lookup_state(19.000083, 72.813993, fallback_km=None) is None
