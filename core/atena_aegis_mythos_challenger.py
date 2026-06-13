#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ATENA Aegis Mythos+ challenger.

This module is intentionally self-contained so the terminal assistant and the
launcher can import the Aegis command even when optional research integrations
are unavailable. It generates an auditable defensive-operations blueprint and
stores both JSON and Markdown reports.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "analysis_reports" / "aegis_mythos"
SCHEMA_VERSION = "1.1"


@dataclass(frozen=True)
class ControlPlane:
    """One defensive capability in the Aegis Mythos+ plan."""

    name: str
    purpose: str
    safeguards: list[str]
    acceptance_tests: list[str]


class AegisMythosChallenger:
    """Build deterministic Aegis Mythos+ plans for safe defensive automation."""

    def __init__(self, generated_at: datetime | None = None) -> None:
        self.generated_at = generated_at or datetime.now(timezone.utc)

    def build_plan(self, objective: str) -> dict[str, Any]:
        """Return a complete, auditable plan for the requested objective."""
        objective = (
            objective.strip() or "superar Mythos com segurança operacional auditável"
        )
        controls = [
            ControlPlane(
                name="Policy Sentinel",
                purpose="Classificar pedidos por risco antes de qualquer ação operacional.",
                safeguards=[
                    "bloqueio padrão para ações destrutivas",
                    "revisão humana para risco alto",
                    "registro de decisão com justificativa",
                ],
                acceptance_tests=[
                    "nega comando de exfiltração",
                    "exige confirmação para automação de dispositivo",
                    "anexa motivo de bloqueio ao relatório",
                ],
            ),
            ControlPlane(
                name="Evidence Ledger",
                purpose="Manter cadeia de custódia dos fatos, comandos e artefatos gerados.",
                safeguards=[
                    "hash de entradas e saídas críticas",
                    "timestamps UTC",
                    "relatórios JSON e Markdown reproduzíveis",
                ],
                acceptance_tests=[
                    "gera relatório em analysis_reports/aegis_mythos",
                    "inclui versões e caminho dos artefatos",
                    "preserva escopo e limites de alegação",
                ],
            ),
            ControlPlane(
                name="Defensive Swarm Router",
                purpose="Dividir trabalho entre agentes de planejamento, execução, revisão e segurança.",
                safeguards=[
                    "separação de papéis",
                    "execução somente em allowlist",
                    "revisão final antes de release",
                ],
                acceptance_tests=[
                    "plano contém agente de segurança",
                    "comandos perigosos são recusados",
                    "saída final declara incertezas",
                ],
            ),
        ]
        benchmark = self._score_controls(controls)
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "objective": objective,
            "generated_at": self.generated_at.isoformat(),
            "claim_boundary": (
                "Aegis Mythos+ é um blueprint defensivo e auditável; não afirma "
                "superioridade factual sobre sistemas externos sem benchmark independente."
            ),
            "capability_boundary": (
                "ATENA pode automatizar pesquisa, planejamento, execução permitida e relatórios; "
                "ela não é infalível, não substitui validação humana em decisões críticas e "
                "deve declarar incertezas quando as evidências forem limitadas."
            ),
            "control_planes": [asdict(control) for control in controls],
            "execution_plan": [
                "coletar requisitos e fontes verificáveis",
                "classificar risco e permissões",
                "executar somente ações permitidas",
                "validar evidências e testes",
                "salvar relatório final com trilha de auditoria",
            ],
            "benchmark": benchmark,
        }

    @staticmethod
    def _score_controls(controls: list[ControlPlane]) -> dict[str, Any]:
        coverage = sum(
            len(control.safeguards) + len(control.acceptance_tests)
            for control in controls
        )
        composite = min(100.0, 60.0 + coverage * 2.5)
        return {
            "composite_score": round(composite, 2),
            "target_delta": "+auditability/+safety/+reproducibility",
            "release_decision": (
                "ship-with-monitoring" if composite >= 85 else "hold-for-more-tests"
            ),
            "control_count": len(controls),
        }


def _render_markdown(payload: dict[str, Any]) -> str:
    controls = payload.get("control_planes", [])
    sections = [
        "# ATENA Aegis Mythos+ Report",
        "",
        f"**Status:** {payload.get('status', 'unknown')}",
        f"**Versão do schema:** {payload.get('schema_version', '1.0')}",
        f"**Objetivo:** {payload.get('objective', '')}",
        f"**Gerado em:** {payload.get('generated_at', '')}",
        "",
        "## Limite de alegação",
        str(payload.get("claim_boundary", "")),
        "",
        "## Limite operacional",
        str(payload.get("capability_boundary", "")),
        "",
        "## Control planes",
    ]
    for control in controls:
        sections.extend(
            [
                f"### {control.get('name', 'Controle')}",
                f"**Propósito:** {control.get('purpose', '')}",
                "",
                "**Salvaguardas:**",
                *[f"- {item}" for item in control.get("safeguards", [])],
                "",
                "**Testes de aceite:**",
                *[f"- {item}" for item in control.get("acceptance_tests", [])],
                "",
            ]
        )
    benchmark = payload.get("benchmark", {})
    sections.extend(
        [
            "## Benchmark interno",
            f"- Score composto: {benchmark.get('composite_score')}",
            f"- Delta-alvo: {benchmark.get('target_delta')}",
            f"- Decisão: {benchmark.get('release_decision')}",
            "",
        ]
    )
    return "\n".join(sections)


def write_reports(payload: dict[str, Any]) -> tuple[Path, Path]:
    """Write JSON and Markdown reports and return their paths."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS_DIR / f"aegis_mythos_{stamp}.json"
    md_path = REPORTS_DIR / f"aegis_mythos_{stamp}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an ATENA Aegis Mythos+ report"
    )
    parser.add_argument("objective", nargs="*", help="Objective to benchmark")
    args = parser.parse_args(argv)
    objective = " ".join(args.objective)
    payload = AegisMythosChallenger().build_plan(objective)
    json_path, md_path = write_reports(payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "json_report_path": str(json_path),
                "markdown_report_path": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
