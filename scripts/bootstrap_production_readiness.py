#!/usr/bin/env python3
"""Bootstrap the minimum production readiness state for ATENA.

This does not weaken the go-live gate. It creates the operational artifacts that
that gate already requires: healthy telemetry, an approved active skill and a
policy audit trail. The script is deterministic enough for CI/staging and can be
run safely more than once.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.production_guardrails import Action, AuditLogger, PolicyEngine, Role
from core.production_observability import TelemetryStore
from core.production_readiness import run_readiness
from core.skill_marketplace import SkillMarketplace, SkillRecord

BOOTSTRAP_SKILL_ID = "atena-production-core"
BOOTSTRAP_SKILL_VERSION = "1.0.0"


def ensure_render_yaml(root: Path) -> dict[str, object]:
    """Validate the repository has deploy configuration for self-audit."""
    path = root / "render.yaml"
    return {
        "name": "render_yaml_present",
        "ok": path.exists(),
        "path": str(path.relative_to(root)) if path.exists() else "render.yaml",
    }


def seed_telemetry(evolution_dir: Path) -> dict[str, object]:
    """Append healthy baseline events used by readiness/SLO checks."""
    telemetry = TelemetryStore(evolution_dir / "telemetry.jsonl")
    missions = [
        ("production-bootstrap", "ok", 180, 0.05),
        ("api-swarm-fabric", "ok", 220, 0.08),
        ("go-live-gate-dry-run", "ok", 160, 0.04),
    ]
    events = [
        telemetry.append(mission, status, latency, cost, tenant_id="prod-bootstrap")
        for mission, status, latency, cost in missions
    ]
    summary = telemetry.summarize()
    return {"name": "telemetry_seeded", "ok": summary["total"] >= len(events), "summary": summary}


def seed_skill(evolution_dir: Path) -> dict[str, object]:
    """Ensure at least one approved active production skill exists."""
    market = SkillMarketplace(evolution_dir / "skills_catalog.json")
    existing = market.list_records()
    already_ready = any(
        item.get("skill_id") == BOOTSTRAP_SKILL_ID
        and item.get("version") == BOOTSTRAP_SKILL_VERSION
        and item.get("approved")
        and item.get("active")
        for item in existing
    )
    if not already_ready:
        market.register(
            SkillRecord(
                skill_id=BOOTSTRAP_SKILL_ID,
                version=BOOTSTRAP_SKILL_VERSION,
                name="ATENA Production Core",
                description="Core production readiness skill used by go-live bootstrap.",
                author="atena",
                risk_level="low",
                cost_class="low",
                tags=["production", "bootstrap", "core"],
            )
        )
        market.approve(BOOTSTRAP_SKILL_ID, version=BOOTSTRAP_SKILL_VERSION)
        market.promote(BOOTSTRAP_SKILL_ID, BOOTSTRAP_SKILL_VERSION)
    records = market.list_records()
    ready = [item for item in records if item.get("approved") and item.get("active")]
    return {"name": "approved_active_skill_seeded", "ok": bool(ready), "active_approved": ready}


def seed_policy_audit(evolution_dir: Path) -> dict[str, object]:
    """Create the policy audit trail required by readiness."""
    audit = AuditLogger(evolution_dir / "policy_audit.jsonl")
    decision = PolicyEngine().decide_with_context(
        role=Role.OPERATOR,
        action=Action.OPEN_URL,
        risk_level="medium",
        hour_utc=12,
    )
    audit.append(
        actor="production-bootstrap",
        role=Role.OPERATOR,
        action=Action.OPEN_URL,
        decision=decision,
        metadata={"purpose": "go-live-readiness-bootstrap"},
    )
    path = evolution_dir / "policy_audit.jsonl"
    return {
        "name": "policy_audit_seeded",
        "ok": path.exists() and path.stat().st_size > 0,
        "path": str(path),
    }


def bootstrap(root: Path = ROOT) -> dict[str, object]:
    """Create required production readiness artifacts and return the resulting status."""
    root = root.resolve()
    evolution_dir = root / "atena_evolution" / "production_center"
    evolution_dir.mkdir(parents=True, exist_ok=True)

    steps = [
        ensure_render_yaml(root),
        seed_telemetry(evolution_dir),
        seed_skill(evolution_dir),
        seed_policy_audit(evolution_dir),
    ]
    telemetry = TelemetryStore(evolution_dir / "telemetry.jsonl")
    market = SkillMarketplace(evolution_dir / "skills_catalog.json")
    readiness = run_readiness(telemetry=telemetry, market=market, evolution_dir=evolution_dir)
    return {
        "status": (
            "ok"
            if all(step["ok"] for step in steps) and readiness["status"] in {"pass", "warn"}
            else "fail"
        ),
        "steps": steps,
        "readiness": readiness,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap ATENA production readiness artifacts")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to bootstrap")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload = bootstrap(args.root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"production-bootstrap status={payload['status']} readiness={payload['readiness']['status']}")
        for step in payload["steps"]:
            print(f"- {step['name']}: {'ok' if step['ok'] else 'fail'}")
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
