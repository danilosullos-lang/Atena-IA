#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Executa loop semanal de evolução contínua da ATENA com Otimização Dinâmica."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from core.atena_dynamic_evolution_optimizer import AtenaDynamicEvolutionOptimizer

ROOT = Path(__file__).resolve().parent.parent

def run_loop(root: Path) -> dict[str, object]:
    print("🔱 Iniciando Loop de Evolução com Otimização Dinâmica...")
    optimizer = AtenaDynamicEvolutionOptimizer(root)
    strategy = optimizer.optimize_workflow()
    
    steps = [
        ("secret-scan", [sys.executable, str(ROOT / "core" / "atena_secret_scan.py")]),
        ("memory-maintenance", [sys.executable, str(ROOT / "core" / "atena_memory_maintenance.py")]),
        ("evolution-scorecard", [sys.executable, str(ROOT / "core" / "atena_evolution_scorecard.py")]),
        ("dynamic-optimization", [sys.executable, str(ROOT / "core" / "atena_dynamic_evolution_optimizer.py")]),
    ]
    
    results: list[dict[str, object]] = []
    for step_name, cmd in steps:
        print(f"🔄 Executando: {step_name}...")
        try:
            proc = subprocess.run(
                cmd, 
                cwd=str(root), 
                check=False, 
                capture_output=True, 
                text=True,
                timeout=strategy.get("timeout", 300)
            )
            results.append({
                "step": step_name,
                "ok": proc.returncode == 0,
                "stdout": (proc.stdout or "").strip()[:500]
            })
        except subprocess.TimeoutExpired:
            results.append({"step": step_name, "ok": False, "error": "timeout"})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if all(r["ok"] for r in results) else "warn",
        "strategy_applied": strategy,
        "results": results
    }

def main() -> int:
    payload = run_loop(ROOT)
    out_dir = ROOT / "analysis_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "ATENA_Weekly_Evolution_Loop.json", 'w') as f:
        json.dump(payload, f, indent=2)
        
    print(f"✅ Evolução concluída. Status: {payload['status']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
