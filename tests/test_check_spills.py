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


class TestLoadConfig:
    def test_loads_all_fields(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text("postcode: GL5 1HE\nradius_km: 20\nlookback_hours: 24\nnotify_email: a@b.com\n")
        result = check_spills.load_config(str(f))
        assert result["postcode"] == "GL5 1HE"
        assert result["radius_km"] == 20
        assert result["lookback_hours"] == 24
        assert result["notify_email"] == "a@b.com"


class TestValidateLookbackHours:
    def test_standard_values_produce_no_warning(self, capsys):
        for hours in (6, 12, 24):
            check_spills.validate_lookback_hours(hours)
        assert capsys.readouterr().err == ""

    def test_nonstandard_value_warns_to_stderr(self, capsys):
        check_spills.validate_lookback_hours(7)
        err = capsys.readouterr().err
        assert "WARNING" in err
        assert "7" in err


import json
from unittest.mock import MagicMock, patch


def _mock_urlopen(response_data: dict) -> MagicMock:
    """Return a context-manager mock for urllib.request.urlopen."""
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value.read.return_value = json.dumps(response_data).encode()
    mock_cm.__exit__.return_value = False
    return mock_cm


class TestGetPostcodeCoords:
    def test_returns_lat_lon(self):
        payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            lat, lon = check_spills.get_postcode_coords("GL5 1HE")
        assert lat == pytest.approx(51.745)
        assert lon == pytest.approx(-2.216)

    def test_exits_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with pytest.raises(SystemExit):
                check_spills.get_postcode_coords("GL5 1HE")
