import re
import pytest
import yaml
import configure


class TestBuildCronAndHours:
    def test_choice_1_every_6h(self):
        cron, hours = configure.build_cron_and_hours(1, hour=None)
        assert cron == "0 */6 * * *"
        assert hours == 6

    def test_choice_2_every_12h(self):
        cron, hours = configure.build_cron_and_hours(2, hour=None)
        assert cron == "0 */12 * * *"
        assert hours == 12

    def test_choice_3_daily_default_hour(self):
        cron, hours = configure.build_cron_and_hours(3, hour=7)
        assert cron == "0 7 * * *"
        assert hours == 24

    def test_choice_3_daily_custom_hour(self):
        cron, hours = configure.build_cron_and_hours(3, hour=8)
        assert cron == "0 8 * * *"
        assert hours == 24


class TestPatchWorkflowCron:
    def test_patches_cron_expression(self, tmp_path):
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text("    - cron: '0 7 * * *'\n")
        configure.patch_workflow_cron("0 */6 * * *", str(workflow))
        result = workflow.read_text()
        assert "0 */6 * * *" in result
        assert "0 7 * * *" not in result

    def test_leaves_rest_of_file_intact(self, tmp_path):
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text("name: foo\n    - cron: '0 7 * * *'\njobs:\n")
        configure.patch_workflow_cron("0 */12 * * *", str(workflow))
        result = workflow.read_text()
        assert "name: foo" in result
        assert "jobs:" in result


class TestWriteConfig:
    def test_writes_multi_recipient_format(self, tmp_path):
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            lookback_hours=24,
            recipients=[{"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "test@example.com"}],
            path=config_path,
        )
        with open(config_path) as f:
            result = yaml.safe_load(f)
        assert result["lookback_hours"] == 24
        assert len(result["recipients"]) == 1
        assert result["recipients"][0]["postcode"] == "GL5 1HE"
        assert result["recipients"][0]["radius_km"] == 20
        assert result["recipients"][0]["notify_email"] == "test@example.com"

    def test_writes_multiple_recipients(self, tmp_path):
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            lookback_hours=12,
            recipients=[
                {"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "a@example.com"},
                {"postcode": "SW1A 1AA", "radius_km": 5, "notify_email": "b@example.com"},
            ],
            path=config_path,
        )
        with open(config_path) as f:
            result = yaml.safe_load(f)
        assert result["lookback_hours"] == 12
        assert len(result["recipients"]) == 2
        assert result["recipients"][1]["postcode"] == "SW1A 1AA"

    def test_writes_slug_recipient(self, tmp_path):
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            lookback_hours=24,
            recipients=[{"slug": "alice", "radius_km": 15}],
            path=config_path,
        )
        with open(config_path) as f:
            result = yaml.safe_load(f)
        assert len(result["recipients"]) == 1
        r = result["recipients"][0]
        assert r["slug"] == "alice"
        assert r["radius_km"] == 15
        assert "postcode" not in r
        assert "notify_email" not in r

    def test_writes_slug_first_on_dash_line(self, tmp_path):
        """slug must be first field so check_spills.py hand-rolled parser finds it."""
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            lookback_hours=24,
            recipients=[{"slug": "alice", "radius_km": 15}],
            path=config_path,
        )
        with open(config_path) as f:
            content = f.read()
        assert '  - slug: "alice"' in content

    def test_writes_mixed_recipients(self, tmp_path):
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            lookback_hours=24,
            recipients=[
                {"slug": "alice", "radius_km": 15},
                {"postcode": "SW1A 1AA", "radius_km": 20, "notify_email": "b@example.com"},
            ],
            path=config_path,
        )
        with open(config_path) as f:
            result = yaml.safe_load(f)
        assert result["recipients"][0]["slug"] == "alice"
        assert result["recipients"][1]["postcode"] == "SW1A 1AA"


class TestReadConfig:
    def test_reads_multi_recipient_format(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            '  - postcode: "GL5 1HE"\n'
            "    radius_km: 20\n"
            '    notify_email: "a@b.com"\n'
        )
        result = configure.read_config(str(f))
        assert result["lookback_hours"] == 24
        assert result["recipients"][0]["postcode"] == "GL5 1HE"

    def test_flat_format_backwards_compat(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text("postcode: GL5 1HE\nradius_km: 20\nlookback_hours: 24\nnotify_email: a@b.com\n")
        result = configure.read_config(str(f))
        assert len(result["recipients"]) == 1
        assert result["recipients"][0]["postcode"] == "GL5 1HE"

    def test_missing_file_returns_empty_recipients(self):
        result = configure.read_config("/nonexistent/config.yml")
        assert result == {"recipients": []}
