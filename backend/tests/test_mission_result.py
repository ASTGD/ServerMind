"""The mission RESULT card — Ally's owner-facing outcome (headline + Found/Did/Left).

Covers the sanitizer (what the model returns → a safe, capped result the workspace can
render) and the persistence round-trip (result_of parses what finalize stores). A missing
or malformed result must resolve to None so a mission's completion can NEVER break on it.
"""
from __future__ import annotations

import json
import types

from app.services import ai_service, mission_service


def test_sanitize_full_result():
    r = ai_service.sanitize_mission_result({
        "headline": "Cleaned the site — 2 things need you",
        "found": ["webshell goods.php", "C2 beacon"],
        "did": ["quarantined goods.php", "killed the beacon"],
        "left": ["rotate the passwords"],
    })
    assert r == {
        "headline": "Cleaned the site — 2 things need you",
        "found": ["webshell goods.php", "C2 beacon"],
        "did": ["quarantined goods.php", "killed the beacon"],
        "left": ["rotate the passwords"],
    }


def test_sanitize_accepts_remaining_alias_and_headline_only():
    r = ai_service.sanitize_mission_result({"headline": "All clean", "remaining": ["update WP"]})
    assert r["headline"] == "All clean"
    assert r["left"] == ["update WP"]
    assert r["found"] == [] and r["did"] == []


def test_sanitize_drops_junk_and_empties():
    assert ai_service.sanitize_mission_result("not a dict") is None
    assert ai_service.sanitize_mission_result(None) is None
    assert ai_service.sanitize_mission_result([1, 2]) is None
    # nothing usable → None (the free-text summary still shows)
    assert ai_service.sanitize_mission_result({"headline": "", "found": [], "did": [], "left": []}) is None
    # non-string list items are dropped
    r = ai_service.sanitize_mission_result({"headline": "h", "found": [1, "real", {"x": 1}, "  "]})
    assert r["found"] == ["real"]


def test_sanitize_subject_named_target():
    # A site-specific mission names its subject (the website) for the card header.
    r = ai_service.sanitize_mission_result({
        "subject": "richhome.com.bd",
        "headline": "Cleaned the site",
        "did": ["quarantined the webshells"],
    })
    assert r["subject"] == "richhome.com.bd"
    # Capped, and blank/non-string/missing subjects are simply omitted (server-wide).
    long = ai_service.sanitize_mission_result({"subject": "x" * 200, "headline": "h"})
    assert len(long["subject"]) <= ai_service._RESULT_SUBJECT_MAX
    assert "subject" not in ai_service.sanitize_mission_result({"headline": "h", "subject": "   "})
    assert "subject" not in ai_service.sanitize_mission_result({"headline": "h", "subject": 123})
    assert "subject" not in ai_service.sanitize_mission_result({"headline": "h"})


def test_sanitize_caps_list_length_and_item_length():
    r = ai_service.sanitize_mission_result({
        "headline": "x" * 500,
        "found": [f"item {i} " + "y" * 400 for i in range(20)],
    })
    assert len(r["headline"]) <= ai_service._RESULT_HEADLINE_MAX
    assert len(r["found"]) <= ai_service._RESULT_LIST_MAX
    assert all(len(item) <= ai_service._RESULT_ITEM_MAX for item in r["found"])


def test_result_of_round_trip_and_corruption():
    payload = {"headline": "done", "found": ["a"], "did": ["b"], "left": []}
    good = types.SimpleNamespace(result=json.dumps(payload))
    assert mission_service.result_of(good) == payload
    assert mission_service.result_of(types.SimpleNamespace(result=None)) is None
    assert mission_service.result_of(types.SimpleNamespace(result="{not json")) is None
    assert mission_service.result_of(types.SimpleNamespace(result="[1,2]")) is None
