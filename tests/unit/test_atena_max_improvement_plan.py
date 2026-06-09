from datetime import datetime, timezone

from core.atena_max_improvement_plan import build_report, render_markdown


def test_max_improvement_report_contains_prioritized_creation_plan() -> None:
    report = build_report(now=datetime(2026, 6, 9, tzinfo=timezone.utc))

    assert report["summary"]["highest_leverage_creation"].startswith("Atena Max")
    assert report["snapshot"]["counts"]["core_py"] >= 1
    assert any(item["priority"] == "P0" for item in report["recommendations"])
    assert any(
        "contrato" in item["create"] and "comandos" in item["create"]
        for item in report["recommendations"]
    )


def test_max_improvement_markdown_mentions_creation_artifacts() -> None:
    report = build_report(now=datetime(2026, 6, 9, tzinfo=timezone.utc))
    markdown = render_markdown(report)

    assert "Análise Completa da ATENA" in markdown
    assert "O que recomendo criar" in markdown
    assert "core/atena_max_improvement_plan.py" in markdown
