"""Daily self-health-check for SV TeamIntel.

Runs from .github/workflows/health-check.yml (daily cron + manual dispatch).
Posts to #sv-automation via scripts/sv_automation_notify.py ONLY when it finds
something to fix — silent when healthy.

The app is cycle-aware: between draft cycles the build pipeline is shuttered
on purpose (ACTIVE=false in update-dashboard.yml — see CLAUDE.md
"Draft-cycle activation"). While shuttered, "no recent builds" is the expected
state and is NOT a finding; the check still watches the things that stay live
year-round (dashboard page, Vercel overrides API, Redis, Slack token).

Checks:
  1. Dashboard page responding (https://sv-teamintel.vercel.app/)
  2. Overrides API end-to-end (Vercel function -> Upstash Redis)
  3. Redis reachable directly from CI (REDIS_URL secret still valid)
  4. Slack bot token still valid (auth.test) — needed to fetch intel messages
  5. Cadence-gate vs workflow-state mismatch (ACTIVE=true but the workflow
     is disabled in GitHub, so no builds would actually run)
  6. Build freshness — ONLY when ACTIVE=true: a successful
     "Update TeamIntel Dashboard" run in the last 26 hours

Env:
  SLACK_BOT_TOKEN, REDIS_URL           — repo secrets (already set)
  SV_AUTOMATION_WEBHOOK_URL            — repo secret (webhook for #sv-automation)
  GITHUB_TOKEN, GITHUB_REPOSITORY      — provided by Actions
  HEALTH_CHECK_TEST=true               — send a clearly-labeled test post instead
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sv_automation_notify import Finding, post_findings  # noqa: E402

DASHBOARD_URL = "https://sv-teamintel.vercel.app"
BUILD_WORKFLOW_FILE = "update-dashboard.yml"
FRESHNESS_HOURS = 26  # post-draft active cadence is hourly-daytime; 26h spans the overnight quiet window

REPO = os.environ.get("GITHUB_REPOSITORY", "Stadium-Ventures/sv-team-intel")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _http_get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _gh_api(path):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, body = _http_get(f"https://api.github.com{path}", headers=headers)
    return json.loads(body)


def build_cadence_is_active():
    """Read the ACTIVE master switch out of the build workflow's cadence gate."""
    path = os.path.join(REPO_ROOT, ".github", "workflows", BUILD_WORKFLOW_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r"^\s*ACTIVE=(\S+)", f.read(), re.MULTILINE)
        return m is not None and m.group(1).strip().strip('"') == "true"
    except OSError:
        return False


def check_dashboard(findings):
    try:
        status, _ = _http_get(f"{DASHBOARD_URL}/")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
    except Exception as e:
        findings.append(Finding(
            "TeamIntel dashboard is down",
            "The TeamIntel dashboard page isn't loading, so nobody can view the team-interest matrix.",
            f"{DASHBOARD_URL}/ did not respond normally just now ({e}).",
            "Check the sv-teamintel project on Vercel (stadium-ventures team) and redeploy if needed.",
            fix_type="code",
        ))


def check_overrides_api(findings):
    try:
        status, body = _http_get(f"{DASHBOARD_URL}/api/overrides")
        if status != 200:
            raise RuntimeError(f"HTTP {status}")
        data = json.loads(body)
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(data["error"])
    except Exception as e:
        findings.append(Finding(
            "Dashboard edits can't save or load",
            "The dashboard's saved edits (scores, PDW flags, manual entries) can't be read or written.",
            f"{DASHBOARD_URL}/api/overrides returned an error just now ({e}).",
            "Check that the REDIS_URL env var is still set on the sv-teamintel Vercel project and that the Upstash database is up.",
            fix_type="manual",
        ))


def check_redis(findings):
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        findings.append(Finding(
            "Redis connection string is missing",
            "The build can no longer merge in dashboard edits — the Redis secret is gone.",
            "The REDIS_URL secret was empty when the daily health check ran.",
            "Re-set the REDIS_URL secret on this repo (value lives in the Upstash / Vercel storage settings).",
            fix_type="manual",
        ))
        return
    try:
        import redis  # installed by the workflow
        r = redis.from_url(url, socket_connect_timeout=10, socket_timeout=10)
        r.ping()
        r.exists("score_overrides")
    except Exception as e:
        findings.append(Finding(
            "Redis (saved dashboard edits) is unreachable",
            "The database that stores dashboard edits isn't answering, so builds would lose manual edits.",
            f"A direct connection from the health check failed just now ({type(e).__name__}).",
            "Check the Upstash database tied to the sv-teamintel Vercel project; rotate the REDIS_URL secret if the credentials changed.",
            fix_type="manual",
        ))


def check_slack_token(findings):
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    problem = None
    if not token:
        problem = "The SLACK_BOT_TOKEN secret was empty when the daily health check ran."
    else:
        try:
            status, body = _http_get(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = json.loads(body)
            if not data.get("ok"):
                problem = f"Slack rejected the token just now ({data.get('error', 'unknown error')})."
        except Exception as e:
            print(f"WARN: Slack auth.test unreachable ({e}) — not treating as a finding.")
            return
    if problem:
        findings.append(Finding(
            "Slack access for intel fetching is broken",
            "The app can no longer read TeamIntel messages from Slack, so rebuilds would produce an empty/stale dashboard.",
            problem,
            "Reinstall or re-issue the Slack bot token and update the SLACK_BOT_TOKEN secret on this repo. Needed before the next draft cycle even while builds are shuttered.",
            fix_type="manual",
        ))


def check_build_pipeline(findings, active):
    try:
        wf = _gh_api(f"/repos/{REPO}/actions/workflows/{BUILD_WORKFLOW_FILE}")
        wf_enabled = wf.get("state") == "active"
    except Exception as e:
        print(f"WARN: could not read workflow state ({e}) — skipping pipeline checks.")
        return

    if active and not wf_enabled:
        findings.append(Finding(
            "Dashboard builds are switched on but not actually running",
            "The build cadence is set to live (ACTIVE=true) but the GitHub workflow itself is disabled, so no scheduled builds happen.",
            "GitHub reports the 'Update TeamIntel Dashboard' workflow is disabled while the cadence gate says active.",
            "Re-enable the workflow: gh workflow enable update-dashboard.yml -R " + REPO,
            fix_type="manual",
        ))
        return

    if not active:
        return  # shuttered between draft cycles — no builds is the expected state

    try:
        runs = _gh_api(
            f"/repos/{REPO}/actions/workflows/{BUILD_WORKFLOW_FILE}/runs"
            "?status=success&per_page=1"
        ).get("workflow_runs", [])
        if runs:
            last = datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - last
            if age <= timedelta(hours=FRESHNESS_HOURS):
                return
            how = f"The last successful build was {age.days}d {age.seconds // 3600}h ago."
        else:
            how = "GitHub shows no successful builds at all."
        findings.append(Finding(
            "Dashboard has stopped updating",
            "The TeamIntel dashboard isn't rebuilding, so new Slack intel isn't showing up.",
            how + " While live it should rebuild at least hourly during the day.",
            "Open the failed runs at https://github.com/" + REPO + "/actions and fix the first error; a manual 'gh workflow run update-dashboard.yml' is a quick retry.",
            fix_type="code",
        ))
    except Exception as e:
        print(f"WARN: could not read run history ({e}) — skipping freshness check.")


def main():
    test = os.environ.get("HEALTH_CHECK_TEST", "").strip().lower() in ("1", "true", "yes")
    if test:
        post_findings([], test=True)
        print("Test post delivered to #sv-automation.")
        return

    active = build_cadence_is_active()
    print(f"Build cadence ACTIVE={active} (shuttered between draft cycles is normal).")

    findings = []
    check_dashboard(findings)
    check_overrides_api(findings)
    check_redis(findings)
    check_slack_token(findings)
    check_build_pipeline(findings, active)

    if not findings:
        print("Healthy — staying silent.")
        return

    print(f"{len(findings)} finding(s):")
    for f in findings:
        print("---\n" + f.render())

    try:
        post_findings(findings)
        print("Posted to #sv-automation.")
    except RuntimeError as e:
        # No webhook (or delivery failed): fail the run so the problem is
        # visible in the Actions tab instead of disappearing.
        print(f"::error::{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
