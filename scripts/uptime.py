"""Check the live system the way a visitor uses it. Run by .github/workflows/uptime.yml: a quick
check every 30 minutes, and the full one, ending with one real verdict, once a day.

It reads the deployed config.js to find the API the website really calls, wakes that API (it
scales to zero when nobody uses it), then checks each part a visitor needs. Those requests
count as activity, so they also keep the free Qdrant cluster from being suspended. With
--history, each run is added to an uptime history: the file the System page and the README's
badge read. Standard library only, so the check still runs when the project's own
dependencies are broken.

    python3 scripts/uptime.py --site https://YOUR-GITHUB-USER.github.io/tribunal-of-ages/
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

TEST_CASE = {
    "crime": "My roommate ate my leftover pizza from the fridge.",
    "outrage": 3,
    "record": False,  # the daily check stays out of the public record
}
ICONS = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
PAUSE = 20  # seconds between attempts while the API starts up from zero


@dataclass
class Reply:
    status: int  # 0 when nothing answered: DNS failure, refused connection or timeout
    body: str


@dataclass
class Check:
    name: str
    result: str  # "ok", "warn" (working, but worth a look) or "fail"
    detail: str


type Fetch = Callable[[str, dict | None], Reply]


def fetch(url: str, payload: dict | None = None) -> Reply:
    """GET `url`, or POST `payload` to it as JSON. Never raises: failures become a Reply."""
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "tribunal-uptime/1.0"}
    request = urllib.request.Request(url, data=data, headers=headers)
    try:  # a verdict can take a while: two LLM calls
        with urllib.request.urlopen(request, timeout=30 if data is None else 90) as response:
            return Reply(response.status, response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as err:
        return Reply(err.code, err.read().decode("utf-8", "replace"))
    except (OSError, ValueError) as err:  # URLError and timeouts are OSErrors
        return Reply(0, str(err))


def run(
    site: str,
    get: Fetch = fetch,
    wait: float = 240,
    sleep: Callable[[float], None] = time.sleep,
    quick: bool = False,
) -> list[Check]:
    """Every check, in the order a visitor depends on them. Stops when nothing more can work.
    A quick run leaves out the real verdict, so it spends no AI tokens."""
    site = site.rstrip("/") + "/"
    checks = [website(site, get), hall_of_fame(site, get), library(site, get)]
    api = api_address(get(site + "config.js", None).body)
    if api is None or "YOUR-API-ADDRESS" in api:
        detail = f"config.js points at {api or 'no https:// address'}: set your API's address"
        return [*checks, Check("API address", "fail", detail)]
    checks.append(wake(api, get, wait, sleep))
    if checks[-1].result == "fail":
        return checks
    parts = [ready(api, get), catalog(api, get), record(api, get), ledger(api, get)]
    return [*checks, *parts] if quick else [*checks, *parts, verdict(api, get)]


def remember(history: dict, checks: list[Check], now: datetime, days: int = 90) -> dict:
    """Add one run to an uptime history: checks and passes per day for `days` days, the latest
    incidents, and the uptime they add up to. A run is up when no check failed."""
    up = all(check.result != "fail" for check in checks)
    today, oldest = now.strftime("%Y-%m-%d"), (now - timedelta(days=days)).strftime("%Y-%m-%d")
    kept = [day for day in history.get("days", []) if day["day"] > oldest]
    if not kept or kept[-1]["day"] != today:
        kept.append({"day": today, "checks": 0, "up": 0})
    kept[-1]["checks"] += 1
    kept[-1]["up"] += int(up)
    incidents = history.get("incidents", [])
    if not up:
        failed = [check.name for check in checks if check.result == "fail"]
        incidents = [{"at": now.strftime("%Y-%m-%dT%H:%MZ"), "failed": failed}, *incidents][:20]
    return {
        "updated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "status": "up" if up else "down",
        "summary": {
            "uptime_30d": _share(kept[-30:]),
            "uptime_90d": _share(kept),
            "checks": sum(day["checks"] for day in kept),
        },
        "days": kept,
        "incidents": incidents,
    }


def _share(days: list[dict]) -> float:
    """The percentage of checks that passed, to two decimal places."""
    checks = sum(day["checks"] for day in days)
    return round(100 * sum(day["up"] for day in days) / checks, 2) if checks else 100.0


def api_address(config_js: str) -> str | None:
    """The production API in config.js: the https:// address assigned to TRIBUNAL_API."""
    match = re.search(r'TRIBUNAL_API\s*=[^;]*?"(https://[^"]+)"', config_js)
    return match.group(1).rstrip("/") if match else None


def website(site: str, get: Fetch) -> Check:
    page = get(site, None)
    if page.status == 200 and 'id="case-form"' in page.body:
        return Check("Website", "ok", f"{site} serves the case form")
    return Check("Website", "fail", f"{site} answered {page.status or 'nothing'}")


def hall_of_fame(site: str, get: Fetch) -> Check:
    reply = get(site + "hall-of-fame.json", None)
    try:
        cases = len(json.loads(reply.body)["cases"])
    except (ValueError, KeyError, TypeError):
        return Check("Hall of Fame", "fail", f"hall-of-fame.json answered {reply.status}")
    if not cases:
        return Check("Hall of Fame", "warn", "empty: run `uv run tribunal hall-of-fame`")
    return Check("Hall of Fame", "ok", f"{cases} archived verdicts for when the court can't sit")


def library(site: str, get: Fetch) -> Check:
    reply = get(site + "laws.json", None)
    try:
        laws = len(json.loads(reply.body)["laws"])
    except (ValueError, KeyError, TypeError):
        return Check("Library", "warn", "laws.json is missing: CI writes it on every deploy")
    return Check("Library", "ok", f"{laws} laws on the shelves")


def record(api: str, get: Fetch) -> Check:
    reply = get(f"{api}/api/v1/records?limit=1", None)
    if reply.status == 200:
        return Check("Public record", "ok", "the record answers")
    if reply.status == 503:
        detail = "closed: check DATABASE_URL, and Neon's monthly limits"
        return Check("Public record", "warn", detail)
    return Check("Public record", "fail", f"/api/v1/records answered {reply.status}")


def ledger(api: str, get: Fetch) -> Check:
    reply = get(f"{api}/api/v1/stats", None)
    if reply.status != 200:
        detail = f"/api/v1/stats answered {reply.status}: the System page is empty"
        return Check("Ledger", "warn", detail)
    try:
        board = json.loads(reply.body)
        detail = f"{board['ledger']['today']} of {board['per_day']} cases today"
    except (ValueError, KeyError, TypeError):
        return Check("Ledger", "fail", "/api/v1/stats answered something unreadable")
    return Check("Ledger", "ok", detail)


def wake(api: str, get: Fetch, wait: float, sleep: Callable[[float], None]) -> Check:
    """An API scaled to zero answers 503, or nothing, while it starts: keep asking a while."""
    attempts = max(1, round(wait / PAUSE))
    for attempt in range(1, attempts + 1):
        reply = get(f"{api}/healthz", None)
        if reply.status == 200:
            return Check("API", "ok", f"{api} is up (attempt {attempt})")
        if attempt < attempts:
            sleep(PAUSE)
    answer = reply.status or "no answer"
    detail = f"{api} gave {answer} for {wait:.0f} s: see the container app's logs"
    return Check("API", "fail", detail)


def ready(api: str, get: Fetch) -> Check:
    reply = get(f"{api}/readyz", None)
    laws = _json(reply).get("laws")
    if reply.status == 200 and laws:
        return Check("Search index", "ok", f"Qdrant answered with {laws} laws")
    return Check("Search index", "fail", f"/readyz gave {reply.status}: is Qdrant suspended?")


def catalog(api: str, get: Fetch) -> Check:
    reply = get(f"{api}/api/v1/catalog", None)
    themes = [str(theme.get("id")) for theme in _json(reply).get("themes", [])]
    if reply.status == 200 and themes:
        return Check("Catalog", "ok", "themes: " + ", ".join(themes))
    return Check("Catalog", "fail", f"/api/v1/catalog gave {reply.status} and no themes")


def verdict(api: str, get: Fetch) -> Check:
    """One real case, end to end: analysis, search, the judge and the cited law."""
    reply = get(f"{api}/api/v1/verdicts", TEST_CASE)
    ruling = _json(reply)
    if reply.status == 200 and ruling.get("kind") == "verdict":
        law = ruling.get("law") or {}
        return Check("Verdict", "ok", f"judged under {law.get('law_id', 'an unnamed law')}")
    if reply.status == 200:
        return Check("Verdict", "warn", f"the test case was declined: {ruling.get('message')}")
    if reply.status == 429:
        detail = "in recess: the daily budget or the AI providers' quota is spent"
        return Check("Verdict", "warn", detail)
    reasons = {
        503: "every AI provider failed: check the container app's API keys and model names",
        422: "the test case was rejected: did the case schema or the catalog change?",
    }
    return Check("Verdict", "fail", reasons.get(reply.status, f"answered {reply.status}"))


def report(checks: list[Check]) -> str:
    healthy = all(check.result != "fail" for check in checks)
    title = "Everything a visitor needs works." if healthy else "Something a visitor needs is down."
    rows = [f"| {ICONS[c.result]} {c.name} | {c.detail.replace('|', '/')} |" for c in checks]
    return "\n".join([f"**{title}**", "", "| Check | Result |", "|---|---|", *rows, ""])


def _json(reply: Reply) -> dict:
    try:
        data = json.loads(reply.body)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the live Tribunal of Ages.")
    parser.add_argument("--site", required=True, help="the website's address")
    parser.add_argument("--report", help="also write the Markdown report to this file")
    parser.add_argument("--quick", action="store_true", help="leave out the real verdict")
    parser.add_argument("--history", help="add this run to an uptime history JSON file")
    args = parser.parse_args()
    checks = run(args.site, quick=args.quick)
    if args.history:
        path = Path(args.history)
        try:
            past = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            past = {}  # a damaged history starts again rather than stopping the check
        history = remember(past, checks, datetime.now(UTC))
        path.write_text(json.dumps(history, indent=1) + "\n", encoding="utf-8")
    text = report(checks)
    print(text)
    for path in filter(None, [args.report, os.getenv("GITHUB_STEP_SUMMARY")]):
        with open(path, "a", encoding="utf-8") as file:
            file.write(text + "\n")
    sys.exit(0 if all(check.result != "fail" for check in checks) else 1)


if __name__ == "__main__":
    main()
