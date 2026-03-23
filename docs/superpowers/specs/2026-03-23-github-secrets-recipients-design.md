# Design: Optional GitHub Secrets for Recipient PII

Date: 2026-03-23

## Problem

The current `config.yml` stores each recipient's email address and postcode in plaintext. Since `config.yml` is committed to the repository, this places PII (email + postcode) in the public domain. Users who want privacy need an alternative.

## Solution

Make it optional, per recipient, to store the sensitive fields (postcode and email) in GitHub Secrets rather than in `config.yml`. The config file stores only a short slug and the radius; the sensitive data lives entirely in encrypted GitHub Secrets.

Both modes coexist in the same config file and codebase.

## Config Format

Two recipient shapes are valid in `config.yml`:

```yaml
recipients:
  # Plaintext (existing behaviour, unchanged)
  - postcode: "SW1A 2AA"
    radius_km: 20
    notify_email: "bob@example.com"

  # Secret-backed (no PII committed)
  - slug: alice
    radius_km: 15
```

The presence of `slug` (instead of `postcode`) is the discriminator. No extra flag is needed.

The slug must be a short string of letters, digits, and underscores only — no hyphens. It is uppercased to form secret names: `RECIPIENT_ALICE_POSTCODE`, `RECIPIENT_ALICE_EMAIL`. `configure.py` must validate the slug against `^[A-Za-z0-9_]+$` and re-prompt on failure.

Slugs must be unique across all recipients. `configure.py` must check for duplicates at add time and reject collisions. If duplicate slugs exist in `config.yml` (e.g. hand-edited), `read_config` in `configure.py` should print a warning to stderr and continue.

## Changes to configure.py

### New imports required

Add to `configure.py`:
```python
import shutil
import subprocess
```

`shutil` is needed for `shutil.which("gh")`. `subprocess` is needed to invoke `gh secret set` and capture its exit code. Use `subprocess.run(["gh", "secret", "set", name, "--body", value], capture_output=True)` and check `.returncode`.

### `gh` availability check

At the start of `main()`, check `shutil.which("gh")`. Store the result as a boolean `gh_available`. If `gh` is not available, skip the secrets prompt when adding a recipient and proceed with plaintext.

### read_config changes

`read_config` uses `yaml.safe_load`. YAML parses `slug: 123` as an integer. After loading, cast each recipient's `slug` value to `str` if present:

```python
for r in data.get("recipients", []):
    if "slug" in r:
        r["slug"] = str(r["slug"])
```

### Adding a recipient

After collecting the radius, and only if `gh_available`, the script asks:

```
Store postcode and email in GitHub Secrets? [y/N]:
```

**If N (default):** collect postcode and email as today.

**If Y (secret-backed):**
1. Prompt for a slug. Validate against `^[A-Za-z0-9_]+$`; re-prompt if invalid. Check uniqueness with `any(r.get("slug") == slug for r in recipients)`; reject and re-prompt if collision.
2. Prompt for postcode; run `gh secret set RECIPIENT_{SLUG}_POSTCODE --body "<value>"`. If this fails (non-zero exit), print the error, do not append the recipient, and return to the main menu.
3. Prompt for email; run `gh secret set RECIPIENT_{SLUG}_EMAIL --body "<value>"`. If this fails, print the error, do not append the recipient, and return to the main menu. Note to the user that the postcode secret was already set and will need manual cleanup if they abandon this slug (`gh secret delete RECIPIENT_{SLUG}_POSTCODE`). Do not attempt automatic rollback.
4. Append `{"slug": slug, "radius_km": radius_km}` to the in-memory recipients list.

If the user retries with the same slug after a failure at step 3, the duplicate-slug check will not block them (the recipient was not appended). The second attempt will overwrite the orphaned postcode secret at step 2, which is harmless.

`write_config` and `patch_workflow_env` are called once at the end of `main()` after all editing is done.

### Editing a recipient

When the user selects `e N`:

- If the recipient has a `slug`, only allow editing the radius using `_prompt("Radius (km)", str(r["radius_km"]))`. Print a note before the prompt:
  ```
  Note: postcode and email are stored in GitHub Secrets.
  To update them run:
    gh secret set RECIPIENT_ALICE_POSTCODE
    gh secret set RECIPIENT_ALICE_EMAIL
  ```
  Do not access `r["postcode"]` or `r["notify_email"]` for slug-backed recipients.

- If the recipient has a `postcode`, edit as today.

Converting between slug-backed and plaintext is not supported; the user should remove and re-add.

### Listing recipients

**This is a crash fix as well as a display change.** The existing listing loop accesses `r["postcode"]` and `r["notify_email"]` unconditionally; this raises `KeyError` immediately for any slug-backed recipient loaded from config. Replace the listing line with:

```python
if "slug" in r:
    print(f"  {i}) [secrets: {r['slug']}] | {r['radius_km']}km")
else:
    print(f"  {i}) {r['postcode']} | {r['radius_km']}km | {r['notify_email']}")
```

### Removing a secret-backed recipient

Remove from the in-memory list as normal. Print a reminder:

```
Note: GitHub Secrets RECIPIENT_ALICE_POSTCODE and RECIPIENT_ALICE_EMAIL were not deleted automatically.
Run: gh secret delete RECIPIENT_ALICE_POSTCODE && gh secret delete RECIPIENT_ALICE_EMAIL
```

### write_config changes

`write_config` must branch on recipient shape. For slug-backed recipients, `slug` is always written as the first field on the `- ` line (required by `check_spills.py`'s hand-rolled parser — see below):

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

### patch_workflow_env (new function)

Add `patch_workflow_env(slugs: list[str], workflow_path: str) -> None`. It rewrites the `env:` block under the `Check for nearby spills` step unconditionally — even when `slugs` is empty, it must rewrite the block so that previously injected slug env vars are removed when a slug recipient is deleted.

The replacement string is built as:

```python
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
```

The regex replaces from the `env:` line to end of file (the env block is always the last content in the workflow file). The replacement includes the trailing newline on the last line, so the file ends with exactly one newline:

```python
content = re.sub(r'        env:.*', replacement.rstrip("\n"), content, flags=re.DOTALL)
```

After substitution, write `content + "\n"` to the file to ensure a single trailing newline.

Called from `main()` once at the end, immediately after `patch_workflow_cron`.

### Post-setup summary message

Always include the two `GMAIL_*` secret commands. If any slug-backed recipients were successfully appended to the list during the session, note that their secrets were already set. Omit this section if none:

```
Setup complete!

Still to do:
  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD

Secrets already set this session:
  RECIPIENT_ALICE_POSTCODE, RECIPIENT_ALICE_EMAIL

Then push and test:
  git add config.yml .github/workflows/check_spills.yml
  git commit -m "configure sewage alerts"
  git push -u origin main
  gh workflow run check_spills.yml
```

## Changes to check_spills.py

### load_config

`load_config` uses a hand-rolled line parser that reads any `key: value` pair under a recipient entry into the dict. For slug-backed recipients, this correctly produces `{"slug": "alice", "radius_km": 15}` — but only if `slug` is the first key on the `- ` line. `write_config` always writes `slug` first, so machine-written configs are safe. Hand-edited configs that place `radius_km` first would cause `slug` to be silently dropped; this is pre-existing parser fragility and is out of scope to fix here.

`load_config` does not use `yaml.safe_load`, so there is no integer-slug issue (all values are strings from the hand-rolled parser).

### Recipient resolution in main()

Before using `postcode` and `notify_email` for each recipient, add a resolution step:

```python
if "slug" in recipient:
    slug = recipient["slug"].upper()
    postcode = os.environ[f"RECIPIENT_{slug}_POSTCODE"]
    notify_email = os.environ[f"RECIPIENT_{slug}_EMAIL"]
else:
    postcode = recipient["postcode"]
    notify_email = recipient["notify_email"]
```

A missing env var raises `KeyError` with a message naming the missing variable. No additional handling needed — the workflow log surfaces it immediately.

### CLI override flags

`--postcode`, `--radius`, `--email` remain plaintext-only and unchanged. Intentional.

### Backwards compatibility

Existing flat-format backwards-compat path is unaffected.

## Out of Scope

- Migrating existing plaintext recipients to secrets automatically.
- Validating postcode format during configure.
- Deleting secrets automatically on recipient removal.
- Converting a recipient between slug-backed and plaintext in-place.
- Fixing the hand-rolled parser's first-key-must-be-on-dash-line fragility.
