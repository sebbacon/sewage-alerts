#!/usr/bin/env python3
"""Interactive setup script for sewage alerts."""

import re
import shutil
import subprocess
import sys
import yaml

WORKFLOW_PATH = ".github/workflows/check_spills.yml"
CONFIG_PATH = "config.yml"


def build_cron_and_hours(choice: int, hour: int) -> tuple[str, int]:
    """Return (cron_expression, lookback_hours) for the given menu choice."""
    if choice == 1:
        return "0 */6 * * *", 6
    elif choice == 2:
        return "0 */12 * * *", 12
    elif choice == 3:
        return f"0 {hour} * * *", 24
    else:
        print("Invalid choice, defaulting to daily at 07:00 UTC.", file=sys.stderr)
        return "0 7 * * *", 24


def patch_workflow_cron(cron_expr: str, workflow_path: str = WORKFLOW_PATH) -> None:
    """Replace the cron expression in the workflow YAML file."""
    with open(workflow_path) as f:
        content = f.read()
    new_content = re.sub(
        r"(- cron: ')[^']+(')",
        rf"\g<1>{cron_expr}\g<2>",
        content,
    )
    with open(workflow_path, "w") as f:
        f.write(new_content)


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


def read_config(path: str = CONFIG_PATH) -> dict:
    """Read configuration from a YAML file."""
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {"recipients": []}

    # Backwards compat: old flat format
    if "recipients" not in data and "postcode" in data:
        data["recipients"] = [{
            "postcode": data.pop("postcode"),
            "radius_km": data.pop("radius_km"),
            "notify_email": data.pop("notify_email"),
        }]
    data.setdefault("recipients", [])

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

    return data


def write_config(
    lookback_hours: int,
    recipients: list[dict],
    path: str = CONFIG_PATH,
) -> None:
    """Write configuration to a YAML file."""
    with open(path, "w") as f:
        f.write(f"lookback_hours: {lookback_hours}\n")
        f.write("recipients:\n")
        for r in recipients:
            if "slug" in r:
                f.write(f'  - slug: "{r["slug"]}"\n')
                f.write(f'    radius_km: {r["radius_km"]}\n')
            else:
                f.write(f'  - postcode: "{r["postcode"]}"\n')
                f.write(f'    radius_km: {r["radius_km"]}\n')
                f.write(f'    notify_email: "{r["notify_email"]}"\n')


def _prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("Welcome to Sewage Alerts setup!\n")
    gh_available = bool(shutil.which("gh"))

    print("Check interval:")
    print("  1) Every 6 hours")
    print("  2) Every 12 hours")
    print("  3) Daily (default)")
    print("  4) Custom cron expression")
    choice_str = input("Choice [3]: ").strip() or "3"
    choice = int(choice_str)

    if choice == 4:
        cron_expr = input("Cron expression (e.g. 0 */8 * * *): ").strip()
        if not cron_expr:
            print("ERROR: Cron expression cannot be empty.", file=sys.stderr)
            sys.exit(1)
        try:
            lookback_hours = int(input("Corresponding lookback_hours: ").strip())
        except ValueError:
            print("ERROR: lookback_hours must be an integer.", file=sys.stderr)
            sys.exit(1)
    else:
        hour = 7
        if choice == 3:
            hour = int(_prompt("Hour to run (UTC, 0-23)", "7"))
        cron_expr, lookback_hours = build_cron_and_hours(choice, hour=hour)

    recipients = read_config(CONFIG_PATH).get("recipients", [])

    new_slugs_this_session = []
    while True:
        print("\nCurrent recipients:")
        if recipients:
            for i, r in enumerate(recipients, 1):
                if "slug" in r:
                    print(f"  {i}) [secrets: {r['slug']}] | {r['radius_km']}km")
                else:
                    print(f"  {i}) {r['postcode']} | {r['radius_km']}km | {r['notify_email']}")
        else:
            print("  (none)")
        choice_r = input("\n[a]dd  [e]dit N  [r]emove N  [d]one: ").strip().lower()
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
        elif choice_r.startswith("e"):
            try:
                n = int(choice_r[1:].strip()) - 1
                r = recipients[n]
                if "slug" in r:
                    slug_upper = r["slug"].upper()
                    print("Note: postcode and email are stored in GitHub Secrets.")
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
        elif choice_r.startswith("r"):
            try:
                n = int(choice_r[1:].strip()) - 1
                if len(recipients) == 1:
                    print("ERROR: must have at least one recipient.")
                else:
                    removed_recipient = recipients.pop(n)
                    if "slug" in removed_recipient:
                        slug_upper = removed_recipient["slug"].upper()
                        print(f"Note: GitHub Secrets RECIPIENT_{slug_upper}_POSTCODE and RECIPIENT_{slug_upper}_EMAIL were not deleted automatically.")
                        print(f"Run: gh secret delete RECIPIENT_{slug_upper}_POSTCODE && gh secret delete RECIPIENT_{slug_upper}_EMAIL")
            except (ValueError, IndexError):
                print("Invalid selection.")
        elif choice_r == "d":
            if not recipients:
                print("ERROR: must have at least one recipient.")
            else:
                break

    write_config(lookback_hours, recipients, path=CONFIG_PATH)
    print(f"\n✓ Written {CONFIG_PATH}")

    patch_workflow_cron(cron_expr, workflow_path=WORKFLOW_PATH)
    print(f"✓ Updated {WORKFLOW_PATH}")

    slugs = [r["slug"] for r in recipients if "slug" in r]
    patch_workflow_env(slugs, workflow_path=WORKFLOW_PATH)

    session_secrets_section = ""
    if new_slugs_this_session:
        lines = ["Secrets already set this session:"]
        for slug in new_slugs_this_session:
            s = slug.upper()
            lines.append(f"  RECIPIENT_{s}_POSTCODE, RECIPIENT_{s}_EMAIL")
        session_secrets_section = "\n" + "\n".join(lines) + "\n"

    print(f"""
Setup complete!

Still to do:
  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD
{session_secrets_section}
Then push and test:
  git add {CONFIG_PATH} {WORKFLOW_PATH}
  git commit -m "configure sewage alerts"
  git push -u origin main
  gh workflow run check_spills.yml
""")


if __name__ == "__main__":
    main()
