#!/usr/bin/env python3
"""Executa um ciclo curto e auditável de aprendizagem local da ATENA.

O modelo gera observações e propostas; não recebe permissão para editar código-fonte.
As propostas ficam em atena_evolution/proposals para revisão e testes posteriores.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "atena_evolution" / "llm_learning_memory.json"
PROPOSALS_DIR = ROOT / "atena_evolution" / "proposals"
MODEL = os.getenv("ATENA_LOCAL_MODEL", "qwen2.5:3b-instruct")


def load_memory() -> list[dict]:
    if not MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def ask_local_model(memory: list[dict]) -> dict:
    context = json.dumps(memory[-8:], ensure_ascii=False, indent=2)
    prompt = f"""Você é o módulo local de análise da ATENA. Faça um ciclo de aprendizagem de no máximo cinco minutos.
Analise apenas o contexto abaixo e produza JSON válido com as chaves: insights (lista de strings),
risks (lista de strings), proposed_changes (lista de objetos com file, rationale e tests),
next_cycle (lista de strings). Não escreva código, não peça segredos e não recomende alterações
fora de atena_evolution/proposals. Diferencie fatos de hipóteses.
Memória recente:
{context}
"""
    result = subprocess.run(
        ["ollama", "run", MODEL, prompt],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    raw = result.stdout.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"raw": raw}
    except json.JSONDecodeError:
        return {"raw": raw, "parse_error": True}


def main() -> int:
    start = time.monotonic()
    now = datetime.now(timezone.utc)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    memory = load_memory()
    cycle = {
        "timestamp": now.isoformat(),
        "model": MODEL,
        "duration_limit_seconds": 300,
        "observations": ask_local_model(memory),
    }
    memory.append(cycle)
    MEMORY_PATH.write_text(json.dumps(memory[-200:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proposal_path = PROPOSALS_DIR / f"cycle-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    proposal_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": MODEL, "elapsed_seconds": round(time.monotonic() - start, 2), "memory": str(MEMORY_PATH), "proposal": str(proposal_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
