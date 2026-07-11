"""Track B Phase 2 — Ally-emitted Workspace artifacts (`ai_service.split_artifacts`).

The contract: Ally MAY append ```ally-artifact fenced-JSON blocks (a table or chart) to a
reply; the backend splits them out so the chat text stays clean and the panels render in the
Workspace. Robustness is the whole point — a malformed/unknown block must NEVER break the
reply, it is simply dropped and the text is preserved.
"""
from app.services import ai_service


def test_no_artifact_returns_text_unchanged():
    text = "Everything looks clean — I scanned all 22 files, found nothing."
    clean, arts = ai_service.split_artifacts(text)
    assert clean == text
    assert arts == []


def test_table_extracted_and_stripped_from_text():
    text = (
        "Found 2 infected sites — the full list is in the workspace.\n\n"
        "```ally-artifact\n"
        '{"type":"table","title":"Infected","columns":["Site","Risk"],'
        '"rows":[["a.com","high"],["b.com","low"]]}\n'
        "```"
    )
    clean, arts = ai_service.split_artifacts(text)
    assert "ally-artifact" not in clean
    assert clean.startswith("Found 2 infected sites")
    assert len(arts) == 1
    a = arts[0]
    assert a["type"] == "table"
    assert a["title"] == "Infected"
    assert a["columns"] == ["Site", "Risk"]
    assert a["rows"] == [["a.com", "high"], ["b.com", "low"]]


def test_chart_values_coerced_to_float():
    text = (
        "Breakdown in the workspace →\n"
        "```ally-artifact\n"
        '{"type":"chart","chartType":"pie","title":"By risk",'
        '"data":[{"label":"high","value":2},{"label":"low","value":"1"}]}\n'
        "```"
    )
    clean, arts = ai_service.split_artifacts(text)
    assert arts[0]["chartType"] == "pie"
    assert arts[0]["data"] == [{"label": "high", "value": 2.0}, {"label": "low", "value": 1.0}]


def test_malformed_block_is_dropped_but_text_survives():
    text = "Here is the result.\n```ally-artifact\n{not valid json]\n```"
    clean, arts = ai_service.split_artifacts(text)
    assert arts == []
    assert clean == "Here is the result."


def test_unknown_type_dropped():
    text = '```ally-artifact\n{"type":"video","src":"x"}\n```'
    clean, arts = ai_service.split_artifacts(text)
    assert arts == []


def test_bad_chart_type_dropped():
    text = '```ally-artifact\n{"type":"chart","chartType":"3d","data":[{"label":"a","value":1}]}\n```'
    _clean, arts = ai_service.split_artifacts(text)
    assert arts == []


def test_at_most_four_artifacts():
    blocks = "\n".join(
        '```ally-artifact\n{"type":"chart","chartType":"bar","data":[{"label":"a","value":1}]}\n```'
        for _ in range(7)
    )
    _clean, arts = ai_service.split_artifacts("many\n" + blocks)
    assert len(arts) == 4
