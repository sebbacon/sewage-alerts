import pytest
import check_spills


class TestHaversineKm:
    def test_zero_distance(self):
        assert check_spills.haversine_km(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0)

    def test_known_distance_london_to_paris(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ≈ 340km
        dist = check_spills.haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert 330 < dist < 350

    def test_within_20km(self):
        # GL5 1HE approx (51.745, -2.216) to River Severn site (51.752, -2.449) ≈ 14km
        dist = check_spills.haversine_km(51.745, -2.216, 51.752, -2.449)
        assert dist < 20
        assert dist > 0
