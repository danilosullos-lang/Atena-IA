from datetime import datetime, timezone

from core.atena_aegis_mythos_challenger import AegisMythosChallenger, _render_markdown


def test_aegis_mythos_plan_declares_capability_boundaries() -> None:
    generated_at = datetime(2026, 6, 8, 22, 0, tzinfo=timezone.utc)
    payload = AegisMythosChallenger(generated_at=generated_at).build_plan(
        "avaliar automação segura"
    )

    assert payload["status"] == "ok"
    assert payload["schema_version"] == "1.1"
    assert payload["objective"] == "avaliar automação segura"
    assert "não é infalível" in payload["capability_boundary"]
    assert payload["benchmark"]["release_decision"] == "ship-with-monitoring"
    assert len(payload["control_planes"]) == 3


def test_aegis_mythos_markdown_includes_operational_boundary() -> None:
    payload = AegisMythosChallenger().build_plan("teste")
    markdown = _render_markdown(payload)

    assert "## Limite operacional" in markdown
    assert "ATENA pode automatizar pesquisa" in markdown
    assert "## Benchmark interno" in markdown
