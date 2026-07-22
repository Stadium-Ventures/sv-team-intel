"""Shared #sv-automation post helper for SV TeamIntel.

EVERY message this repo sends to the #sv-automation ops channel goes through
post_findings() so the product label and message contract live in exactly one
place. Do not build a second webhook path.

Message contract (see CLAUDE.md "#sv-automation scope + message contract"):
  1. Lead with the product label: "SV TeamIntel (sv-team-intel) — ...".
  2. Tag each finding as a fix type: "🛠️ Code change" or "👤 Manual".
  3. Each finding reads as three plain-English lines:
     What broke / How we know / What to do.
  4. Silent when healthy — never post an "all good" message.

The webhook URL comes from the SV_AUTOMATION_WEBHOOK_URL env var (GitHub
Actions secret). Never hardcode or commit the URL. If you need the value,
ask Tom Trudeau (ttrudeau@stadium-ventures.com).
"""

import json
import os
import urllib.request

APP_LABEL = "SV TeamIntel (sv-team-intel)"

WEBHOOK_ENV = "SV_AUTOMATION_WEBHOOK_URL"


class Finding:
    """One actionable problem. fix_type is 'code' or 'manual'."""

    def __init__(self, title, what_broke, how_we_know, what_to_do, fix_type="code"):
        self.title = title
        self.what_broke = what_broke
        self.how_we_know = how_we_know
        self.what_to_do = what_to_do
        self.fix_type = fix_type

    def render(self):
        tag = "🛠️ Code change" if self.fix_type == "code" else "👤 Manual"
        return (
            f"{tag} — {self.title}\n"
            f"• What broke: {self.what_broke}\n"
            f"• How we know: {self.how_we_know}\n"
            f"• What to do: {self.what_to_do}"
        )


def post_findings(findings, test=False):
    """Post findings to #sv-automation. Returns True if a post was delivered.

    - Empty findings + not a test → no post at all (silent when healthy).
    - Missing webhook env var → raises RuntimeError so the caller can decide
      how loudly to fail (the health check exits non-zero so the Actions run
      itself goes red instead of the problem vanishing).
    """
    if not findings and not test:
        return False

    if test:
        body = (
            f"{APP_LABEL} — 🧪 TEST POST (please ignore)\n"
            "This is a manually-triggered test of the health-check alert path. "
            "No action needed."
        )
    else:
        n = len(findings)
        header = f"{APP_LABEL} — daily health check found {n} issue{'s' if n != 1 else ''}"
        body = header + "\n\n" + "\n\n".join(f.render() for f in findings)

    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise RuntimeError(
            f"{WEBHOOK_ENV} is not set — cannot deliver this message:\n\n{body}"
        )

    req = urllib.request.Request(
        url,
        data=json.dumps({"text": body}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Webhook returned HTTP {resp.status}")
    return True
