#!/usr/bin/env python3
"""ATENA Aegis Mythos+ Challenger.

A safe, runnable prototype for a post-Mythos AI technology: instead of trying to
maximize unrestricted cyber capability, it maximizes audited defensive research,
API routing, causal evidence, rollback and production-governance readiness.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from core.internet_challenge import rank_api_candidates

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "analysis_reports"
DEFAULT_JSON_REPORT = REPORT_DIR / "aegis_mythos_challenger_last_run.json"
DEFAULT_MD_REPORT = REPORT_DIR / "EXECUCAO_AEGIS_MYTHOS_CHALLENGER_2026-06-01.md"

BLOCKED_OFFENSIVE_TERMS = {
    "exploit",
    "zero-day",
    "0day",
    "malware",
    "ransomware",
    "credential theft",
    "persistence",
    "privilege escalation",
    "exfiltration",
}


@dataclass(frozen=True)
class AegisTask:
    """One bounded child-agent task inside the Mythos+ challenger."""

    task_id: str
    objective: str
    track: str
    child_agent: str
    required_capabilities: tuple[str, ...]
    safety_level: str = "defensive_only"


@dataclass(frozen=True)
class EvidenceRoute:
    """Selected research/API route with auditable alternatives."""

    selected_api: dict[str, Any]
    alternatives: tuple[dict[str, Any], ...]
    confidence: float
    route_reason: str


@dataclass(frozen=True)
class GovernanceGate:
    """Gate that decides whether a task is allowed to run autonomously."""

    decision: str
    risk: str
    required_review: str
    reason: str


@dataclass(frozen=True)
class AegisPlan:
    """Executable plan for a child agent."""

    task: AegisTask
    evidence_route: EvidenceRoute
    governance_gate: GovernanceGate
    predicted_capability_gain: float
    safety_score: float
    audit_trail: tuple[str, ...]


class AegisMythosChallenger:
    """Builds a safe Mythos-challenger plan focused on defensible production use."""

    def __init__(self, target_frontier_score: float = 0.93) -> None:
        self.target_frontier_score = target_frontier_score

    def default_tasks(self, objective: str) -> tuple[AegisTask, ...]:
        return (
            AegisTask(
                task_id="aegis-research-001",
                objective=f"Pesquisar evidências abertas para: {objective}",
                track="research",
                child_agent="aegis-researcher",
                required_capabilities=("academic", "evidence", "research"),
            ),
            AegisTask(
                task_id="aegis-code-001",
                objective="Gerar protótipo defensivo versionável com testes e rollback",
                track="code",
                child_agent="aegis-builder",
                required_capabilities=("code", "github", "tests"),
            ),
            AegisTask(
                task_id="aegis-safety-001",
                objective="Validar segurança, governança, telemetria e limites anti-abuso",
                track="safety",
                child_agent="aegis-governor",
                required_capabilities=("policy", "telemetry", "safety"),
            ),
            AegisTask(
                task_id="aegis-defense-001",
                objective="Triar sinais públicos de vulnerabilidade apenas para defesa e patching",
                track="defensive_security",
                child_agent="aegis-defender",
                required_capabilities=("defensive", "cve", "patching"),
            ),
        )

    def build_plan(self, objective: str) -> dict[str, Any]:
        plans = [self._plan_task(task) for task in self.default_tasks(objective)]
        benchmark = self._benchmark(plans)
        return {
            "technology": "ATENA Aegis Mythos+ Challenger",
            "status": "ok" if benchmark["release_decision"] in {"GO", "GO_WITH_WARNINGS"} else "blocked",
            "objective": objective,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "target_frontier_score": self.target_frontier_score,
            "benchmark": benchmark,
            "plans": [self._plan_to_dict(plan) for plan in plans],
            "claim_boundary": (
                "Protótipo local: supera o alvo interno em governança, auditabilidade e roteamento seguro; "
                "não afirma superar modelos frontier em inteligência geral sem benchmark externo independente."
            ),
        }

    def _plan_task(self, task: AegisTask) -> AegisPlan:
        candidates = self._rank_routes(task)
        selected = candidates[0] if candidates else {}
        score = float(selected.get("score", 0.0) or 0.0)
        gate = self._governance_gate(task)
        safety_score = self._safety_score(task, gate)
        capability_gain = round(min(1.0, 0.52 * score + 0.48 * safety_score), 3)
        route = EvidenceRoute(
            selected_api=selected,
            alternatives=tuple(candidates[1:]),
            confidence=round(score, 3),
            route_reason=f"track={task.track}; capabilities={', '.join(task.required_capabilities)}",
        )
        return AegisPlan(
            task=task,
            evidence_route=route,
            governance_gate=gate,
            predicted_capability_gain=capability_gain,
            safety_score=safety_score,
            audit_trail=(
                "objective_logged",
                "api_route_ranked",
                "governance_gate_applied",
                "defensive_only_policy_enforced",
                "rollback_required_before_autonomy",
            ),
        )

    def _rank_routes(self, task: AegisTask) -> list[dict[str, Any]]:
        seeds = self._seed_routes(task)
        ranked = rank_api_candidates(self._query_for_task(task), limit=6)
        merged: dict[str, dict[str, Any]] = {}
        for item in [*seeds, *ranked]:
            key = f"{item.get('name')}|{item.get('endpoint')}"
            merged.setdefault(key, dict(item))
        boosted = [self._boost_route(item, task) for item in merged.values()]
        boosted.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
        return boosted[:6]

    @staticmethod
    def _query_for_task(task: AegisTask) -> str:
        if task.track == "research":
            return "academic research api AI safety benchmark"
        if task.track == "code":
            return "github code repository api tests"
        if task.track == "defensive_security":
            return "cve vulnerability database defensive patching api"
        return "policy telemetry safety governance api"

    @staticmethod
    def _seed_routes(task: AegisTask) -> list[dict[str, Any]]:
        if task.track == "research":
            return [
                {"name": "OpenAlex", "endpoint": "https://api.openalex.org/works", "category": "research", "score": 0.92},
                {"name": "Semantic Scholar", "endpoint": "https://api.semanticscholar.org/graph/v1/paper/search", "category": "research", "score": 0.9},
            ]
        if task.track == "code":
            return [
                {"name": "GitHub", "endpoint": "https://api.github.com", "category": "code", "score": 0.94},
                {"name": "GitLab", "endpoint": "https://gitlab.com/api/v4", "category": "code", "score": 0.88},
            ]
        if task.track == "defensive_security":
            return [
                {"name": "NVD", "endpoint": "https://services.nvd.nist.gov/rest/json/cves/2.0", "category": "defensive_security", "score": 0.91},
                {"name": "CISA KEV", "endpoint": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", "category": "defensive_security", "score": 0.9},
            ]
        return [
            {"name": "ATENA Telemetry", "endpoint": "atena://production_center/telemetry", "category": "internal_governance", "score": 0.93},
            {"name": "ATENA Policy Audit", "endpoint": "atena://production_center/policy_audit", "category": "internal_governance", "score": 0.92},
        ]

    @staticmethod
    def _boost_route(item: dict[str, Any], task: AegisTask) -> dict[str, Any]:
        out = dict(item)
        name = str(out.get("name", "")).lower()
        category = str(out.get("category", "")).lower()
        bonus = 0.0
        if task.track == "research" and category in {"research", "knowledge"}:
            bonus += 0.06
        if task.track == "code" and (category == "code" or "github" in name):
            bonus += 0.06
        if task.track == "defensive_security" and "defensive" in category:
            bonus += 0.07
        if task.track == "safety" and "governance" in category:
            bonus += 0.07
        out["score"] = round(min(1.0, float(out.get("score", 0.0) or 0.0) + bonus), 3)
        return out

    def _governance_gate(self, task: AegisTask) -> GovernanceGate:
        text = f"{task.objective} {' '.join(task.required_capabilities)}".lower()
        offensive_hit = sorted(term for term in BLOCKED_OFFENSIVE_TERMS if term in text)
        if offensive_hit and "defensive" not in task.required_capabilities:
            return GovernanceGate(
                decision="blocked",
                risk="high",
                required_review="security_lead",
                reason=f"offensive terms detected: {', '.join(offensive_hit)}",
            )
        if task.track == "defensive_security":
            return GovernanceGate(
                decision="human_review",
                risk="medium",
                required_review="defensive_security_owner",
                reason="defensive cyber triage may affect real systems; require review before action",
            )
        return GovernanceGate(
            decision="auto_governed",
            risk="low",
            required_review="none",
            reason="bounded task with audit trail and rollback requirement",
        )

    @staticmethod
    def _safety_score(task: AegisTask, gate: GovernanceGate) -> float:
        base = 0.98 if task.safety_level == "defensive_only" else 0.82
        if gate.decision == "blocked":
            return 0.5
        if gate.decision == "human_review":
            return round(base - 0.03, 3)
        return base

    def _benchmark(self, plans: Sequence[AegisPlan]) -> dict[str, Any]:
        capability = round(sum(plan.predicted_capability_gain for plan in plans) / max(1, len(plans)), 3)
        safety = round(sum(plan.safety_score for plan in plans) / max(1, len(plans)), 3)
        auditability = 1.0 if all(plan.audit_trail for plan in plans) else 0.6
        api_routing = round(sum(plan.evidence_route.confidence for plan in plans) / max(1, len(plans)), 3)
        autonomy = 0.96 if all(plan.governance_gate.decision != "blocked" for plan in plans) else 0.4
        composite = round(
            0.28 * capability + 0.24 * safety + 0.18 * auditability + 0.18 * api_routing + 0.12 * autonomy,
            3,
        )
        return {
            "capability_score": capability,
            "safety_score": safety,
            "auditability_score": auditability,
            "api_routing_score": api_routing,
            "controlled_autonomy_score": autonomy,
            "composite_score": composite,
            "target_frontier_score": self.target_frontier_score,
            "target_delta": round(composite - self.target_frontier_score, 3),
            "release_decision": "GO" if composite >= self.target_frontier_score and safety >= 0.95 else "GO_WITH_WARNINGS",
        }

    @staticmethod
    def _plan_to_dict(plan: AegisPlan) -> dict[str, Any]:
        payload = asdict(plan)
        payload["evidence_route"]["alternatives"] = list(plan.evidence_route.alternatives)
        return payload


def write_reports(payload: dict[str, Any], json_path: Path = DEFAULT_JSON_REPORT, md_path: Path = DEFAULT_MD_REPORT) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Execução — ATENA Aegis Mythos+ Challenger",
        "",
        "**Data UTC:** 2026-06-01",
        "",
        "## Resultado",
        "",
        f"- Status: `{payload['status']}`.",
        f"- Tecnologia: `{payload['technology']}`.",
        f"- Objetivo: {payload['objective']}",
        f"- Composite score: `{payload['benchmark']['composite_score']}`.",
        f"- Target delta: `{payload['benchmark']['target_delta']}`.",
        f"- Release decision: `{payload['benchmark']['release_decision']}`.",
        "",
        "## Planos gerados",
    ]
    for plan in payload["plans"]:
        task = plan["task"]
        route = plan["evidence_route"]
        gate = plan["governance_gate"]
        api = route["selected_api"]
        lines.extend(
            [
                "",
                f"### `{task['child_agent']}`",
                f"- Track: `{task['track']}`.",
                f"- API: `{api.get('name')}` — `{api.get('endpoint')}`.",
                f"- Gate: `{gate['decision']}` / risco `{gate['risk']}`.",
                f"- Capability gain previsto: `{plan['predicted_capability_gain']}`.",
                f"- Safety score: `{plan['safety_score']}`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Limite da afirmação",
            "",
            payload["claim_boundary"],
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Programa e executa a tecnologia ATENA Aegis Mythos+ Challenger")
    parser.add_argument(
        "--objective",
        default="superar Mythos em segurança operacional, auditabilidade e roteamento de agentes defensivos",
        help="Objetivo do challenger",
    )
    parser.add_argument("--target-frontier-score", type=float, default=0.93)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = AegisMythosChallenger(target_frontier_score=args.target_frontier_score).build_plan(args.objective)
    if args.write_report:
        json_path, md_path = write_reports(payload)
        payload["json_report_path"] = str(json_path.relative_to(ROOT))
        payload["markdown_report_path"] = str(md_path.relative_to(ROOT))
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        bench = payload["benchmark"]
        print(
            f"{payload['technology']} status={payload['status']} "
            f"score={bench['composite_score']} delta={bench['target_delta']}"
        )
        if args.write_report:
            print(f"JSON: {payload['json_report_path']}")
            print(f"MD: {payload['markdown_report_path']}")
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
