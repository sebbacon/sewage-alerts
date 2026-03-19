# Multi-Recipient Support Design

## Goal

Allow `config.yml` to hold a list of postcode/radius/email triples so a single cron run can notify multiple people about spills near different locations. A single `lookback_hours` / cron schedule applies to all recipients.

---

## Config Format

`config.yml` gains a `recipients:` list. `lookback_hours` stays at the top level:

```yaml
lookback_hours: 24
recipients:
  - postcode: "GL5 1HE"
    radius_km: 45
    notify_email: "seb.bacon@gmail.com"
  - postcode: "SW1A 1AA"
    radius_km: 10
    notify_email: "other@example.com"
```

**Backwards compatibility:** If no `recipients:` key is present (old flat format), `load_config()` wraps the three flat fields (`postcode`, `radius_km`, `notify_email`) into a single-element recipients list. No manual migration required.

---

## `load_config()` Changes

The existing flat-key parser in `check_spills.py` is replaced with a parser that handles the new structure. It returns:

```python
{
    "lookback_hours": 24,
    "recipients": [
        {"postcode": "GL5 1HE", "radius_km": 45, "notify_email": "seb.bacon@gmail.com"},
        ...
    ]
}
```

Parser logic (stdlib only, no PyYAML in runtime code):
- Top-level `key: value` lines populate the top-level dict (just `lookback_hours` in practice).
- `recipients:` line begins list parsing mode.
- `- postcode:` lines start a new recipient dict.
- `radius_km:` and `notify_email:` lines populate the current recipient dict.
- `radius_km` is cast to `int`.

**Backwards compat fallback:** After parsing, if `"recipients"` is absent from the result, construct it from the flat `postcode`/`radius_km`/`notify_email` keys.

The existing `TestLoadConfig` tests are updated to use the new format. A new `TestLoadConfigBackwardsCompat` class verifies the flat-format fallback.

---

## `main()` Changes

`main()` loops over recipients. For each recipient it:
1. Looks up the postcode's coordinates (existing `get_postcode_coords`)
2. Queries all 9 companies (existing per-company loop)
3. Sends an alert email if spills found (or failure email if errors and no spills)

Company query failures are tracked globally across the run: if a company is down, it's down for all recipients. The `failures` list is reset per recipient so each recipient's email correctly reflects which companies failed for their query.

Updated signature:

```python
def main(
    config_path: str = "config.yml",
    companies_path: str = "companies.yml",
    postcode_override: str | None = None,
    radius_km_override: int | None = None,
    notify_email_override: str | None = None,
) -> None:
```

If override values are provided, they form a single synthetic recipient and `config["recipients"]` is ignored entirely.

`sys.exit(1)` is called at the end of `main()` if any company query failed for any recipient.

---

## CLI Override Validation

In the `__main__` block, before calling `main()`:

- If all three of `--postcode`, `--radius`, `--email` are given → pass as overrides (single synthetic recipient).
- If none are given → normal multi-recipient run from config.
- If one or two are given → print error and `sys.exit(1)`.

```python
overrides = [args.postcode, args.radius, args.email]
if any(overrides) and not all(overrides):
    print("ERROR: --postcode, --radius, and --email must all be provided together.", file=sys.stderr)
    sys.exit(1)
```

---

## `configure.py` Changes

### `read_config()`

Updated to read the new multi-recipient format (with the same backwards-compat fallback). Returns:

```python
{"lookback_hours": int, "recipients": [...]}
```

### `write_config()`

Updated signature:

```python
def write_config(lookback_hours: int, recipients: list[dict], path: str = CONFIG_PATH) -> None:
```

Writes the new YAML format:

```python
f.write(f"lookback_hours: {lookback_hours}\n")
f.write("recipients:\n")
for r in recipients:
    f.write(f'  - postcode: "{r["postcode"]}"\n')
    f.write(f'    radius_km: {r["radius_km"]}\n')
    f.write(f'    notify_email: "{r["notify_email"]}"\n')
```

### Interactive flow in `main()`

1. Prompt for schedule/lookback (unchanged).
2. Load existing recipients from config (empty list if none).
3. Enter recipient management loop:

```
Current recipients:
  1) GL5 1HE | 45km | seb.bacon@gmail.com

Options: [a]dd  [e]dit N  [r]emove N  [d]one
```

- **add**: prompt postcode, radius (default 20), email.
- **edit N**: re-prompt with existing values pre-filled.
- **remove N**: remove from list (blocked if it would leave the list empty).
- **done**: exit loop (requires at least one recipient).

4. `write_config(lookback_hours, recipients)` — single call.

---

## Files Changed

| File | Change |
|---|---|
| `config.yml` | Migrated to new multi-recipient format |
| `check_spills.py` | `load_config()` rewritten; `main()` loops over recipients; CLI override validation added |
| `configure.py` | `read_config()`, `write_config()` updated; `main()` gains recipient management loop |
| `tests/test_check_spills.py` | `TestLoadConfig` updated to new format; `TestLoadConfigBackwardsCompat` added; `TestMain` updated for multi-recipient |
| `tests/test_configure.py` | `TestWriteConfig` and `TestReadConfig` updated for new format; recipient management flow tested |
