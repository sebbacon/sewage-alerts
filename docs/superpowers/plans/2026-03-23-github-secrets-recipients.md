# GitHub Secrets Recipients Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow each recipient's postcode and email to be stored optionally in GitHub Secrets rather than plaintext in `config.yml`.

**Architecture:** The discriminator is whether a recipient dict has a `slug` key (secret-backed) or a `postcode` key (plaintext). `configure.py` handles interactive setup and calls `gh secret set` when needed; `check_spills.py` resolves slugs to env vars at runtime. The workflow YAML `env:` block is rewritten by `configure.py` to expose each slug's secrets.

**Tech Stack:** Python 3.12, PyYAML, subprocess (stdlib), shutil (stdlib), pytest, gh CLI

---

### Task 1: Update `write_config` to handle slug-backed recipients

**Files:**
- Modify: `configure.py:57-69`
- Test: `tests/test_configure.py`

- [ ] **Step 1: Write failing tests for slug-backed write_config**

Add to `TestWriteConfig` in `tests/test_configure.py`:

```python
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
    assert "  - slug: alice" in content

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_configure.py::TestWriteConfig -v
```
Expected: 2–3 new tests FAIL (KeyError or assertion error)

- [ ] **Step 3: Update `write_config` in `configure.py`**

Replace the `for r in recipients:` block (lines 66–69):

```python
for r in recipients:
    if "slug" in r:
        f.write(f'  - slug: {r["slug"]}\n')
        f.write(f'    radius_km: {r["radius_km"]}\n')
    else:
        f.write(f'  - postcode: "{r["postcode"]}"\n')
        f.write(f'    radius_km: {r["radius_km"]}\n')
        f.write(f'    notify_email: "{r["notify_email"]}"\n')
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_configure.py::TestWriteConfig -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "feat: write_config supports slug-backed recipients"
```

---

### Task 2: Update `read_config` to cast slug to str and warn on duplicates

**Files:**
- Modify: `configure.py:38-54`
- Test: `tests/test_configure.py`

- [ ] **Step 1: Write failing tests**

Add to `TestReadConfig` in `tests/test_configure.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_configure.py::TestReadConfig -v
```
Expected: 3 new tests FAIL

- [ ] **Step 3: Update `read_config` in `configure.py`**

After loading `data`, add slug normalisation and duplicate detection. The function currently ends at line 54. Add after `data.setdefault("recipients", [])`:

```python
# Cast slug to str (yaml.safe_load parses purely numeric slugs as int)
for r in data.get("recipients", []):
    if "slug" in r:
        r["slug"] = str(r["slug"])

# Warn on duplicate slugs (e.g. from hand-editing)
slugs_seen = set()
for r in data.get("recipients", []):
    slug = r.get("slug")
    if slug is not None:
        if slug in slugs_seen:
            print(f"WARNING: duplicate slug '{slug}' in config", file=sys.stderr)
        slugs_seen.add(slug)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_configure.py::TestReadConfig -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "feat: read_config casts slug to str, warns on duplicates"
```

---

### Task 3: Add `patch_workflow_env` to `configure.py`

**Files:**
- Modify: `configure.py` (add new function after `patch_workflow_cron`)
- Test: `tests/test_configure.py`

- [ ] **Step 1: Write failing tests**

Add new `TestPatchWorkflowEnv` class to `tests/test_configure.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_configure.py::TestPatchWorkflowEnv -v
```
Expected: all FAIL with `AttributeError: module 'configure' has no attribute 'patch_workflow_env'`

- [ ] **Step 3: Implement `patch_workflow_env` in `configure.py`**

Add after `patch_workflow_cron`:

```python
def patch_workflow_env(slugs: list[str], workflow_path: str = WORKFLOW_PATH) -> None:
    """Rewrite the env: block under 'Check for nearby spills' step."""
    lines = [
        "        env:\n",
        "          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}\n",
        "          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}\n",
    ]
    for slug in slugs:
        s = slug.upper()
        lines.append(f"          RECIPIENT_{s}_POSTCODE: ${{{{ secrets.RECIPIENT_{s}_POSTCODE }}}}\n")
        lines.append(f"          RECIPIENT_{s}_EMAIL: ${{{{ secrets.RECIPIENT_{s}_EMAIL }}}}\n")
    replacement = "".join(lines)
    with open(workflow_path) as f:
        content = f.read()
    new_content = re.sub(r"        env:.*", replacement.rstrip("\n"), content, flags=re.DOTALL)
    with open(workflow_path, "w") as f:
        f.write(new_content + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_configure.py::TestPatchWorkflowEnv -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "feat: add patch_workflow_env to manage recipient secret env vars"
```

---

### Task 4: Update `check_spills.py` to resolve slug-backed recipients

**Files:**
- Modify: `check_spills.py:299-303` (recipient loop in `main()`)
- Test: `tests/test_check_spills.py`

- [ ] **Step 1: Write failing tests**

Add new `TestResolveRecipient` class to `tests/test_check_spills.py`:

```python
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

    def test_missing_env_var_raises_key_error(self):
        r = {"slug": "ghost", "radius_km": 10}
        with pytest.raises(KeyError, match="RECIPIENT_GHOST_POSTCODE"):
            check_spills.resolve_recipient(r)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_check_spills.py::TestResolveRecipient -v
```
Expected: all FAIL with `AttributeError: module 'check_spills' has no attribute 'resolve_recipient'`

- [ ] **Step 3: Add `resolve_recipient` to `check_spills.py` and call it in `main()`**

Add the function after `_set_recipient_field` (around line 46):

```python
def resolve_recipient(recipient: dict) -> tuple[str, str]:
    """Return (postcode, notify_email) for a recipient, reading from env if slug-backed."""
    if "slug" in recipient:
        slug = recipient["slug"].upper()
        postcode = os.environ[f"RECIPIENT_{slug}_POSTCODE"]
        notify_email = os.environ[f"RECIPIENT_{slug}_EMAIL"]
    else:
        postcode = recipient["postcode"]
        notify_email = recipient["notify_email"]
    return postcode, notify_email
```

Then in `main()`, replace the lines (around 302–303):
```python
        postcode = recipient["postcode"]
        radius_km = recipient["radius_km"]
        notify_email = recipient["notify_email"]
```
with:
```python
        postcode, notify_email = resolve_recipient(recipient)
        radius_km = recipient["radius_km"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_check_spills.py::TestResolveRecipient -v
```
Expected: all PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add check_spills.py tests/test_check_spills.py
git commit -m "feat: resolve slug-backed recipients from env vars in check_spills"
```

---

### Task 5: Update `configure.py` listing and editing to handle slug recipients

**Files:**
- Modify: `configure.py:107-128` (listing and edit paths in `main()`)
- Test: `tests/test_configure.py` (integration via monkeypatching `input`)

- [ ] **Step 1: Write failing tests**

Add a new `TestConfigureMainSlugDisplay` class to `tests/test_configure.py`:

```python
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
        configure.main()
        captured = capsys.readouterr()
        assert "GL5 1HE" in captured.out
        assert "a@b.com" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_configure.py::TestConfigureMainSlugDisplay -v
```
Expected: FAIL (KeyError on `r['postcode']` for slug recipient)

- [ ] **Step 3: Fix listing loop in `configure.py`**

Replace the single `print` inside the listing loop (line 111):
```python
            print(f"  {i}) {r['postcode']} | {r['radius_km']}km | {r['notify_email']}")
```
with:
```python
            if "slug" in r:
                print(f"  {i}) [secrets: {r['slug']}] | {r['radius_km']}km")
            else:
                print(f"  {i}) {r['postcode']} | {r['radius_km']}km | {r['notify_email']}")
```

- [ ] **Step 4: Fix edit path in `configure.py`**

Replace the edit block (lines 122–128) with branched logic:

```python
        elif choice_r.startswith("e"):
            try:
                n = int(choice_r[1:].strip()) - 1
                r = recipients[n]
                if "slug" in r:
                    slug_upper = r["slug"].upper()
                    print(f"Note: postcode and email are stored in GitHub Secrets.")
                    print(f"To update them run:")
                    print(f"  gh secret set RECIPIENT_{slug_upper}_POSTCODE")
                    print(f"  gh secret set RECIPIENT_{slug_upper}_EMAIL")
                    r["radius_km"] = int(_prompt("Radius (km)", str(r["radius_km"])))
                else:
                    r["postcode"] = _prompt("Postcode", r["postcode"])
                    r["radius_km"] = int(_prompt("Radius (km)", str(r["radius_km"])))
                    r["notify_email"] = _prompt("Email", r["notify_email"])
            except (ValueError, IndexError):
                print("Invalid selection.")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_configure.py::TestConfigureMainSlugDisplay -v
```
Expected: all PASS

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "fix: listing and edit paths handle slug-backed recipients"
```

---

### Task 6: Add `gh` availability check and secret-backed add flow to `configure.py`

**Files:**
- Modify: `configure.py` (imports, `main()` — the add recipient block)
- Test: `tests/test_configure.py`

- [ ] **Step 1: Write failing tests**

Add to the top-level imports in `tests/test_configure.py`:

```python
from unittest.mock import MagicMock
```

Then add `TestAddSlugRecipient` to `tests/test_configure.py`:

```python
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
            "GL5 1HE",  # postcode (sent to gh, not stored)
            "a@b.com",  # email (sent to gh, not stored)
            "d",        # done
        ])
        result = self._run_add(tmp_path, monkeypatch, inputs)
        slugs = [r.get("slug") for r in result["recipients"] if "slug" in r]
        assert "alice" in slugs
        postcodes = [r.get("postcode") for r in result["recipients"] if "postcode" in r]
        assert "GL5 1HE" not in postcodes  # the slug recipient's postcode not in config

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_configure.py::TestAddSlugRecipient -v
```
Expected: all FAIL

- [ ] **Step 3: Add imports to `configure.py`**

Add at the top of `configure.py`:
```python
import shutil
import subprocess
```

- [ ] **Step 4: Update `main()` in `configure.py`**

At the start of `main()`, after the greeting, add:
```python
gh_available = bool(shutil.which("gh"))
```

Add `new_slugs_this_session = []` immediately before the `while True:` recipient loop (not inside it).

Replace the add-recipient block (`if choice_r == "a":`) with:

```python
        if choice_r == "a":
            radius_km = int(_prompt("Radius (km)", "20"))
            use_secrets = False
            if gh_available:
                use_secrets = input("Store postcode and email in GitHub Secrets? [y/N]: ").strip().lower() == "y"
            if use_secrets:
                # Prompt for and validate slug
                while True:
                    slug = _prompt("Slug (letters, digits, underscores only)")
                    if not re.match(r'^[A-Za-z0-9_]+$', slug):
                        print("Invalid slug: use only letters, digits, underscores.")
                        continue
                    if any(r.get("slug") == slug for r in recipients):
                        print(f"Slug '{slug}' already in use. Choose another.")
                        continue
                    break
                postcode = _prompt("Postcode")
                slug_upper = slug.upper()
                result = subprocess.run(
                    ["gh", "secret", "set", f"RECIPIENT_{slug_upper}_POSTCODE", "--body", postcode],
                    capture_output=True,
                )
                if result.returncode != 0:
                    print(f"ERROR: gh secret set failed: {result.stderr.decode()}", file=sys.stderr)
                    continue
                email = _prompt("Email")
                result = subprocess.run(
                    ["gh", "secret", "set", f"RECIPIENT_{slug_upper}_EMAIL", "--body", email],
                    capture_output=True,
                )
                if result.returncode != 0:
                    print(f"ERROR: gh secret set failed: {result.stderr.decode()}", file=sys.stderr)
                    print(f"Note: RECIPIENT_{slug_upper}_POSTCODE was already set.", file=sys.stderr)
                    print(f"Clean up with: gh secret delete RECIPIENT_{slug_upper}_POSTCODE", file=sys.stderr)
                    continue
                recipients.append({"slug": slug, "radius_km": radius_km})
                new_slugs_this_session.append(slug)
            else:
                postcode = _prompt("Postcode")
                email = _prompt("Email")
                recipients.append({"postcode": postcode, "radius_km": radius_km, "notify_email": email})
```

Also add `new_slugs_this_session = []` just before the `while True:` recipient loop.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_configure.py::TestAddSlugRecipient -v
```
Expected: all PASS

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "feat: add gh secret flow when adding slug-backed recipients"
```

---

### Task 7: Wire up `patch_workflow_env` and update remove + post-setup message

**Files:**
- Modify: `configure.py` — remove path, final block of `main()`
- Test: `tests/test_configure.py`

- [ ] **Step 1: Write failing tests**

Add `TestRemoveSlugRecipient` and `TestFinalWireup` to `tests/test_configure.py`:

```python
class TestRemoveSlugRecipient:
    def test_remove_prints_cleanup_hint(self, tmp_path, monkeypatch, capsys):
        config = tmp_path / "config.yml"
        config.write_text(
            "lookback_hours: 24\n"
            "recipients:\n"
            "  - slug: alice\n"
            "    radius_km: 15\n"
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
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")
        inputs = iter(["3", "", "r1", "d"])  # "" accepts default hour
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        configure.main()
        captured = capsys.readouterr()
        assert "RECIPIENT_ALICE_POSTCODE" in captured.out
        assert "gh secret delete" in captured.out


class TestFinalWireup:
    def test_patch_workflow_env_called_with_current_slugs(self, tmp_path, monkeypatch):
        """After configure, workflow file contains env vars for current slug recipients."""
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
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        inputs = iter([
            "3", "",  # daily schedule, accept default hour
            "a", "15", "y", "bob", "SW1A 2AA", "b@b.com",
            "d",
        ])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        configure.main()
        wf_content = workflow.read_text()
        assert "RECIPIENT_BOB_POSTCODE: ${{ secrets.RECIPIENT_BOB_POSTCODE }}" in wf_content

    def test_post_setup_message_lists_set_secrets(self, tmp_path, monkeypatch, capsys):
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
        monkeypatch.setattr("configure.CONFIG_PATH", str(config))
        monkeypatch.setattr("configure.WORKFLOW_PATH", str(workflow))
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/gh")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)
        inputs = iter([
            "3", "",  # daily schedule, accept default hour
            "a", "15", "y", "carol", "SW1A 2AA", "c@c.com",
            "d",
        ])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        configure.main()
        captured = capsys.readouterr()
        assert "RECIPIENT_CAROL_POSTCODE" in captured.out
        assert "already set" in captured.out.lower() or "set this session" in captured.out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_configure.py::TestRemoveSlugRecipient tests/test_configure.py::TestFinalWireup -v
```
Expected: FAIL

- [ ] **Step 3: Update remove path in `configure.py`**

Replace the entire `elif choice_r.startswith("r"):` block with:

```python
        elif choice_r.startswith("r"):
            try:
                n = int(choice_r[1:].strip()) - 1
                if len(recipients) == 1:
                    print("ERROR: must have at least one recipient.")
                else:
                    removed = recipients[n]
                    recipients.pop(n)
                    if "slug" in removed:
                        slug_upper = removed["slug"].upper()
                        print(f"Note: GitHub Secrets RECIPIENT_{slug_upper}_POSTCODE and RECIPIENT_{slug_upper}_EMAIL were not deleted automatically.")
                        print(f"Run: gh secret delete RECIPIENT_{slug_upper}_POSTCODE && gh secret delete RECIPIENT_{slug_upper}_EMAIL")
            except (ValueError, IndexError):
                print("Invalid selection.")
```

- [ ] **Step 4: Wire `patch_workflow_env` and update final message in `configure.py`**

After `write_config(lookback_hours, recipients)` and `patch_workflow_cron(cron_expr)`, add:

```python
    current_slugs = [r["slug"] for r in recipients if "slug" in r]
    patch_workflow_env(current_slugs)
    print(f"✓ Updated {WORKFLOW_PATH} (env vars)")
```

Replace the final `print(f"""...""")` block with:

```python
    secrets_set_msg = ""
    if new_slugs_this_session:
        secret_names = ", ".join(
            f"RECIPIENT_{s.upper()}_POSTCODE, RECIPIENT_{s.upper()}_EMAIL"
            for s in new_slugs_this_session
        )
        secrets_set_msg = f"\nSecrets already set this session:\n  {secret_names}\n"

    print(f"""
Setup complete!

Still to do:
  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD
{secrets_set_msg}
Then push and test:

  git add {CONFIG_PATH} {WORKFLOW_PATH}
  git commit -m "configure sewage alerts"
  git push -u origin main
  gh workflow run check_spills.yml
""")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_configure.py::TestRemoveSlugRecipient tests/test_configure.py::TestFinalWireup -v
```
Expected: all PASS

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add configure.py tests/test_configure.py
git commit -m "feat: wire patch_workflow_env, remove hint, updated setup message"
```

---

### Task 8: Test `load_config` in `check_spills.py` for slug recipients

**Files:**
- Test: `tests/test_check_spills.py`

- [ ] **Step 1: Write tests confirming `load_config` handles slug recipients**

Add to `TestLoadConfig` in `tests/test_check_spills.py`:

```python
def test_loads_slug_recipient(self, tmp_path):
    f = tmp_path / "config.yml"
    f.write_text(
        "lookback_hours: 24\n"
        "recipients:\n"
        "  - slug: alice\n"
        "    radius_km: 15\n"
    )
    result = check_spills.load_config(str(f))
    r = result["recipients"][0]
    assert r["slug"] == "alice"
    assert r["radius_km"] == 15
    assert "postcode" not in r
    assert "notify_email" not in r

def test_loads_mixed_recipients(self, tmp_path):
    f = tmp_path / "config.yml"
    f.write_text(
        "lookback_hours: 24\n"
        "recipients:\n"
        "  - slug: alice\n"
        "    radius_km: 15\n"
        '  - postcode: "GL5 1HE"\n'
        "    radius_km: 20\n"
        '    notify_email: "a@b.com"\n'
    )
    result = check_spills.load_config(str(f))
    assert result["recipients"][0]["slug"] == "alice"
    assert result["recipients"][1]["postcode"] == "GL5 1HE"
```

- [ ] **Step 2: Run tests — these should PASS immediately (load_config is unchanged)**

```bash
python -m pytest tests/test_check_spills.py::TestLoadConfig -v
```
Expected: all PASS (no code change needed — confirms the parser works as specced)

- [ ] **Step 3: Run full test suite one final time**

```bash
python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_check_spills.py
git commit -m "test: confirm load_config handles slug recipients correctly"
```
