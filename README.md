# Sewage Alerts

Emails you when sewage overflow events start near your home. Runs automatically on a schedule using GitHub Actions.

> **Geographic note:** This tool uses Severn Trent Water's dataset and only covers their service area (broadly the Midlands and parts of the East of England). If your postcode is outside this area, the script will run without error but will never find events.

## Prerequisites

- Python 3.9 or later installed on your computer
- A Gmail account

## Setup

### 1. Create a GitHub account

Sign up at [github.com/signup](https://github.com/signup) if you don't have one.

### 2. Install the GitHub CLI

Follow the instructions at [cli.github.com](https://cli.github.com) for your operating system.

### 3. Log in to GitHub

```bash
gh auth login
```

Follow the prompts. Choose "GitHub.com" and "HTTPS" when asked.

### 4. Fork and clone this repository

```bash
gh repo fork <REPO_URL> --clone && cd sewage-alerts
```

### 5. Enable GitHub Actions on your fork

Go to your forked repository on github.com → click the **Actions** tab → click **"I understand my workflows, go ahead and enable them"**.

### 6. Create a Gmail App Password

You'll need this in the next step. App Passwords require 2-Step Verification to be enabled on your Google account first.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security) and enable **2-Step Verification** if it isn't already on
2. Then go directly to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Name it "Sewage Alerts" and click **Create**
4. Copy the 16-character password shown — you'll need it shortly

> **Note:** If you don't see the App passwords page, your Google account may be managed by an organisation (e.g. a work or school account) that disables this feature. You'll need to use a personal Gmail account instead.

### 7. Run the setup script

```bash
python configure.py
```

Follow the prompts to enter your postcode, email address, and preferred check interval.

### 8. Run the commands printed by the setup script

The script will print something like:

```
  gh secret set GMAIL_ADDRESS
  gh secret set GMAIL_APP_PASSWORD

  git add config.yml .github/workflows/check_spills.yml
  git commit -m "configure sewage alerts"
  git push
  gh workflow run check_spills.yml
```

Copy and run each command. When prompted by `gh secret set`, paste the value (your Gmail address or App Password).

The last command triggers an immediate test run. You can watch it at:
`https://github.com/<your-username>/sewage-alerts/actions`

If spills are found near you, you'll receive an email. If not, the workflow will complete silently — that's normal.

## Configuration

Edit `config.yml` to change settings:

```yaml
postcode: "GL5 1HE"     # Your home postcode
radius_km: 20            # Search radius in kilometres
lookback_hours: 24       # How far back to look for new spills
notify_email: "you@gmail.com"  # Where to send alerts
```

After editing, commit and push:

```bash
git add config.yml
git commit -m "update config"
git push
```

To change the schedule, run `python configure.py` again.

## How it works

1. The workflow runs on your configured schedule
2. It looks up your postcode's coordinates via [postcodes.io](https://postcodes.io)
3. It queries Severn Trent Water's live overflow data for events that **started** within `lookback_hours` and within `radius_km` of your home
4. If any are found, it sends you an HTML email with a table of nearby spills
5. If none are found, it exits silently — no email is sent
