#!/usr/bin/env python3
"""Interactive setup script for sewage alerts."""

import re
import sys

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


def read_config(path: str = CONFIG_PATH) -> dict:
    """Read configuration from a YAML file without external dependencies."""
    config: dict = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    config[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return config


def write_config(
    postcode: str,
    radius_km: int,
    lookback_hours: int,
    notify_email: str,
    path: str = CONFIG_PATH,
) -> None:
    """Write configuration to a YAML file."""
    with open(path, "w") as f:
        f.write(f'postcode: "{postcode}"\n')
        f.write(f"radius_km: {radius_km}\n")
        f.write(f"lookback_hours: {lookback_hours}\n")
        f.write(f'notify_email: "{notify_email}"\n')


def _prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("Welcome to Sewage Alerts setup!\n")

    existing = read_config()

    postcode = _prompt("Postcode", existing.get("postcode", "GL5 1HE"))
    notify_email = _prompt("Notification email", existing.get("notify_email", ""))
    radius_km = int(_prompt("Search radius (km)", str(existing.get("radius_km", 20))))

    print("\nCheck interval:")
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

    write_config(postcode, radius_km, lookback_hours, notify_email)
    print(f"\n✓ Written {CONFIG_PATH}")

    patch_workflow_cron(cron_expr)
    print(f"✓ Updated {WORKFLOW_PATH}")

    print(f"""
Setup complete! Run these commands to finish:

  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD

Then push and test:

  git add {CONFIG_PATH} {WORKFLOW_PATH}
  git commit -m "configure sewage alerts"
  git push
  gh workflow run check_spills.yml
""")


if __name__ == "__main__":
    main()
