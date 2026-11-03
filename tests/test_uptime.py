import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# scripts/ isn't a package, so load the script by its path.
SCRIPT = Path(__file__).parents[1] / "scripts" / "uptime.py"
spec = importlib.util.spec_from_file_location("uptime", SCRIPT)
assert spec and spec.loader
uptime = importlib.util.module_from_spec(spec)
sys.modules["uptime"] = uptime
spec.loader.exec_module(uptime)

SITE = "https://you.github.io/tribunal-of-ages/"
API = "https://tribunal-api.calmsea-1a2b3c4d.eastus.azurecontainerapps.io"
CONFIG = f"""window.TRIBUNAL_API = ["localhost"].includes(location.hostname)
  ? "http://localhost:8000"
  : "{API}";
window.TRIBUNAL_ANALYTICS = {{ key: "", host: "https://us.i.posthog.com" }};
"""
VERDICT = {"kind": "verdict", "law": {"law_id": "hammurabi-8"}}


def web(**overrides):
    """A fake internet: each URL gives its replies in turn, then repeats the last one."""
    routes = {
        SITE: [(200, '<form id="case-form">')],
        SITE + "config.js": [(200, CONFIG)],
        SITE + "hall-of-fame.json": [(200, json.dumps({"cases": [{}, {}]}))],
        SITE + "laws.json": [(200, json.dumps({"laws": [{}, {}, {}]}))],
        API + "/healthz": [(200, "{}")],
        API + "/readyz": [(200, json.dumps({"ok": True, "laws": 351}))],
        API + "/api/v1/catalog": [(200, json.dumps({"themes": [{"id": "ancient"}]}))],
        API + "/api/v1/records?limit=1": [(200, "[]")],
        API + "/api/v1/stats": [(200, json.dumps({"ledger": {"today": 4}, "per_day": 150}))],
        API + "/api/v1/verdicts": [(200, json.dumps(VERDICT))],
    }
    routes.update({API + path: replies for path, replies in overrides.items()})
    asked = []

    def get(url, payload=None):
        asked.append(url)
        replies = routes[url]
        status, body = replies.pop(0) if len(replies) > 1 else replies[0]
        return uptime.Reply(status, body)

    return get, asked


def results(checks):
    return {check.name: check.result for check in checks}


def test_reads_the_api_address_from_config_js():
    assert uptime.api_address(CONFIG) == API


def test_a_healthy_system_passes_every_check():
    get, _ = web()
    checks = uptime.run(SITE, get, sleep=lambda seconds: None)
    assert set(results(checks).values()) == {"ok"}
    assert "Everything a visitor needs works." in uptime.report(checks)


def test_waits_for_a_sleeping_space():
    naps = []
    get, _ = web(**{"/healthz": [(503, "starting"), (0, "timed out"), (200, "{}")]})
    checks = uptime.run(SITE, get, sleep=naps.append)
    assert results(checks)["API"] == "ok"
    assert len(naps) == 2


def test_a_space_that_never_wakes_fails_without_more_calls():
    get, asked = web(**{"/healthz": [(503, "starting")]})
    checks = uptime.run(SITE, get, wait=60, sleep=lambda seconds: None)
    assert results(checks)["API"] == "fail"
    assert API + "/api/v1/verdicts" not in asked


def test_the_placeholder_address_fails_fast():
    get, asked = web()
    placeholder = CONFIG.replace(API, "https://YOUR-API-ADDRESS")
    routes_get = get

    def get_with_placeholder(url, payload=None):
        if url == SITE + "config.js":
            return uptime.Reply(200, placeholder)
        return routes_get(url, payload)

    checks = uptime.run(SITE, get_with_placeholder, sleep=lambda seconds: None)
    assert results(checks)["API address"] == "fail"
    assert not any(url.startswith(API) for url in asked)


def test_a_spent_budget_is_a_warning_not_an_outage():
    get, _ = web(**{"/api/v1/verdicts": [(429, '{"detail": "recess"}')]})
    checks = uptime.run(SITE, get, sleep=lambda seconds: None)
    assert results(checks)["Verdict"] == "warn"
    assert "Everything a visitor needs works." in uptime.report(checks)


def test_failing_ai_providers_are_an_outage():
    get, _ = web(**{"/api/v1/verdicts": [(503, '{"detail": "scribes"}')]})
    checks = uptime.run(SITE, get, sleep=lambda seconds: None)
    assert results(checks)["Verdict"] == "fail"
    assert "Something a visitor needs is down." in uptime.report(checks)


def test_a_quick_check_spends_no_tokens():
    get, asked = web()
    checks = uptime.run(SITE, get, sleep=lambda seconds: None, quick=True)
    assert all(check.result == "ok" for check in checks)
    assert API + "/api/v1/verdicts" not in asked  # no real verdict, so no AI call


def test_the_history_counts_each_day_keeps_90_and_lists_incidents():
    ok = [uptime.Check("Website", "ok", "")]
    down = [uptime.Check("Website", "ok", ""), uptime.Check("API ready", "fail", "503")]
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    history: dict = {}
    for day in range(100):  # one passing check a day for 100 days
        history = uptime.remember(history, ok, start + timedelta(days=day))
    history = uptime.remember(history, down, start + timedelta(days=99, hours=1))
    assert len(history["days"]) == 90 and history["days"][-1] == {
        "day": "2026-04-10",
        "checks": 2,
        "up": 1,
    }
    assert history["status"] == "down"
    assert history["incidents"][0]["failed"] == ["API ready"]
    assert history["summary"]["uptime_90d"] == round(100 * 90 / 91, 2)
