from __future__ import annotations

from scripts.bootstrap_production_readiness import bootstrap


def test_bootstrap_creates_readiness_artifacts(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "render.yaml").write_text("services: []\n", encoding="utf-8")

    payload = bootstrap(root)

    assert payload["status"] == "ok"
    assert payload["readiness"]["status"] in {"pass", "warn"}
    assert (root / "atena_evolution" / "production_center" / "telemetry.jsonl").exists()
    assert (root / "atena_evolution" / "production_center" / "skills_catalog.json").exists()
    assert (root / "atena_evolution" / "production_center" / "policy_audit.jsonl").exists()
    assert all(step["ok"] for step in payload["steps"])
