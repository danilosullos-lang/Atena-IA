#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a maximum-improvement analysis plan for ATENA.

The report is intentionally evidence-driven: it scans repository structure,
known launcher entrypoints, generated artifacts, and quality configuration so the
recommendations can be regenerated instead of being only hand-written notes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "analysis_reports"
REPORT_BASENAME = "ATENA_ANALISE_COMPLETA_E_PLANO_MAXIMO"


@dataclass(frozen=True)
class Recommendation:
    priority: str
    area: str
    title: str
    why: str
    create: str
    acceptance: list[str]


def _count_files(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob(pattern) if item.is_file())


def _launcher_entrypoints() -> dict[str, bool]:
    expected = {
        "core/main.py": ROOT / "core" / "main.py",
        "core/atena_doctor.py": ROOT / "core" / "atena_doctor.py",
        "core/atena_benchmark.py": ROOT / "core" / "atena_benchmark.py",
        "core/atena_release_gate.py": ROOT / "core" / "atena_release_gate.py",
        "core/atena_terminal_assistant.py": (
            ROOT / "core" / "atena_terminal_assistant.py"
        ),
        "core/atena_aegis_mythos_challenger.py": (
            ROOT / "core" / "atena_aegis_mythos_challenger.py"
        ),
    }
    return {name: path.exists() for name, path in expected.items()}


def _has_conflict_markers(path: Path) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8", errors="ignore")
    markers = ("<<<<<<<", "=======", ">>>>>>>")
    return any(marker in content for marker in markers)


def collect_snapshot() -> dict[str, Any]:
    """Collect a lightweight repository snapshot for the report."""
    entrypoints = _launcher_entrypoints()
    return {
        "root": str(ROOT),
        "counts": {
            "core_py": _count_files(ROOT / "core", "*.py"),
            "modules_py": _count_files(ROOT / "modules", "*.py"),
            "protocols_py": _count_files(ROOT / "protocols", "*.py"),
            "unit_tests_py": _count_files(ROOT / "tests" / "unit", "*.py"),
            "generated_files": _count_files(ROOT / "generated"),
            "analysis_reports": _count_files(ROOT / "analysis_reports"),
        },
        "launcher_entrypoints": entrypoints,
        "missing_launcher_entrypoints": [
            name for name, ok in entrypoints.items() if not ok
        ],
        "quality_flags": {
            "gitignore_has_conflict_markers": _has_conflict_markers(
                ROOT / ".gitignore"
            ),
            "food_delivery_pack_exists": (
                (ROOT / "generated" / "atena_food_delivery_push_ready").exists()
            ),
            "aegis_mythos_exists": (
                (ROOT / "core" / "atena_aegis_mythos_challenger.py").exists()
            ),
        },
    }


def build_recommendations(snapshot: dict[str, Any]) -> list[Recommendation]:
    missing = ", ".join(snapshot.get("missing_launcher_entrypoints", [])) or "nenhum"
    return [
        Recommendation(
            priority="P0",
            area="Confiabilidade do launcher",
            title="Fechar comandos quebrados e contratos de CLI",
            why=f"O launcher expõe comandos que precisam existir de ponta a ponta; ausentes detectados: {missing}.",
            create="Um contrato de comandos (`atena doctor`, `benchmark`, `release-gate`, `self-test`) com smoke tests que falham quando script referenciado não existe.",
            acceptance=[
                "todo comando listado em `bash atena --help` executa ou informa fallback claro",
                "teste de contrato cobre scripts do launcher",
                "doctor retorna JSON opcional para automação",
            ],
        ),
        Recommendation(
            priority="P0",
            area="Higiene de repositório",
            title="Eliminar marcadores de merge e estados locais versionados",
            why="Marcadores de merge em arquivos raiz e logs/venvs versionados reduzem confiança no push-ready.",
            create="Um baseline limpo de `.gitignore`, política de artefatos locais e verificação CI para conflito de merge.",
            acceptance=[
                "nenhum `<<<<<<<`, `=======` ou `>>>>>>>` em arquivos versionados",
                "logs, caches, venvs e relatórios temporários ignorados",
                "CI roda verificação de higiene antes dos testes",
            ],
        ),
        Recommendation(
            priority="P0",
            area="Segurança e alegações",
            title="Separar marketing de capacidade validada",
            why="O projeto declara AGI e perfeição operacional; isso precisa estar acoplado a evidências reproduzíveis e limites explícitos.",
            create="Um scorecard público com métricas, datasets, gates, riscos e limites operacionais por versão.",
            acceptance=[
                "cada claim possui métrica e comando de validação",
                "relatórios declaram incertezas e fontes",
                "gates bloqueiam release quando evidência estiver ausente",
            ],
        ),
        Recommendation(
            priority="P1",
            area="Produto e apps gerados",
            title="Transformar geradores em fábrica validada de produtos",
            why="Há apps gerados e scaffolds úteis; falta catálogo de templates com maturidade, testes e deploy padrão.",
            create="Uma `Atena App Factory` com templates versionados, manifestos, testes mínimos e esteiras Docker/CI por template.",
            acceptance=[
                "cada template gera README, testes, Docker/CI e checklist",
                "backend, mobile e web têm smoke tests independentes",
                "artefatos gerados recebem manifest com versão da Atena",
            ],
        ),
        Recommendation(
            priority="P1",
            area="Memória e avaliação",
            title="Criar memória de decisões com avaliação contínua",
            why="Módulos de memória, telemetria e evolução existem, mas precisam convergir para aprendizado verificável entre missões.",
            create="Um ledger de decisões com objetivo, fontes, comandos, resultado, regressões e feedback humano.",
            acceptance=[
                "cada missão salva plano, comandos e resultado",
                "falhas viram testes regressivos",
                "dashboard mostra taxa de sucesso por tipo de tarefa",
            ],
        ),
        Recommendation(
            priority="P2",
            area="Experiência do operador",
            title="Unificar UX de instalação, Colab, Windows e Linux",
            why="A documentação possui caminhos e nomes divergentes; isso atrapalha adoção rápida.",
            create="Um instalador único com modos `--minimal`, `--dev`, `--ml`, `--full` e documentação sincronizada.",
            acceptance=[
                "quickstart usa um único nome de diretório",
                "bootstrap valida Python e dependências por perfil",
                "erros trazem remediação executável",
            ],
        ),
    ]


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    snapshot = collect_snapshot()
    recommendations = build_recommendations(snapshot)
    return {
        "generated_at": now.isoformat(),
        "summary": {
            "verdict": (
                "ATENA é ampla e produtiva, mas precisa consolidar confiabilidade, claims verificáveis e produto gerado com contratos de qualidade."
            ),
            "highest_leverage_creation": (
                "Atena Max Improvement Program: contrato de CLI + higiene de repo + scorecard de claims + app factory validada."
            ),
        },
        "snapshot": snapshot,
        "strengths": [
            "Arquitetura rica com core, modules, protocols, tests e generated apps.",
            "Launcher central com modos de assistente, doctor, produção e missões.",
            "Boa base de testes unitários e exemplos de apps gerados.",
            "Capacidades de segurança, memória, orquestração, internet e geração de software já aparecem no repositório.",
        ],
        "risks": [
            "Alguns entrypoints do launcher não têm script correspondente.",
            "Configuração e documentação mostram sinais de drift e conflito de merge.",
            "Claims fortes precisam de scorecards reproduzíveis e limites operacionais.",
            "Apps gerados precisam maturar de scaffold para deploy real com persistência, auth e observabilidade.",
        ],
        "recommendations": [asdict(item) for item in recommendations],
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["snapshot"]["counts"]
    missing = report["snapshot"]["missing_launcher_entrypoints"]
    rec_lines: list[str] = []
    for index, rec in enumerate(report["recommendations"], start=1):
        acceptance = "\n".join(f"  - {item}" for item in rec["acceptance"])
        rec_lines.append(
            f"### {index}. [{rec['priority']}] {rec['title']}\n"
            f"- **Área:** {rec['area']}\n"
            f"- **Por quê:** {rec['why']}\n"
            f"- **Criar:** {rec['create']}\n"
            f"- **Aceite:**\n{acceptance}"
        )
    strengths = "\n".join(f"- {item}" for item in report["strengths"])
    risks = "\n".join(f"- {item}" for item in report["risks"])
    missing_md = "\n".join(f"- {item}" for item in missing) or "- Nenhum"
    return f"""# Análise Completa da ATENA e Plano de Melhoria Máxima

**Gerado em:** {report['generated_at']}
**Veredito:** {report['summary']['verdict']}

## 1. Snapshot do repositório

| Área | Quantidade |
|---|---:|
| `core/*.py` | {counts['core_py']} |
| `modules/*.py` | {counts['modules_py']} |
| `protocols/*.py` | {counts['protocols_py']} |
| `tests/unit/*.py` | {counts['unit_tests_py']} |
| `generated/` arquivos | {counts['generated_files']} |
| `analysis_reports/` arquivos | {counts['analysis_reports']} |

## 2. Pontos fortes

{strengths}

## 3. Riscos e gargalos

{risks}

## 4. Entrypoints ausentes detectados

{missing_md}

## 5. O que recomendo criar para melhorar ao máximo

{chr(10).join(rec_lines)}

## 6. Criação executada nesta rodada

Criei este programa de melhoria máxima como artefato reproduzível:

- `core/atena_max_improvement_plan.py`: gera snapshot, recomendações, JSON e Markdown.
- `analysis_reports/{REPORT_BASENAME}_2026-06-09.md`: relatório executivo para humanos.
- `analysis_reports/{REPORT_BASENAME}_2026-06-09.json`: backlog estruturado para automação.

## 7. Próxima criação recomendada

A próxima entrega de maior impacto é implementar o **contrato de CLI do launcher** e corrigir os comandos faltantes, porque isso transforma a Atena de “faz muita coisa” para “faz muita coisa com contrato, evidência e regressão automática”.
"""


def write_report(
    report: dict[str, Any], date_label: str | None = None
) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if date_label is None:
        date_label = report["generated_at"][:10]
    md_path = REPORTS_DIR / f"{REPORT_BASENAME}_{date_label}.md"
    json_path = REPORTS_DIR / f"{REPORT_BASENAME}_{date_label}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return md_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate ATENA max improvement analysis"
    )
    parser.add_argument(
        "--date", default=None, help="Date label for output files (YYYY-MM-DD)"
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args(argv)
    report = build_report()
    md_path, json_path = write_report(report, date_label=args.date)
    if args.json:
        print(
            json.dumps(
                {"markdown": str(md_path), "json": str(json_path)}, ensure_ascii=False
            )
        )
    else:
        print(f"Relatório criado: {md_path.relative_to(ROOT)}")
        print(f"Backlog JSON criado: {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
