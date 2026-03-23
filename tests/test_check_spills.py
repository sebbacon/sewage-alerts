import json

import pytest
import yaml
from unittest.mock import MagicMock, patch

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
    def test_loads_multi_recipient_format(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            '  - postcode: "GL5 1HE"\n'
            "    radius_km: 45\n"
            '    notify_email: "a@b.com"\n'
            '  - postcode: "SW1A 1AA"\n'
            "    radius_km: 10\n"
            '    notify_email: "c@d.com"\n'
        )
        result = check_spills.load_config(str(f))
        assert result["lookback_hours"] == 24
        assert len(result["recipients"]) == 2
        assert result["recipients"][0] == {
            "postcode": "GL5 1HE", "radius_km": 45, "notify_email": "a@b.com"
        }
        assert result["recipients"][1] == {
            "postcode": "SW1A 1AA", "radius_km": 10, "notify_email": "c@d.com"
        }

    def test_key_order_independent(self, tmp_path):
        # yaml.dump sorts alphabetically: notify_email before postcode before radius_km
        f = tmp_path / "config.yml"
        f.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "- notify_email: a@b.com\n"
            "  postcode: GL5 1HE\n"
            "  radius_km: 45\n"
        )
        result = check_spills.load_config(str(f))
        assert result["recipients"][0]["postcode"] == "GL5 1HE"
        assert result["recipients"][0]["radius_km"] == 45
        assert result["recipients"][0]["notify_email"] == "a@b.com"


class TestLoadConfigBackwardsCompat:
    def test_flat_format_becomes_single_recipient(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text(
            "postcode: GL5 1HE\n"
            "radius_km: 20\n"
            "lookback_hours: 24\n"
            "notify_email: a@b.com\n"
        )
        result = check_spills.load_config(str(f))
        assert result["lookback_hours"] == 24
        assert len(result["recipients"]) == 1
        assert result["recipients"][0] == {
            "postcode": "GL5 1HE", "radius_km": 20, "notify_email": "a@b.com"
        }


class TestLoadCompanies:
    def test_loads_all_companies(self, tmp_path):
        f = tmp_path / "companies.yml"
        f.write_text(
            "companies:\n"
            "  - name: Anglian Water\n"
            "    query_url: https://example.com/anglian/query\n"
            "  - name: Thames Water\n"
            "    query_url: https://example.com/thames/query\n"
        )
        result = check_spills.load_companies(str(f))
        assert len(result) == 2
        assert result[0] == {
            "name": "Anglian Water",
            "query_url": "https://example.com/anglian/query",
        }
        assert result[1] == {
            "name": "Thames Water",
            "query_url": "https://example.com/thames/query",
        }

    def test_ignores_comments_and_header(self, tmp_path):
        f = tmp_path / "companies.yml"
        f.write_text(
            "# This is a comment\n"
            "companies:\n"
            "  - name: Test Water\n"
            "    query_url: https://example.com/query\n"
        )
        result = check_spills.load_companies(str(f))
        assert len(result) == 1
        assert result[0]["name"] == "Test Water"


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


FAKE_QUERY_URL = "https://fake.arcgis.com/FeatureServer/0/query"


SAMPLE_FEATURE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-2.449, 51.752]},
    "properties": {
        "Id": "SVT00291",
        "ReceivingWaterCourse": "RIVER SEVERN",
        "Latitude": 51.752,
        "Longitude": -2.449,
        "LatestEventStart": 1773753148000,
        "LatestEventEnd": 1773753431000,
    },
}

SAMPLE_FEATURE_SOUTH_WEST = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-4.826, 50.514]},
    "properties": {
        "Id": "SBB00407",
        "receivingWaterCourse": "CAMEL ESTUARY",
        # South West Water uses camelCase; coordinates come from geometry, not properties
        "latestEventStart": 1773224866000,
        "latestEventEnd": 1773224876000,
    },
}


class TestQuerySpills:
    def test_returns_features_list(self):
        payload = {"type": "FeatureCollection", "features": [SAMPLE_FEATURE]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            features = check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)
        assert len(features) == 1
        assert features[0]["properties"]["Id"] == "SVT00291"

    def test_returns_empty_list_when_no_results(self):
        payload = {"type": "FeatureCollection", "features": []}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(payload)):
            features = check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)
        assert features == []

    def test_raises_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with pytest.raises(RuntimeError, match="network error"):
                check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)

    def test_url_contains_interval_and_distance(self):
        payload = {"type": "FeatureCollection", "features": []}
        captured_url = []

        def capturing_urlopen(url, **kwargs):
            captured_url.append(url)
            return _mock_urlopen(payload)

        with patch("urllib.request.urlopen", side_effect=capturing_urlopen):
            check_spills.query_spills(51.745, -2.216, 20, 24, FAKE_QUERY_URL)

        url = captured_url[0]
        assert "INTERVAL" in url
        assert "24" in url
        assert "20000" in url
        assert "esriSRUnit_Meter" in url
        assert FAKE_QUERY_URL in url


class TestFormatSpillRow:
    def test_all_fields_present(self):
        row = check_spills.format_spill_row(SAMPLE_FEATURE, 51.745, -2.216, "Severn Trent Water")
        assert row["site_id"] == "SVT00291"
        assert row["company"] == "Severn Trent Water"
        assert row["watercourse"] == "RIVER SEVERN"
        assert isinstance(row["distance_km"], float)
        assert row["distance_km"] < 20
        assert "UTC" in row["started"]
        assert "UTC" in row["ended"]

    def test_ongoing_when_end_is_none(self):
        feature = {
            "geometry": SAMPLE_FEATURE["geometry"],
            "properties": {
                **SAMPLE_FEATURE["properties"],
                "LatestEventEnd": None,
            },
        }
        row = check_spills.format_spill_row(feature, 51.745, -2.216, "Test Co")
        assert row["ended"] == "Ongoing"

    def test_ongoing_when_end_is_zero(self):
        feature = {
            "geometry": SAMPLE_FEATURE["geometry"],
            "properties": {
                **SAMPLE_FEATURE["properties"],
                "LatestEventEnd": 0,
            },
        }
        row = check_spills.format_spill_row(feature, 51.745, -2.216, "Test Co")
        assert row["ended"] == "Ongoing"

    def test_camelcase_fields_normalised(self):
        row = check_spills.format_spill_row(SAMPLE_FEATURE_SOUTH_WEST, 51.745, -2.216, "South West Water")
        assert row["site_id"] == "SBB00407"
        assert row["company"] == "South West Water"
        assert row["watercourse"] == "CAMEL ESTUARY"
        assert "UTC" in row["started"]
        assert "UTC" in row["ended"]


SAMPLE_ROWS = [
    {
        "site_id": "SVT001",
        "company": "Test Water Co",
        "watercourse": "RIVER TEST",
        "distance_km": 5.3,
        "started": "2026-03-17 10:00 UTC",
        "ended": "Ongoing",
        "osm_url": "https://www.openstreetmap.org/?mlat=51.752&mlon=-2.449&zoom=16",
    }
]


class TestBuildHtmlEmail:
    def test_subject_contains_count_and_postcode(self):
        subject, _ = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "1" in subject
        assert "GL5 1HE" in subject

    def test_html_contains_all_row_fields(self):
        _, html = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "SVT001" in html
        assert "Test Water Co" in html
        assert "RIVER TEST" in html
        assert "5.3" in html
        assert "2026-03-17 10:00 UTC" in html
        assert "Ongoing" in html

    def test_html_is_valid_table(self):
        _, html = check_spills.build_html_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "<table" in html
        assert "<tr>" in html or "<tr " in html
        assert "<th>" in html or "<th " in html

    def test_html_appends_failure_warning(self):
        subject, html = check_spills.build_html_email(
            SAMPLE_ROWS, "GL5 1HE", 20, failures=[("United Utilities", "timeout")]
        )
        assert "United Utilities" in html
        assert "unreported" in html


class TestBuildTextEmail:
    def test_contains_all_row_fields(self):
        text = check_spills.build_text_email(SAMPLE_ROWS, "GL5 1HE", 20)
        assert "SVT001" in text
        assert "Test Water Co" in text
        assert "RIVER TEST" in text
        assert "Ongoing" in text
        assert "GL5 1HE" in text

    def test_text_appends_failure_warning(self):
        text = check_spills.build_text_email(
            SAMPLE_ROWS, "GL5 1HE", 20, failures=[("United Utilities", "timeout")]
        )
        assert "United Utilities" in text
        assert "unreported" in text


class TestSendEmail:
    def test_calls_smtp_login_and_sendmail(self):
        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm) as mock_smtp:
            check_spills.send_email(
                subject="Test subject",
                html="<p>html</p>",
                text="plain text",
                to_addr="to@example.com",
                from_addr="from@gmail.com",
                password="app_password",
            )

        mock_smtp.assert_called_once_with("smtp.gmail.com", 465)
        mock_server.login.assert_called_once_with("from@gmail.com", "app_password")
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "from@gmail.com"
        assert args[1] == "to@example.com"

    def test_exits_on_smtp_error(self):
        with patch("smtplib.SMTP_SSL", side_effect=Exception("connection refused")):
            with pytest.raises(SystemExit):
                check_spills.send_email(
                    "subj", "<p>html</p>", "text",
                    "to@example.com", "from@gmail.com", "pw",
                )


class TestResolveRecipient:
    def test_plaintext_recipient_unchanged(self):
        r = {"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "a@b.com"}
        postcode, email = check_spills.resolve_recipient(r)
        assert postcode == "GL5 1HE"
        assert email == "a@b.com"

    def test_slug_recipient_reads_env(self, monkeypatch):
        monkeypatch.setenv("RECIPIENT_ALICE_POSTCODE", "SW1A 2AA")
        monkeypatch.setenv("RECIPIENT_ALICE_EMAIL", "alice@example.com")
        r = {"slug": "alice", "radius_km": 15}
        postcode, email = check_spills.resolve_recipient(r)
        assert postcode == "SW1A 2AA"
        assert email == "alice@example.com"

    def test_slug_uppercased_for_env_lookup(self, monkeypatch):
        monkeypatch.setenv("RECIPIENT_MYSLUG_POSTCODE", "EC1A 1BB")
        monkeypatch.setenv("RECIPIENT_MYSLUG_EMAIL", "x@y.com")
        r = {"slug": "myslug", "radius_km": 10}
        postcode, email = check_spills.resolve_recipient(r)
        assert postcode == "EC1A 1BB"

    def test_missing_env_var_raises_key_error(self, monkeypatch):
        monkeypatch.delenv("RECIPIENT_GHOST_POSTCODE", raising=False)
        r = {"slug": "ghost", "radius_km": 10}
        with pytest.raises(KeyError, match="RECIPIENT_GHOST_POSTCODE"):
            check_spills.resolve_recipient(r)


class TestMain:
    BASE_CONFIG = {
        "lookback_hours": 24,
        "recipients": [
            {"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "user@example.com"},
        ],
    }
    COMPANIES_YAML = (
        "companies:\n"
        "  - name: Severn Trent Water\n"
        "    query_url: https://fake1.arcgis.com/query\n"
        "  - name: Thames Water\n"
        "    query_url: https://fake2.arcgis.com/query\n"
    )

    def _write_config(self, tmp_path):
        import yaml
        config_file = tmp_path / "config.yml"
        config_file.write_text(yaml.dump(self.BASE_CONFIG))
        return str(config_file)

    def _write_companies(self, tmp_path, content=None):
        companies_file = tmp_path / "companies.yml"
        companies_file.write_text(content or self.COMPANIES_YAML)
        return str(companies_file)

    def test_no_email_when_no_spills(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        empty_features = {"type": "FeatureCollection", "features": []}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            return _mock_urlopen(empty_features)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL") as mock_smtp, \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=config_file, companies_path=companies_file)

        mock_smtp.assert_not_called()

    def test_sends_email_when_spills_found(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        features_payload = {"type": "FeatureCollection", "features": [SAMPLE_FEATURE]}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            return _mock_urlopen(features_payload)

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=config_file, companies_path=companies_file)

        mock_server.sendmail.assert_called_once()

    def test_aggregates_spills_from_multiple_companies(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        spill_1 = {**SAMPLE_FEATURE, "properties": {**SAMPLE_FEATURE["properties"], "Id": "AAA001"}}
        spill_2 = {**SAMPLE_FEATURE, "properties": {**SAMPLE_FEATURE["properties"], "Id": "BBB001"}}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}
        call_count = [0]

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_urlopen({"type": "FeatureCollection", "features": [spill_1]})
            return _mock_urlopen({"type": "FeatureCollection", "features": [spill_2]})

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=config_file, companies_path=companies_file)

        args = mock_server.sendmail.call_args[0]
        assert "AAA001" in args[2]
        assert "BBB001" in args[2]

    def test_continues_and_exits_nonzero_on_partial_failure(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}
        call_count = [0]

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("connection refused")
            return _mock_urlopen({"type": "FeatureCollection", "features": [SAMPLE_FEATURE]})

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}), \
             pytest.raises(SystemExit) as exc_info:
            check_spills.main(config_path=config_file, companies_path=companies_file)

        assert exc_info.value.code == 1
        mock_server.sendmail.assert_called_once()

    def test_sends_error_only_email_when_no_spills_but_failures(self, tmp_path):
        config_file = self._write_config(tmp_path)
        companies_file = self._write_companies(tmp_path)

        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            raise Exception("timeout")

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}), \
             pytest.raises(SystemExit) as exc_info:
            check_spills.main(config_path=config_file, companies_path=companies_file)

        assert exc_info.value.code == 1
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert "could not be queried" in args[2]

    def test_runs_for_each_recipient(self, tmp_path):
        multi_config = {
            "lookback_hours": 24,
            "recipients": [
                {"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "alice@example.com"},
                {"postcode": "SW1A 1AA", "radius_km": 10, "notify_email": "bob@example.com"},
            ],
        }
        import yaml
        config_file = tmp_path / "config.yml"
        config_file.write_text(yaml.dump(multi_config))
        companies_file = self._write_companies(tmp_path)

        features_payload = {"type": "FeatureCollection", "features": [SAMPLE_FEATURE]}
        postcode_payload = {"status": 200, "result": {"latitude": 51.745, "longitude": -2.216}}

        def fake_urlopen(url, **kwargs):
            if "postcodes.io" in url:
                return _mock_urlopen(postcode_payload)
            return _mock_urlopen(features_payload)

        mock_server = MagicMock()
        mock_smtp_cm = MagicMock()
        mock_smtp_cm.__enter__.return_value = mock_server
        mock_smtp_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("smtplib.SMTP_SSL", return_value=mock_smtp_cm), \
             patch.dict("os.environ", {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
            check_spills.main(config_path=str(config_file), companies_path=companies_file)

        assert mock_server.sendmail.call_count == 2
