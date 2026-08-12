#!/usr/bin/env python3
"""Executa um ciclo curto e auditável de aprendizagem local da ATENA.

O modelo gera observações e propostas; não recebe permissão para editar código-fonte.
As propostas ficam em atena_evolution/proposals para revisão e testes posteriores.
"""
from __future__ import annotations

import json
import os
import re
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


ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
REQUIRED_KEYS = {"insights", "risks", "proposed_changes", "next_cycle"}


def parse_model_json(raw: str) -> dict:
    """Normalize Ollama output and reject anything outside the expected schema."""
    cleaned = ANSI_RE.sub("", raw).replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    decoder = json.JSONDecoder()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("A resposta do modelo não contém um objeto JSON")
    parsed, _ = decoder.raw_decode(cleaned[start:])
    if not isinstance(parsed, dict) or not REQUIRED_KEYS.issubset(parsed):
        raise ValueError("A resposta do modelo não atende ao esquema de evolução")
    if not isinstance(parsed["insights"], list) or not all(isinstance(item, str) for item in parsed["insights"]):
        raise ValueError("insights deve ser uma lista de textos")
    if not isinstance(parsed["risks"], list) or not all(isinstance(item, str) for item in parsed["risks"]):
        raise ValueError("risks deve ser uma lista de textos")
    if not isinstance(parsed["next_cycle"], list) or not all(isinstance(item, str) for item in parsed["next_cycle"]):
        raise ValueError("next_cycle deve ser uma lista de textos")
    if not isinstance(parsed["proposed_changes"], list):
        raise ValueError("proposed_changes deve ser uma lista")
    for proposal in parsed["proposed_changes"]:
        if not isinstance(proposal, dict) or not {"file", "rationale", "tests"}.issubset(proposal):
            raise ValueError("cada proposta precisa de file, rationale e tests")
        if not isinstance(proposal["file"], str) or not isinstance(proposal["rationale"], str):
            raise ValueError("file e rationale devem ser textos")
        if not isinstance(proposal["tests"], list) or not all(isinstance(item, str) for item in proposal["tests"]):
            raise ValueError("tests deve ser uma lista de textos")
    return parsed


def ask_local_model(memory: list[dict]) -> dict:
    context = json.dumps(memory[-8:], ensure_ascii=False, indent=2)
    prompt = f"""Você é o módulo local de análise da ATENA. Faça um ciclo de aprendizagem de no máximo cinco minutos.
Responda SOMENTE com um objeto JSON, sem Markdown, sem comentários, sem códigos ANSI e sem texto antes ou depois.
As chaves obrigatórias são: insights (lista de strings), risks (lista de strings), proposed_changes
(lista de objetos com file, rationale e tests) e next_cycle (lista de strings). Não escreva código,
não peça segredos e não recomende alterações fora de atena_evolution/proposals. Diferencie fatos de hipóteses.
Memória recente:
{context}
"""
    result = subprocess.run(
        ["ollama", "run", MODEL, "--format", "json", "--nowordwrap"],
        cwd=ROOT,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Ollama terminou com código {result.returncode}: {result.stderr[-500:]}")
    return parse_model_json(result.stdout)


def main() -> int:
    start = time.monotonic()
    now = datetime.now(timezone.utc)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    memory = load_memory()
    observations = ask_local_model(memory)
    cycle = {
        "timestamp": now.isoformat(),
        "model": MODEL,
        "duration_limit_seconds": 300,
        "observations": observations,
    }
    memory.append(cycle)
    MEMORY_PATH.write_text(json.dumps(memory[-200:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proposal_path = PROPOSALS_DIR / f"cycle-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    proposal_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": MODEL, "elapsed_seconds": round(time.monotonic() - start, 2), "memory": str(MEMORY_PATH), "proposal": str(proposal_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
