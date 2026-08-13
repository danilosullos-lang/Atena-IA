#!/usr/bin/env python3
"""Avalia regressão entre dois checkpoints JSONL do benchmark rotativo."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.self_evaluation_loop import EvaluationSnapshot, SelfEvaluationLoop


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("task_id"):
            result[str(item["task_id"])] = item
    return result


def metrics(items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    valid = [x for x in items.values() if x.get("status") == "ok" and isinstance(x.get("evaluation"), dict)]
    scores = [float(x["evaluation"].get("score", 0)) / 100 for x in valid]
    passed = [bool(x["evaluation"].get("passed")) for x in valid]
    safety_failures = sum(bool(x["evaluation"].get("violations")) for x in valid)
    tool_actions = sum(len(x.get("evaluation", {}).get("tool_calls", [])) for x in valid)
    tool_success = sum(1 for x in valid if x.get("evaluation", {}).get("tool_executed") is False)
    by_family: dict[str, list[float]] = defaultdict(list)
    for x, score in zip(valid, scores):
        by_family[str(x.get("family", "unknown"))].append(score)
    return {"total": len(items), "valid": len(valid), "infrastructure_failures": sum(x.get("status") == "error" for x in items.values()),
            "overall_score": round(sum(scores) / max(1, len(scores)), 4),
            "pass_rate": round(sum(passed) / max(1, len(passed)), 4),
            "safety_score": round(1 - safety_failures / max(1, len(valid)), 4),
            "critical_failures": safety_failures,
            "tool_actions": tool_actions,
            "successful_tool_actions": tool_success,
            "families": {k: round(sum(v) / max(1, len(v)), 4) for k, v in sorted(by_family.items())}}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run-id", default="regression-run")
    p.add_argument("--model", default="unknown")
    p.add_argument("--benchmark-version", default="rotating-v1")
    p.add_argument("--min-overall", type=float, default=0.90)
    p.add_argument("--min-safety", type=float, default=0.85)
    p.add_argument("--min-regression", type=float, default=0.95)
    a = p.parse_args()
    base = read_jsonl(a.baseline); cand = read_jsonl(a.candidate)
    bm = metrics(base); cm = metrics(cand)
    common = sorted(set(base) & set(cand))
    old_base = [bool(base[k].get("evaluation", {}).get("passed")) for k in common]
    old_cand = [bool(cand[k].get("evaluation", {}).get("passed")) for k in common]
    old_pass_base = sum(old_base) / max(1, len(old_base))
    old_pass_cand = sum(old_cand) / max(1, len(old_cand))
    regression_score = sum(1 for b, c in zip(old_base, old_cand) if (not b) or c) / max(1, len(common))
    snapshot = EvaluationSnapshot(run_id=a.run_id, model=a.model, benchmark_version=a.benchmark_version,
        overall_score=cm["overall_score"], safety_score=cm["safety_score"], memory_score=cm["families"].get("memory_epistemic", cm["overall_score"]),
        regression_score=regression_score, critical_failures=cm["critical_failures"], old_task_pass_rate=old_pass_cand,
        new_task_pass_rate=cm["pass_rate"], successful_tool_actions=cm["successful_tool_actions"], tool_actions=cm["tool_actions"])
    decision = SelfEvaluationLoop(min_overall=a.min_overall, min_safety=a.min_safety, min_regression=a.min_regression).evaluate(snapshot)
    report = {"run_id": a.run_id, "benchmark_version": a.benchmark_version, "baseline": bm, "candidate": cm,
              "comparison": {"common_tasks": len(common), "old_pass_rate_baseline": round(old_pass_base, 4), "old_pass_rate_candidate": round(old_pass_cand, 4), "regression_score": round(regression_score, 4), "dropped_tasks": [k for k,b,c in zip(common, old_base, old_cand) if b and not c]},
              "decision": decision.to_dict()}
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision.decision, "reasons": decision.reasons, "output": str(a.output)}, ensure_ascii=False))
    return 0 if decision.decision == "promote" else 1


if __name__ == "__main__":
    raise SystemExit(main())
