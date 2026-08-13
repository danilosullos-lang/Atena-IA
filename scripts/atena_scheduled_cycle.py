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
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from core.episodic_memory import build_episode
from core.memory_store import MemoryStore

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "atena_evolution" / "llm_learning_memory.json"
PROPOSALS_DIR = ROOT / "atena_evolution" / "proposals"
SQLITE_PATH = Path(os.getenv("ATENA_MEMORY_DB", str(ROOT / "atena_evolution" / "memory.sqlite3")))
MODEL = os.getenv("ATENA_LOCAL_MODEL", "qwen2.5:3b-instruct")
SQLITE_REQUIRED = os.getenv("ATENA_SQLITE_REQUIRED", "0").lower() in {"1", "true", "yes"}
SYSTEM_VERSION = os.getenv("GITHUB_SHA", "local")


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
MODEL_SCHEMA = {
    "type": "object",
    "required": ["insights", "risks", "proposed_changes", "next_cycle"],
    "properties": {
        "insights": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "proposed_changes": {"type": "array", "items": {"type": "object"}},
        "next_cycle": {"type": "array", "items": {"type": "string"}},
    },
}


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


def cycle_to_episode(cycle: dict) -> dict:
    """Converte o formato legado do ciclo para o contrato episódico."""
    observations = cycle["observations"]
    output = json.dumps(observations, ensure_ascii=False, sort_keys=True)
    return build_episode(
        record_type="outcome",
        task_id="scheduled-learning-cycle",
        domain="self_evolution",
        output=output,
        source_type="llm",
        source_id=f"cycle:{cycle['timestamp']}",
        system_version=SYSTEM_VERSION,
        model=cycle.get("model", MODEL),
        status="unverified",
        confidence=0.0,
        event_extra={
            "environment": {
                "duration_limit_seconds": cycle.get("duration_limit_seconds", 300),
                "storage_mode": "dual-write",
            }
        },
    )


def write_sqlite_cycle(cycle: dict) -> str:
    """Persiste o ciclo no SQLite e verifica a integridade da cadeia."""
    episode = cycle_to_episode(cycle)
    with MemoryStore(SQLITE_PATH) as store:
        memory_id = store.append(episode)
        store.verify_integrity()
    return memory_id


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
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": MODEL_SCHEMA,
        "options": {"temperature": 0.1},
    }
    request = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama indisponível em {host}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama retornou uma resposta HTTP que não é JSON") from exc
    content = body.get("message", {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError("Resposta do Ollama não contém message.content textual")
    return parse_model_json(content)


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
    # Compatibilidade: o JSON legado continua sendo escrito primeiro.
    MEMORY_PATH.write_text(json.dumps(memory[-200:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proposal_path = PROPOSALS_DIR / f"cycle-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    proposal_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sqlite_status = "ok"
    sqlite_memory_id = None
    try:
        sqlite_memory_id = write_sqlite_cycle(cycle)
    except Exception as exc:
        sqlite_status = f"error:{type(exc).__name__}"
        print(f"SQLite dual-write falhou: {exc}", file=sys.stderr)
        if SQLITE_REQUIRED:
            raise

    print(json.dumps({
        "model": MODEL,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "memory": str(MEMORY_PATH),
        "proposal": str(proposal_path),
        "sqlite": str(SQLITE_PATH),
        "sqlite_status": sqlite_status,
        "sqlite_memory_id": sqlite_memory_id,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
