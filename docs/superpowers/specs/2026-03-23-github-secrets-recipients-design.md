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

The slug must be a short alphanumeric-and-hyphen string (e.g. `alice`, `home`, `mum`). It is uppercased to form secret names: `RECIPIENT_ALICE_POSTCODE`, `RECIPIENT_ALICE_EMAIL`.

## Changes to configure.py

### Adding / editing a recipient

After collecting the radius, the script asks:

```
Store postcode and email in GitHub Secrets? [y/N]:
```

**If N (default):** collect postcode and email as today; store all three fields in config.

**If Y (secret-backed):**
1. Prompt for a slug (short identifier, e.g. `alice`).
2. Prompt for postcode; run `gh secret set RECIPIENT_{SLUG}_POSTCODE --body "<value>"`.
3. Prompt for email; run `gh secret set RECIPIENT_{SLUG}_EMAIL --body "<value>"`.
4. Store only `slug` and `radius_km` in config.
5. Patch the workflow YAML to expose the two new secrets as env vars (see below).

If `gh` is not available or the secret-set commands fail, print a clear error and abort adding that recipient.

### Listing recipients

```
Current recipients:
  1) [secrets: alice]  | 20km
  2) SW1A 2AA | 15km | bob@example.com
```

### Removing a secret-backed recipient

Remove from config and patch the workflow as normal. Print a reminder:

```
Note: GitHub Secrets RECIPIENT_ALICE_POSTCODE and RECIPIENT_ALICE_EMAIL were not deleted automatically.
Run: gh secret delete RECIPIENT_ALICE_POSTCODE && gh secret delete RECIPIENT_ALICE_EMAIL
```

### write_config changes

`write_config` handles both shapes:

```yaml
# secret-backed
  - slug: alice
    radius_km: 15

# plaintext
  - postcode: "SW1A 2AA"
    radius_km: 20
    notify_email: "bob@example.com"
```

### Workflow patching

`configure.py` already patches the cron schedule. It will also manage the `env:` block in the workflow, rewriting it on every run to reflect the current recipient list. The fixed secrets (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`) are always present; `RECIPIENT_*` entries are added/removed to match the current set of slug-based recipients.

Example resulting env block:

```yaml
env:
  GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
  GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
  RECIPIENT_ALICE_POSTCODE: ${{ secrets.RECIPIENT_ALICE_POSTCODE }}
  RECIPIENT_ALICE_EMAIL: ${{ secrets.RECIPIENT_ALICE_EMAIL }}
```

The patch targets the `env:` key under the `Check for nearby spills` step, replacing it in full each time.

## Changes to check_spills.py

### load_config / load_recipients

`load_config` is unchanged structurally; it returns recipients with whatever fields are present in the YAML.

At runtime, when iterating recipients in `main()`, add a resolution step before using `postcode` and `notify_email`:

```python
if "slug" in recipient:
    slug = recipient["slug"].upper()
    postcode = os.environ[f"RECIPIENT_{slug}_POSTCODE"]
    notify_email = os.environ[f"RECIPIENT_{slug}_EMAIL"]
else:
    postcode = recipient["postcode"]
    notify_email = recipient["notify_email"]
```

A missing environment variable raises `KeyError`, which will surface as an unhandled exception with a clear message indicating which variable is absent. No special error handling is needed beyond what the workflow log provides.

### Backwards compatibility

The existing `load_config` backwards-compat path (flat format → recipients list) is unaffected; it only fires when `postcode` is present at the top level.

## Out of Scope

- Migrating existing plaintext recipients to secrets automatically.
- Validating postcode format during configure (already not done).
- Deleting secrets automatically on recipient removal.
