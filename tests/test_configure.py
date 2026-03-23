import re
import pytest
import yaml
import configure
from unittest.mock import MagicMock


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

    def test_reads_slug_recipient(self, tmp_path):
        f = tmp_path / "config.yml"
        f.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "  - slug: alice\n"
            "    radius_km: 15\n"
        )
        result = configure.read_config(str(f))
        r = result["recipients"][0]
        assert r["slug"] == "alice"
        assert isinstance(r["slug"], str)
        assert r["radius_km"] == 15
        assert "postcode" not in r

    def test_numeric_slug_cast_to_str(self, tmp_path):
        """yaml.safe_load parses slug: 123 as int; must be cast to str."""
        f = tmp_path / "config.yml"
        f.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "  - slug: 123\n"
            "    radius_km: 15\n"
        )
        result = configure.read_config(str(f))
        assert result["recipients"][0]["slug"] == "123"
        assert isinstance(result["recipients"][0]["slug"], str)

    def test_duplicate_slug_warns(self, tmp_path, capsys):
        f = tmp_path / "config.yml"
        f.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "  - slug: alice\n"
            "    radius_km: 15\n"
            "  - slug: alice\n"
            "    radius_km: 20\n"
        )
        result = configure.read_config(str(f))
        captured = capsys.readouterr()
        assert "duplicate" in captured.err.lower() or "warning" in captured.err.lower()
        assert len(result["recipients"]) == 2  # continues, does not abort


class TestConfigureMainSlugDisplay:
    """Test that the listing loop doesn't crash on slug-backed recipients."""

    def test_list_slug_recipient_no_crash(self, tmp_path, monkeypatch, capsys):
        config = tmp_path / "config.yml"
        config.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "  - slug: alice\n"
            "    radius_km: 15\n"
        )
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text(
            "    - cron: '0 7 * * *'\n"
            "        env:\n"
            "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n"
            "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n"
        )
        inputs = iter(["3", "", "d"])  # choice=daily, "" accepts default hour, then done
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        original_read_config = configure.read_config
        monkeypatch.setattr("configure.read_config", lambda path=None: original_read_config(str(config)))
        configure.main()
        captured = capsys.readouterr()
        assert "[secrets: alice]" in captured.out
        assert "20km" not in captured.out  # radius is 15

    def test_list_plaintext_recipient_unchanged(self, tmp_path, monkeypatch, capsys):
        config = tmp_path / "config.yml"
        config.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            '  - postcode: "GL5 1HE"\n'
            "    radius_km: 20\n"
            '    notify_email: "a@b.com"\n'
        )
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text(
            "    - cron: '0 7 * * *'\n"
            "        env:\n"
            "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n"
            "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n"
        )
        inputs = iter(["3", "", "d"])  # "" accepts default hour
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        original_read_config = configure.read_config
        monkeypatch.setattr("configure.read_config", lambda path=None: original_read_config(str(config)))
        configure.main()
        captured = capsys.readouterr()
        assert "GL5 1HE" in captured.out
        assert "a@b.com" in captured.out


class TestPatchWorkflowEnv:
    WORKFLOW_BASE = (
        "name: Check sewage spills\n"
        "on:\n"
        "  schedule:\n"
        "    - cron: '0 7 * * *'\n"
        "jobs:\n"
        "  check:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Check for nearby spills\n"
        "        run: python check_spills.py\n"
        "        env:\n"
        "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n"
        "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n"
    )

    def test_no_slugs_keeps_fixed_keys(self, tmp_path):
        wf = tmp_path / "check_spills.yml"
        wf.write_text(self.WORKFLOW_BASE)
        configure.patch_workflow_env([], str(wf))
        result = wf.read_text()
        assert "GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}" in result
        assert "GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}" in result
        assert "RECIPIENT_" not in result

    def test_adds_slug_env_vars(self, tmp_path):
        wf = tmp_path / "check_spills.yml"
        wf.write_text(self.WORKFLOW_BASE)
        configure.patch_workflow_env(["alice"], str(wf))
        result = wf.read_text()
        assert "RECIPIENT_ALICE_POSTCODE: ${{ secrets.RECIPIENT_ALICE_POSTCODE }}" in result
        assert "RECIPIENT_ALICE_EMAIL: ${{ secrets.RECIPIENT_ALICE_EMAIL }}" in result

    def test_adds_multiple_slugs(self, tmp_path):
        wf = tmp_path / "check_spills.yml"
        wf.write_text(self.WORKFLOW_BASE)
        configure.patch_workflow_env(["alice", "bob"], str(wf))
        result = wf.read_text()
        assert "RECIPIENT_ALICE_POSTCODE" in result
        assert "RECIPIENT_BOB_EMAIL" in result

    def test_removes_old_slugs_on_rewrite(self, tmp_path):
        """Calling with empty slugs removes previously injected RECIPIENT_ vars."""
        wf = tmp_path / "check_spills.yml"
        initial = self.WORKFLOW_BASE + (
            "          RECIPIENT_ALICE_POSTCODE: ${{ secrets.RECIPIENT_ALICE_POSTCODE }}\n"
            "          RECIPIENT_ALICE_EMAIL: ${{ secrets.RECIPIENT_ALICE_EMAIL }}\n"
        )
        wf.write_text(initial)
        configure.patch_workflow_env([], str(wf))
        result = wf.read_text()
        assert "RECIPIENT_ALICE" not in result

    def test_file_ends_with_single_newline(self, tmp_path):
        wf = tmp_path / "check_spills.yml"
        wf.write_text(self.WORKFLOW_BASE)
        configure.patch_workflow_env(["alice"], str(wf))
        raw = wf.read_text()
        assert raw.endswith("\n")
        assert not raw.endswith("\n\n")

    def test_slugs_uppercased(self, tmp_path):
        wf = tmp_path / "check_spills.yml"
        wf.write_text(self.WORKFLOW_BASE)
        configure.patch_workflow_env(["MySlug"], str(wf))
        result = wf.read_text()
        assert "RECIPIENT_MYSLUG_POSTCODE" in result
        assert "RECIPIENT_myslug" not in result


class TestAddSlugRecipient:
    def _run_add(self, tmp_path, monkeypatch, inputs, gh_available=True, gh_returncode=0):
        """Helper to run configure.main() with mocked input and gh."""
        config = tmp_path / "config.yml"
        config.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            '  - postcode: "GL5 1HE"\n'
            "    radius_km: 20\n"
            '    notify_email: "a@b.com"\n'
        )
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text(
            "    - cron: '0 7 * * *'\n"
            "        env:\n"
            "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n"
            "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n"
        )
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh" if gh_available else None)
        mock_result = MagicMock()
        mock_result.returncode = gh_returncode
        mock_result.stderr = b"some error" if gh_returncode != 0 else b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        configure.main()
        return yaml.safe_load(config.read_text())

    def test_add_slug_recipient_stores_slug_not_pii(self, tmp_path, monkeypatch):
        inputs = iter([
            "3",        # daily schedule
            "",         # accept default hour (7)
            "a",        # add recipient
            "15",       # radius
            "y",        # use secrets
            "alice",    # slug
            "SW1A 2AA",  # postcode (sent to gh, not stored)
            "a@b.com",  # email (sent to gh, not stored)
            "d",        # done
        ])
        result = self._run_add(tmp_path, monkeypatch, inputs)
        slugs = [r.get("slug") for r in result["recipients"] if "slug" in r]
        assert "alice" in slugs
        postcodes = [r.get("postcode") for r in result["recipients"] if "postcode" in r]
        assert "SW1A 2AA" not in postcodes  # the slug recipient's postcode not in config

    def test_add_slug_recipient_gh_not_available_skips_option(self, tmp_path, monkeypatch, capsys):
        # When gh is unavailable, the secrets prompt should not appear; goes straight to postcode
        inputs = iter([
            "3",
            "",          # accept default hour
            "a",
            "15",
            "SW1A 2AA",  # postcode directly (no secrets prompt)
            "c@d.com",
            "d",
        ])
        result = self._run_add(tmp_path, monkeypatch, inputs, gh_available=False)
        # new recipient is plaintext
        new = [r for r in result["recipients"] if r.get("postcode") == "SW1A 2AA"]
        assert len(new) == 1

    def test_invalid_slug_reprompts(self, tmp_path, monkeypatch, capsys):
        inputs = iter([
            "3",
            "",          # accept default hour
            "a",
            "15",
            "y",
            "bad-slug",  # invalid (hyphen)
            "goodslug",  # valid on retry
            "GL5 1HE",
            "a@b.com",
            "d",
        ])
        result = self._run_add(tmp_path, monkeypatch, inputs)
        captured = capsys.readouterr()
        assert "goodslug" in [r.get("slug") for r in result["recipients"] if "slug" in r]

    def test_duplicate_slug_reprompts(self, tmp_path, monkeypatch, capsys):
        # Start with existing slug alice in config
        config = tmp_path / "config.yml"
        config.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "  - slug: alice\n"
            "    radius_km: 15\n"
        )
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text(
            "    - cron: '0 7 * * *'\n"
            "        env:\n"
            "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n"
            "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n"
        )
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        inputs = iter([
            "3",
            "",         # accept default hour
            "a",
            "20",
            "y",
            "alice",    # duplicate — should be rejected
            "bob",      # unique — accepted
            "SW1A 2AA",
            "b@b.com",
            "d",
        ])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        configure.main()
        result = yaml.safe_load(config.read_text())
        slugs = [r.get("slug") for r in result["recipients"] if "slug" in r]
        assert "bob" in slugs
        assert slugs.count("alice") == 1  # original, not duplicated


class TestConfigureMainFinal:
    """Tests for patch_workflow_env wiring, remove hint, and post-setup message."""

    def _make_workflow(self, tmp_path):
        workflow = tmp_path / "check_spills.yml"
        workflow.write_text(
            "    - cron: '0 7 * * *'\n"
            "        env:\n"
            "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n"
            "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n"
        )
        return workflow

    def test_patch_workflow_env_called_with_slugs(self, tmp_path, monkeypatch):
        """patch_workflow_env is called with the slug list when there's one slug recipient."""
        workflow = self._make_workflow(tmp_path)

        calls = []
        monkeypatch.setattr("configure.write_config", lambda *a, **kw: None)
        monkeypatch.setattr("configure.patch_workflow_cron", lambda *a, **kw: None)
        monkeypatch.setattr(
            "configure.patch_workflow_env",
            lambda slugs, workflow_path=None: calls.append((slugs, workflow_path)),
        )
        monkeypatch.setattr(
            "configure.read_config",
            lambda path=None: {"recipients": [{"slug": "alice", "radius_km": 15}]},
        )
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))

        inputs = iter(["3", "7", "d"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

        configure.main()

        assert calls == [(["alice"], configure.WORKFLOW_PATH)]

    def test_patch_workflow_env_called_with_empty_slugs(self, tmp_path, monkeypatch):
        """patch_workflow_env is called with empty slugs list when config has no slug recipients."""
        workflow = self._make_workflow(tmp_path)

        calls = []
        monkeypatch.setattr("configure.write_config", lambda *a, **kw: None)
        monkeypatch.setattr("configure.patch_workflow_cron", lambda *a, **kw: None)
        monkeypatch.setattr(
            "configure.patch_workflow_env",
            lambda slugs, workflow_path=None: calls.append((slugs, workflow_path)),
        )
        monkeypatch.setattr(
            "configure.read_config",
            lambda path=None: {"recipients": [{"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "a@b.com"}]},
        )
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))

        inputs = iter(["3", "7", "d"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

        configure.main()

        assert calls == [([], configure.WORKFLOW_PATH)]

    def test_remove_slug_prints_cleanup_hint(self, tmp_path, monkeypatch, capsys):
        """Removing a slug recipient prints a cleanup note."""
        workflow = self._make_workflow(tmp_path)

        monkeypatch.setattr("configure.write_config", lambda *a, **kw: None)
        monkeypatch.setattr("configure.patch_workflow_cron", lambda *a, **kw: None)
        monkeypatch.setattr("configure.patch_workflow_env", lambda *a, **kw: None)
        monkeypatch.setattr(
            "configure.read_config",
            lambda path=None: {
                "recipients": [
                    {"slug": "alice", "radius_km": 15},
                    {"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "a@b.com"},
                ]
            },
        )
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))

        # r 1 removes the first recipient (alice, the slug one)
        inputs = iter(["3", "7", "r 1", "d"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

        configure.main()
        captured = capsys.readouterr()
        assert "gh secret delete RECIPIENT_ALICE_POSTCODE" in captured.out

    def test_post_setup_message_includes_session_slugs(self, tmp_path, monkeypatch, capsys):
        """Post-setup message includes 'Secrets already set this session' for new slug recipients."""
        workflow = self._make_workflow(tmp_path)
        config = tmp_path / "config.yml"
        config.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            '  - postcode: "GL5 1HE"\n'
            "    radius_km: 20\n"
            '    notify_email: "a@b.com"\n'
        )

        monkeypatch.setattr("configure.write_config", lambda *a, **kw: None)
        monkeypatch.setattr("configure.patch_workflow_cron", lambda *a, **kw: None)
        monkeypatch.setattr("configure.patch_workflow_env", lambda *a, **kw: None)
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        # Add a slug recipient (alice) then done
        inputs = iter([
            "3",        # daily schedule
            "7",        # hour
            "a",        # add
            "15",       # radius
            "y",        # use secrets
            "alice",    # slug
            "SW1A 2AA", # postcode
            "test@example.com",  # email
            "d",        # done
        ])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

        configure.main()
        captured = capsys.readouterr()
        assert "RECIPIENT_ALICE_POSTCODE" in captured.out
        assert "Secrets already set this session:" in captured.out
