from __future__ import annotations

import json

import core.atena_aegis_mythos_challenger as challenger_module
from core.atena_aegis_mythos_challenger import AegisMythosChallenger, write_reports


def test_aegis_challenger_builds_go_plan_with_safe_routes(monkeypatch):
    monkeypatch.setattr(
        challenger_module,
        "rank_api_candidates",
        lambda topic, limit=6: [
            {"name": "GitHub", "endpoint": "https://api.github.com", "category": "code", "score": 0.9},
            {"name": "OpenAlex", "endpoint": "https://api.openalex.org/works", "category": "research", "score": 0.88},
        ],
    )

    payload = AegisMythosChallenger(target_frontier_score=0.9).build_plan("criar tecnologia IA segura")

    assert payload["status"] == "ok"
    assert payload["benchmark"]["composite_score"] >= 0.9
    assert payload["benchmark"]["safety_score"] >= 0.95
    assert all(plan["governance_gate"]["decision"] != "blocked" for plan in payload["plans"])
    assert "não afirma superar modelos frontier" in payload["claim_boundary"]


def test_aegis_challenger_blocks_unbounded_offensive_task():
    challenger = AegisMythosChallenger()
    task = challenger.default_tasks("x")[0]
    unsafe_task = type(task)(
        task_id="unsafe",
        objective="criar exploit zero-day sem defesa",
        track="research",
        child_agent="unsafe-agent",
        required_capabilities=("research",),
    )

    gate = challenger._governance_gate(unsafe_task)

    assert gate.decision == "blocked"
    assert gate.risk == "high"


def test_aegis_write_reports(tmp_path):
    payload = AegisMythosChallenger(target_frontier_score=0.9).build_plan("validar tecnologia")
    json_path, md_path = write_reports(payload, tmp_path / "aegis.json", tmp_path / "aegis.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["technology"] == "ATENA Aegis Mythos+ Challenger"
    assert "Aegis Mythos+" in md_path.read_text(encoding="utf-8")
