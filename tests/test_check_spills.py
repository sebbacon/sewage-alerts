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
