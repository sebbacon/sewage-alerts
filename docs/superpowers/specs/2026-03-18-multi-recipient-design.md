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

**Key ordering:** Within each recipient entry, keys may appear in any order. The parser handles this.

**Top-level keys must appear before `recipients:`.** The parser does not handle top-level keys after the list begins.

**Backwards compatibility:** If no `recipients:` key is present (old flat format with top-level `postcode`, `radius_km`, `notify_email`), `load_config()` wraps those three fields into a single-element recipients list. No manual migration required.

---

## `load_config()` Changes (`check_spills.py`)

The existing flat-key parser is replaced. The new parser uses an explicit state machine. It returns:

```python
{
    "lookback_hours": 24,
    "recipients": [
        {"postcode": "GL5 1HE", "radius_km": 45, "notify_email": "seb.bacon@gmail.com"},
        ...
    ]
}
```

### Parser logic (stdlib only, no PyYAML in runtime code)

The parser triggers a new recipient entry on any line starting with `- ` (a YAML list item marker) rather than specifically `- postcode:`. This makes the parser tolerant of any key order within a recipient entry — including the alphabetic order produced by `yaml.dump` in tests.

```python
def load_config(path="config.yml"):
    top = {}
    recipients = []
    in_recipients = False   # True once "recipients:" line is seen
    current = None          # dict being built for the current recipient entry

    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "recipients:":
                in_recipients = True
                continue
            if in_recipients:
                if stripped.startswith("- "):
                    # New recipient entry
                    if current is not None:
                        recipients.append(current)
                    current = {}
                    key, _, val = stripped[2:].partition(":")
                    _set_recipient_field(current, key.strip(), val.strip().strip('"'))
                elif current is not None and ":" in stripped:
                    key, _, val = stripped.partition(":")
                    _set_recipient_field(current, key.strip(), val.strip().strip('"'))
            else:
                if ":" in stripped:
                    key, _, val = stripped.partition(":")
                    top[key.strip()] = val.strip().strip('"').strip("'")

    if current is not None:
        recipients.append(current)

    if "lookback_hours" in top:
        top["lookback_hours"] = int(top["lookback_hours"])

    # Backwards compat: flat format
    if not recipients and "postcode" in top:
        recipients = [{
            "postcode": top.pop("postcode"),
            "radius_km": int(top.pop("radius_km")),
            "notify_email": top.pop("notify_email"),
        }]

    top["recipients"] = recipients
    return top


def _set_recipient_field(d: dict, key: str, val: str) -> None:
    """Set a recipient dict field, casting radius_km to int."""
    if key == "radius_km":
        d[key] = int(val)
    else:
        d[key] = val
```

### Test updates (`tests/test_check_spills.py`)

- `TestLoadConfig` is rewritten to use the new multi-recipient format and assert the new return shape.
- A new `TestLoadConfigBackwardsCompat` class verifies the flat-format fallback returns a single-element `recipients` list.

---

## `main()` Changes (`check_spills.py`)

`main()` iterates over all recipients. The existing signature is unchanged:

```python
def main(
    config_path: str = "config.yml",
    companies_path: str = "companies.yml",
    postcode_override: str | None = None,
    radius_km_override: int | None = None,
    notify_email_override: str | None = None,
) -> None:
```

### Removed code

The following lines from the current `main()` body are **deleted**:

- The three lines that read `postcode`, `radius_km`, `notify_email` from `config` (currently lines 246–249: `postcode = config["postcode"]` etc.)
- The `sys.exit(1)` calls at the end of the `if rows:` branch and the `elif failures:` branch (the current deferred-exit pattern is replaced by `any_failures` flag — see below)
- The `return` at the end of the `else:` branch (no longer needed — the loop naturally continues to the next recipient)

### Recipient list

```python
config = load_config(config_path)
lookback_hours = config["lookback_hours"]

if postcode_override:
    recipients = [{"postcode": postcode_override, "radius_km": radius_km_override, "notify_email": notify_email_override}]
else:
    recipients = config["recipients"]
```

### Before the loop

```python
validate_lookback_hours(lookback_hours)   # called once, before the recipient loop
companies = load_companies(companies_path)
```

### Per-recipient loop

For each recipient, the full pipeline runs independently. The `failures` list is reset per recipient.

```python
any_failures = False
for recipient in recipients:
    postcode = recipient["postcode"]
    radius_km = recipient["radius_km"]
    notify_email = recipient["notify_email"]

    home_lat, home_lon = get_postcode_coords(postcode)  # exits process on error (intentional)

    rows = []
    failures = []
    for company in companies:
        try:
            features = query_spills(home_lat, home_lon, radius_km, lookback_hours, company["query_url"])
            rows += [format_spill_row(f, home_lat, home_lon, company["name"]) for f in features]
        except Exception as exc:
            failures.append((company["name"], str(exc)))
            print(f"WARNING: {company['name']} query failed: {exc}", file=sys.stderr)

    if failures:
        any_failures = True

    if rows:
        subject, html = build_html_email(rows, postcode, radius_km, failures=failures or None)
        text = build_text_email(rows, postcode, radius_km, failures=failures or None)
        send_email(subject, html, text, notify_email, from_addr, password)
        print(f"Alert sent: {subject}")
    elif failures:
        n = len(failures)
        subject = f"Sewage alert warning: {n} company/companies could not be queried near {postcode}"
        body_lines = [f"{n} company/companies could not be queried — results may be incomplete:\n"]
        body_lines += [f"- {name}: {err}" for name, err in failures]
        text = "\n".join(body_lines)
        html = (
            f"<html><body><p>{n} company/companies could not be queried — results may be incomplete:</p><ul>"
            + "".join(f"<li>{name}: {err}</li>" for name, err in failures)
            + "</ul></body></html>"
        )
        send_email(subject, html, text, notify_email, from_addr, password)
        print(f"Warning sent: {subject}")
    else:
        print(f"No spills found within {radius_km}km of {postcode} in the last {lookback_hours}h.")

if any_failures:
    sys.exit(1)
```

**Notes on error handling within the loop:**

- `get_postcode_coords` calls `sys.exit(1)` on a bad postcode — this terminates the whole process and is intentional. A misconfigured postcode is a fatal setup error.
- `send_email` calls `sys.exit(1)` on SMTP failure — this also terminates the whole process. SMTP failures abort the run, which is acceptable since they indicate infrastructure problems affecting all recipients equally.

### Empty recipients

If `recipients` is an empty list, `main()` loops zero times and exits 0 silently. Nothing configured means nothing to do.

### Test updates (`tests/test_check_spills.py`)

`TestMain.BASE_CONFIG` is updated to the new multi-recipient shape:

```python
BASE_CONFIG = {
    "lookback_hours": 24,
    "recipients": [
        {"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "user@example.com"},
    ],
}
```

`_write_config` continues to use `yaml.dump(self.BASE_CONFIG)`. Because the parser now triggers on any `- ` line (not specifically `- postcode:`), it correctly handles `yaml.dump`'s alphabetic key ordering.

A new test `test_runs_for_each_recipient` verifies that with two recipients in the config, `sendmail` is called twice when both have spills. It follows the same mock pattern as `test_sends_email_when_spills_found`, but uses a `BASE_CONFIG` with two recipients (different postcodes, different notify_emails). The `fake_urlopen` routes postcode lookups by `"postcodes.io" in url` and returns `features_payload` for all ArcGIS queries. `sendmail` should be called once per recipient.

---

## CLI Override Validation (`check_spills.py` `__main__` block)

```python
overrides = [args.postcode, args.radius, args.email]
if any(v is not None for v in overrides) and not all(v is not None for v in overrides):
    print("ERROR: --postcode, --radius, and --email must all be provided together.", file=sys.stderr)
    sys.exit(1)
```

---

## `configure.py` Changes

`configure.py` is a developer-run setup tool, not a cron-executed script. It may use PyYAML for parsing (PyYAML is already in `requirements-dev.txt`).

### `read_config()`

Rewritten using `yaml.safe_load` to parse the new multi-recipient format. Returns `{"lookback_hours": int, "recipients": [...]}` with the same backwards-compat fallback as `load_config()`. On `FileNotFoundError`, returns `{"recipients": []}`.

```python
def read_config(path: str = CONFIG_PATH) -> dict:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {"recipients": []}

    # Backwards compat: flat format
    if "recipients" not in data and "postcode" in data:
        data["recipients"] = [{
            "postcode": data.pop("postcode"),
            "radius_km": data.pop("radius_km"),
            "notify_email": data.pop("notify_email"),
        }]
    data.setdefault("recipients", [])
    return data
```

This requires `import yaml` at the top of `configure.py` (add it).

### `write_config()`

New signature:

```python
def write_config(lookback_hours: int, recipients: list[dict], path: str = CONFIG_PATH) -> None:
```

Writes the new multi-recipient YAML format:

```python
def write_config(lookback_hours: int, recipients: list[dict], path: str = CONFIG_PATH) -> None:
    with open(path, "w") as f:
        f.write(f"lookback_hours: {lookback_hours}\n")
        f.write("recipients:\n")
        for r in recipients:
            f.write(f'  - postcode: "{r["postcode"]}"\n')
            f.write(f'    radius_km: {r["radius_km"]}\n')
            f.write(f'    notify_email: "{r["notify_email"]}"\n')
```

### Interactive flow in `configure.main()`

The following lines from the current `configure.main()` are **removed**:

- `existing = read_config()` (line 76)
- `postcode = _prompt(...)` (line 78)
- `notify_email = _prompt(...)` (line 79)
- `radius_km = int(_prompt(...))` (line 80)

These are replaced by `recipients = read_config().get("recipients", [])` placed after the schedule prompt, and the recipient management loop below.

The schedule/cron prompt block (lines 82–104, including the custom `choice == 4` branch) is **unchanged**.

The call `write_config(postcode, radius_km, lookback_hours, notify_email)` on line 106 is replaced by `write_config(lookback_hours, recipients)`.

The success message and `git add` instructions printed after the call are **unchanged**.

#### Recipient management loop

After the schedule prompts, load and manage recipients:

```python
recipients = read_config().get("recipients", [])

while True:
    print("\nCurrent recipients:")
    if recipients:
        for i, r in enumerate(recipients, 1):
            print(f"  {i}) {r['postcode']} | {r['radius_km']}km | {r['notify_email']}")
    else:
        print("  (none)")
    choice = input("\n[a]dd  [e]dit N  [r]emove N  [d]one: ").strip().lower()
    if choice == "a":
        postcode = _prompt("Postcode")
        radius_km = int(_prompt("Radius (km)", "20"))
        email = _prompt("Email")
        recipients.append({"postcode": postcode, "radius_km": radius_km, "notify_email": email})
    elif choice.startswith("e"):
        n = int(choice[1:].strip()) - 1
        r = recipients[n]
        r["postcode"] = _prompt("Postcode", r["postcode"])
        r["radius_km"] = int(_prompt("Radius (km)", str(r["radius_km"])))
        r["notify_email"] = _prompt("Email", r["notify_email"])
    elif choice.startswith("r"):
        n = int(choice[1:].strip()) - 1
        if len(recipients) == 1:
            print("ERROR: must have at least one recipient.")
        else:
            recipients.pop(n)
    elif choice == "d":
        if not recipients:
            print("ERROR: must have at least one recipient.")
        else:
            break
```

### Test updates (`tests/test_configure.py`)

- `TestWriteConfig`: updated to call `write_config(lookback_hours=24, recipients=[{"postcode": "GL5 1HE", "radius_km": 20, "notify_email": "test@example.com"}])` and use `yaml.safe_load` to assert the written structure.
- `TestReadConfig` (new): verifies multi-recipient format parsing and backwards-compat fallback.

---

## Files Changed

| File | Change |
|---|---|
| `config.yml` | Migrated to new multi-recipient format |
| `check_spills.py` | `load_config()` + `_set_recipient_field()` rewritten; `main()` loops over recipients; CLI override validation added |
| `configure.py` | `import yaml` added; `read_config()`, `write_config()` updated; `main()` gains recipient management loop |
| `tests/test_check_spills.py` | `TestLoadConfig` updated; `TestLoadConfigBackwardsCompat` added; `TestMain` updated |
| `tests/test_configure.py` | `TestWriteConfig` updated; `TestReadConfig` added |
