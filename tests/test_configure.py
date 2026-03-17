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
    def test_writes_all_fields(self, tmp_path):
        config_path = str(tmp_path / "config.yml")
        configure.write_config(
            postcode="SW1A 1AA",
            radius_km=15,
            lookback_hours=12,
            notify_email="test@example.com",
            path=config_path,
        )
        with open(config_path) as f:
            result = yaml.safe_load(f)
        assert result["postcode"] == "SW1A 1AA"
        assert result["radius_km"] == 15
        assert result["lookback_hours"] == 12
        assert result["notify_email"] == "test@example.com"
