"""The "Explain this incident" report — Ally's plain-language incident narrative.

Covers the sanitizer (model output → a safe, capped report the UI can render) and the
persistence round-trip. A missing or malformed report must resolve to None so the caller
can always fall back to the structured result card — it can NEVER break the report view.
"""
from __future__ import annotations

import json
import types

from app.services import ai_service, mission_service


def test_sanitize_full_incident_report():
    r = ai_service.sanitize_incident_report({
        "headline": "A hacked plugin let an attacker take over the server.",
        "severity": "critical",
        "how_they_got_in": "An outdated file-upload plugin allowed a stranger to upload a hidden file.",
        "timeline": [
            {"when": "19 May 2026", "what": "First webshell uploaded."},
            {"when": "21 May 2026", "what": "Attacker became root and installed a backdoor."},
        ],
        "impact": "Full server takeover for about two months.",
        "done": ["Removed the backdoor", "Blocked the C2 address"],
        "left": ["Rotate all passwords", "Rebuild the site"],
        "caveat": "A root-compromised box can never be fully trusted.",
    })
    assert r["headline"].startswith("A hacked plugin")
    assert r["severity"] == "critical"
    assert len(r["timeline"]) == 2
    assert r["timeline"][0] == {"when": "19 May 2026", "what": "First webshell uploaded."}
    assert r["done"] == ["Removed the backdoor", "Blocked the C2 address"]
    assert r["left"] == ["Rotate all passwords", "Rebuild the site"]
    assert r["caveat"].startswith("A root-compromised")


def test_sanitize_headline_only_is_valid():
    r = ai_service.sanitize_incident_report({"headline": "Something happened."})
    assert r["headline"] == "Something happened."
    assert r["severity"] == "" and r["timeline"] == [] and r["done"] == []


def test_sanitize_drops_junk_and_empties():
    assert ai_service.sanitize_incident_report("not a dict") is None
    assert ai_service.sanitize_incident_report(None) is None
    assert ai_service.sanitize_incident_report([1, 2]) is None
    # nothing substantive → None (caller falls back to the result card). A caveat alone is
    # not a report — the substantive fields (headline/how/timeline/impact/done/left) are empty.
    assert ai_service.sanitize_incident_report({"caveat": "just a note"}) is None
    assert ai_service.sanitize_incident_report(
        {"headline": "", "how_they_got_in": "", "timeline": [], "impact": "",
         "done": [], "left": []}
    ) is None


def test_sanitize_invalid_severity_dropped():
    assert ai_service.sanitize_incident_report({"headline": "h", "severity": "apocalyptic"})["severity"] == ""
    assert ai_service.sanitize_incident_report({"headline": "h", "severity": "HIGH"})["severity"] == "high"
    assert ai_service.sanitize_incident_report({"headline": "h", "severity": 5})["severity"] == ""


def test_sanitize_timeline_shape_and_bad_entries():
    r = ai_service.sanitize_incident_report({
        "headline": "h",
        "timeline": [
            {"when": "day 1", "what": "start"},
            "not a dict",                      # dropped
            {"when": "", "what": ""},          # both blank → dropped
            {"what": "no when is fine"},       # partial ok
            123,                                # dropped
        ],
    })
    assert r["timeline"] == [
        {"when": "day 1", "what": "start"},
        {"when": "", "what": "no when is fine"},
    ]


def test_sanitize_caps_lengths():
    r = ai_service.sanitize_incident_report({
        "headline": "x" * 500,
        "how_they_got_in": "y" * 2000,
        "impact": "z" * 2000,
        "done": [f"item {i} " + "a" * 400 for i in range(20)],
        "timeline": [{"when": "w" * 200, "what": "q" * 400} for _ in range(40)],
    })
    assert len(r["headline"]) <= ai_service._INCIDENT_HEADLINE_MAX
    assert len(r["how_they_got_in"]) <= ai_service._INCIDENT_TEXT_MAX
    assert len(r["impact"]) <= ai_service._INCIDENT_TEXT_MAX
    assert len(r["done"]) <= ai_service._INCIDENT_LIST_MAX
    assert all(len(i) <= ai_service._INCIDENT_ITEM_MAX for i in r["done"])
    assert len(r["timeline"]) <= ai_service._INCIDENT_TL_MAX
    assert all(len(e["when"]) <= ai_service._INCIDENT_WHEN_MAX for e in r["timeline"])
    assert all(len(e["what"]) <= ai_service._INCIDENT_ITEM_MAX for e in r["timeline"])


def test_sanitize_server_report_adds_breakdown():
    r = ai_service.sanitize_server_report({
        "headline": "Two of your sites were hacked and cleaned.",
        "severity": "high",
        "breakdown": [
            {"title": "desktopit.net", "outcome": "Backdoor + 22 webshells removed"},
            {"title": "richhome.com.bd", "outcome": "Cleaned; rebuild recommended"},
            "not a dict",                              # dropped
            {"title": "", "outcome": ""},              # both blank → dropped
        ],
    })
    assert r["headline"].startswith("Two of your sites")
    assert r["severity"] == "high"
    assert r["breakdown"] == [
        {"title": "desktopit.net", "outcome": "Backdoor + 22 webshells removed"},
        {"title": "richhome.com.bd", "outcome": "Cleaned; rebuild recommended"},
    ]


def test_sanitize_server_report_breakdown_only_is_valid():
    # A report with no narrative but a real per-site breakdown is still usable.
    r = ai_service.sanitize_server_report({"breakdown": [{"title": "site.com", "outcome": "clean"}]})
    assert r is not None and r["breakdown"] == [{"title": "site.com", "outcome": "clean"}]
    assert r["headline"] == "" and r["timeline"] == []


def test_sanitize_server_report_empty_and_junk():
    assert ai_service.sanitize_server_report("nope") is None
    assert ai_service.sanitize_server_report({}) is None
    assert ai_service.sanitize_server_report({"breakdown": []}) is None
    assert ai_service.sanitize_server_report({"breakdown": ["x", 1]}) is None  # no dict entries


def test_sanitize_server_report_caps_breakdown():
    r = ai_service.sanitize_server_report({
        "headline": "h",
        "breakdown": [{"title": "t" * 200, "outcome": "o" * 500} for _ in range(80)],
    })
    assert len(r["breakdown"]) <= ai_service._SR_BREAKDOWN_MAX
    assert all(len(e["title"]) <= ai_service._SR_TITLE_MAX for e in r["breakdown"])
    assert all(len(e["outcome"]) <= ai_service._INCIDENT_ITEM_MAX for e in r["breakdown"])


def test_incident_report_of_round_trip_and_corruption():
    payload = {"headline": "done", "severity": "high", "timeline": [{"when": "t", "what": "w"}],
               "how_they_got_in": "x", "impact": "y", "done": ["a"], "left": ["b"], "caveat": ""}
    good = types.SimpleNamespace(incident_report=json.dumps(payload))
    assert mission_service.incident_report_of(good) == payload
    assert mission_service.incident_report_of(types.SimpleNamespace(incident_report=None)) is None
    assert mission_service.incident_report_of(types.SimpleNamespace(incident_report="{bad json")) is None
    assert mission_service.incident_report_of(types.SimpleNamespace(incident_report="[1,2]")) is None
