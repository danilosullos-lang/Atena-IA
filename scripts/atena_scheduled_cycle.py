#!/usr/bin/env python3
"""Executa um ciclo curto e auditável de aprendizagem local da ATENA.

O modelo gera observações e propostas; não recebe permissão para editar código-fonte.
As propostas ficam em atena_evolution/proposals para revisão e testes posteriores.
"""
from __future__ import annotations

import hashlib
import importlib.util
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
from core.memory_consolidation import compact_context
from core.memory_retrieval import format_context, retrieve_context
from core.research_sources import fetch_configured_sources

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "atena_evolution" / "llm_learning_memory.json"
PROPOSALS_DIR = ROOT / "atena_evolution" / "proposals"
SQLITE_PATH = Path(os.getenv("ATENA_MEMORY_DB", str(ROOT / "atena_evolution" / "memory.sqlite3")))
MODEL = os.getenv("ATENA_LOCAL_MODEL", "qwen2.5:3b-instruct")
SQLITE_REQUIRED = os.getenv("ATENA_SQLITE_REQUIRED", "0").lower() in {"1", "true", "yes"}
SYSTEM_VERSION = os.getenv("GITHUB_SHA", "local")

RESEARCH_TOPICS = [
    ("memória histórica", "Como recuperar evidências antigas sem confundir hipótese com fato?"),
    ("deduplicação", "Como detectar memórias repetidas e preservar apenas novas evidências?"),
    ("segurança", "Quais riscos operacionais novos devem ser testados no próximo ciclo?"),
    ("qualidade de código", "Qual módulo ou teste pode melhorar a confiabilidade do sistema?"),
    ("fontes externas", "Quais fontes públicas autorizadas podem preencher as lacunas atuais?"),
    ("generalização", "Como testar o mesmo princípio em um domínio inédito?"),
    ("FAISS e recuperação", "Como melhorar a busca semântica e a diversidade do contexto?"),
    ("autocorreção", "Qual falha observada precisa de um teste de regressão novo?"),
]
SOURCE_MODULE_PATH = ROOT / "core" / "Atena sources extended.py"


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
        "insights": {"type": "array", "items": {"type": "object", "required": ["text", "evidence_refs", "type", "confidence"], "properties": {"text": {"type": "string"}, "evidence_refs": {"type": "array", "items": {"type": "string"}}, "type": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}}},
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
    if not isinstance(parsed["insights"], list):
        raise ValueError("insights deve ser uma lista")
    normalized_insights = []
    for item in parsed["insights"]:
        # Compatibilidade com memórias antigas; novos retornos devem ser objetos.
        if isinstance(item, str):
            normalized_insights.append({"text": item, "evidence_refs": [], "type": "limitation", "confidence": 0.0})
            continue
        if not isinstance(item, dict) or not {"text", "evidence_refs", "type", "confidence"}.issubset(item):
            raise ValueError("cada insight precisa de text, evidence_refs, type e confidence")
        if not isinstance(item["text"], str) or not isinstance(item["evidence_refs"], list) or not all(isinstance(ref, str) for ref in item["evidence_refs"]):
            raise ValueError("text e evidence_refs têm tipos inválidos")
        if not isinstance(item["confidence"], (int, float)) or not 0 <= item["confidence"] <= 1:
            raise ValueError("confidence do insight deve estar entre 0 e 1")
        item["evidence_refs"] = [ref.strip() for ref in item["evidence_refs"] if ref.strip()]
        if not item["evidence_refs"]:
            item["confidence"] = 0.0
            item["type"] = "limitation"
        normalized_insights.append(item)
    parsed["insights"] = normalized_insights
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


def link_cycle_evidence(cycle_id: str, observations: dict, source_ids: set[str]) -> str:
    """Liga evidence_refs válidos ao episódio do ciclo e promove conservadoramente."""
    refs: set[str] = set()
    for insight in observations.get("insights", []):
        if isinstance(insight, dict):
            refs.update(str(ref) for ref in insight.get("evidence_refs", []) if str(ref) in source_ids)
    with MemoryStore(SQLITE_PATH) as store:
        for ref in sorted(refs):
            store.link_evidence(cycle_id, ref, "supports", weight=0.7)
        return store.promote_from_evidence(cycle_id, min_sources=2, confirm_sources=3)


def choose_research_topic(memory: list[dict]) -> tuple[str, str]:
    previous = [item.get("research", {}).get("topic") for item in memory if isinstance(item, dict)]
    for topic, question in RESEARCH_TOPICS:
        if topic not in previous[-len(RESEARCH_TOPICS):]:
            return topic, question
    index = len(memory) % len(RESEARCH_TOPICS)
    return RESEARCH_TOPICS[index]


def collect_research(topic: str, question: str) -> dict:
    """Consulta fontes públicas e RSS configurados, com limite e degradação segura."""
    query = f"ATENA {topic}: {question}"
    result = {"topic": topic, "question": question, "query": query, "sources": [], "rss_sources": [], "errors": []}
    try:
        result["rss_sources"] = fetch_configured_sources(query, max_sources=4, limit_per_source=5)
    except Exception as exc:
        result["errors"].append(f"RSS {type(exc).__name__}: {exc}")
    if not SOURCE_MODULE_PATH.exists():
        result["errors"].append("módulo de fontes ausente")
        return result
    try:
        spec = importlib.util.spec_from_file_location("atena_sources_extended_runtime", SOURCE_MODULE_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("não foi possível carregar o módulo de fontes")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        fetched = module.fetch_all_relevant(query, max_sources=4, timeout_per=6)
        for item in fetched:
            details = json.dumps(item.details, ensure_ascii=False, sort_keys=True)
            result["sources"].append({
                "source": item.source,
                "category": item.category,
                "ok": bool(item.ok),
                "details": details[:1200],
            })
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def persist_research_sources(research: dict) -> list[str]:
    """Grava fontes bem-sucedidas como episódios independentes e injeta seus IDs."""
    persisted: list[str] = []
    with MemoryStore(SQLITE_PATH) as store:
        for source in research.get("sources", []):
            if not isinstance(source, dict) or not source.get("ok"):
                continue
            source_name = str(source.get("source", "external"))
            output = str(source.get("details", ""))[:4000]
            if not output:
                continue
            episode = build_episode(
                record_type="observation", task_id=f"research:{research.get('topic', 'unknown')}",
                domain=str(source.get("category", "external_research")), output=output,
                source_type="external_source", source_id=f"source:{source_name}",
                source_url=source.get("source_url") or source.get("url"), system_version=SYSTEM_VERSION,
                status="unverified", confidence=0.0,
            )
            ref = store.append(episode)
            source["evidence_ref"] = ref
            persisted.append(ref)
        for feed in research.get("rss_sources", []):
            if not isinstance(feed, dict) or not feed.get("ok"):
                continue
            for item in feed.get("items", []):
                if not isinstance(item, dict):
                    continue
                output = json.dumps({"title": item.get("title"), "summary": item.get("summary"), "published_at": item.get("published_at"), "link": item.get("link")}, ensure_ascii=False, sort_keys=True)
                episode = build_episode(
                    record_type="observation", task_id=f"research:{research.get('topic', 'unknown')}",
                    domain=str(item.get("category", feed.get("category", "rss"))), output=output[:4000],
                    source_type="external_source", source_id=f"rss:{item.get('content_hash') or item.get('link') or feed.get('source')}",
                    source_url=item.get("link") or item.get("source_url"), system_version=SYSTEM_VERSION,
                    status="unverified", confidence=0.0,
                )
                ref = store.append(episode)
                item["evidence_ref"] = ref
                persisted.append(ref)
        store.verify_integrity()
    return persisted


def content_fingerprint(observations: dict) -> str:
    compact = {
        "insights": observations.get("insights", []),
        "risks": observations.get("risks", []),
        "proposed_changes": observations.get("proposed_changes", []),
        "next_cycle": observations.get("next_cycle", []),
    }
    return hashlib.sha256(json.dumps(compact, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def insight_text(item: object) -> str:
    return str(item.get("text", "")) if isinstance(item, dict) else str(item)


def deduplicate_observations(observations: dict, memory: list[dict]) -> dict:
    """Remove repetições literais preservando referências epistemológicas."""
    old_items = []
    old_files = set()
    for cycle in memory[-20:]:
        old = cycle.get("observations", {}) if isinstance(cycle, dict) else {}
        old_items.extend(insight_text(item) for item in old.get("insights", []))
        old_items.extend(old.get("risks", []))
        old_items.extend(old.get("next_cycle", []))
        for change in old.get("proposed_changes", []):
            if isinstance(change, dict) and change.get("file"):
                old_files.add(str(change["file"]).strip().lower())
    old_normalized = {" ".join(str(x).lower().split()) for x in old_items}
    for key in ("insights", "risks", "next_cycle"):
        unique = []
        seen = set()
        for item in observations.get(key, []):
            text = insight_text(item)
            normalized = " ".join(text.lower().split())
            if normalized and normalized not in seen and normalized not in old_normalized:
                unique.append(item)
                seen.add(normalized)
        observations[key] = unique
    unique_changes = []
    seen_files = set()
    for change in observations.get("proposed_changes", []):
        if not isinstance(change, dict):
            continue
        filename = str(change.get("file", "")).strip()
        normalized_file = filename.lower()
        if filename and normalized_file not in old_files and normalized_file not in seen_files:
            unique_changes.append(change)
            seen_files.add(normalized_file)
    observations["proposed_changes"] = unique_changes
    return observations


def ask_local_model(memory: list[dict], research: dict, topic: str, question: str, sqlite_context: str = "") -> dict:
    context = json.dumps(compact_context(memory[-200:], max_items=30), ensure_ascii=False, indent=2)[:9000]
    research_context = json.dumps(research, ensure_ascii=False, indent=2)[:7000]
    sqlite_context = sqlite_context or "(nenhum contexto SQLite recuperado)"
    prompt = f"""Você é o módulo local de análise da ATENA. Faça um ciclo de aprendizagem de no máximo cinco minutos.
Responda SOMENTE com um objeto JSON, sem Markdown, sem comentários, sem códigos ANSI e sem texto antes ou depois.
As chaves obrigatórias são: insights (lista de objetos), risks (lista de strings), proposed_changes
(lista de objetos com file, rationale e tests) e next_cycle (lista de strings). Cada insight DEVE ter exatamente
text (texto), evidence_refs (lista de IDs ou source_ids usados), type (fact, hypothesis, observation ou limitation)
e confidence (número entre 0 e 1). Não escreva código, não peça segredos e não recomende alterações fora de
atena_evolution/proposals. Diferencie fatos de hipóteses.

REGRAS DE DIVERSIDADE:
- Não repita literalmente insights, riscos, propostas ou próximos passos presentes na memória.
- Se a memória for insuficiente, declare essa lacuna, mas formule uma pergunta inédita e verificável.
- Analise o tema deste ciclo: {topic}.
- Responda como a pesquisa deve continuar no próximo ciclo, incluindo fontes, pergunta, evidência esperada e teste de confirmação.
- Não trate resultado de uma única fonte como fato confirmado.
- Toda afirmação factual deve citar pelo menos um evidence_ref existente nos dados coletados ou na memória SQLite.
- Se não houver evidência suficiente, use type=limitation ou type=hypothesis, evidence_refs=[], confidence=0.0 e explique a lacuna.
- Nunca invente IDs, URLs ou fontes; referências ausentes invalidam a promoção.

Pergunta de investigação: {question}
Dados coletados das fontes públicas autorizadas:
{research_context}
Memória recente legada:
{context}

Memória episódica SQLite recuperada por relevância:
{sqlite_context}
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
    intent = None
    try:
        with MemoryStore(SQLITE_PATH) as store:
            intent = store.claim_next_research()
    except Exception as exc:
        print(f"fila de pesquisa indisponível: {exc}", file=sys.stderr)
    if intent:
        topic = str(intent["topic"])
        question = str(intent.get("question") or f"Pesquisar fontes e evidências sobre {topic}.")
    else:
        topic, question = choose_research_topic(memory)
    research = collect_research(topic, question)
    research["requested_by"] = "telegram" if intent else "rotation"
    research["intent_id"] = intent.get("id") if intent else None
    source_episode_ids: set[str] = set()
    try:
        source_episode_ids = set(persist_research_sources(research))
    except Exception as exc:
        print(f"persistência de fontes falhou: {exc}", file=sys.stderr)
    sqlite_context = ""
    try:
        sqlite_context = format_context(retrieve_context(SQLITE_PATH, f"{topic} {question}", limit=12))
    except Exception as exc:
        print(f"recuperação SQLite indisponível: {exc}", file=sys.stderr)
    observations = ask_local_model(memory, research, topic, question, sqlite_context)
    observations = deduplicate_observations(observations, memory)
    if not any(observations.get(key) for key in ("insights", "risks", "proposed_changes", "next_cycle")):
        observations["insights"] = [{
            "text": f"Nenhuma conclusão nova foi confirmada sobre {topic}; a lacuna de evidência será investigada antes de consolidar uma memória.",
            "evidence_refs": [], "type": "limitation", "confidence": 0.0,
        }]
    observations["research_plan"] = {
        "topic": topic,
        "question": question,
        "sources_to_consult": [item["source"] for item in research.get("sources", []) if item.get("ok")],
        "evidence_expected": "comparar pelo menos duas evidências independentes antes de consolidar um fato",
        "next_test": f"verificar uma instância inédita relacionada a {topic}",
        "retrieval": {"source": "sqlite", "episode_limit": 12, "context_chars": len(sqlite_context)},
    }
    cycle = {
        "timestamp": now.isoformat(),
        "model": MODEL,
        "duration_limit_seconds": 300,
        "research": research,
        "observations": observations,
    }
    memory.append(cycle)
    # Compatibilidade: o JSON legado continua sendo escrito primeiro.
    MEMORY_PATH.write_text(json.dumps(memory[-200:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proposal_path = PROPOSALS_DIR / f"cycle-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    proposal_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sqlite_status = "ok"
    sqlite_memory_id = None
    promoted_status = "unverified"
    try:
        sqlite_memory_id = write_sqlite_cycle(cycle)
        if sqlite_memory_id and source_episode_ids:
            promoted_status = link_cycle_evidence(sqlite_memory_id, observations, source_episode_ids)
        if intent:
            with MemoryStore(SQLITE_PATH) as store:
                store.complete_research(intent["id"], cycle["timestamp"], {"topic": topic, "sqlite_memory_id": sqlite_memory_id, "promoted_status": promoted_status, "source_episode_count": len(source_episode_ids), "status": "completed"})
    except Exception as exc:
        sqlite_status = f"error:{type(exc).__name__}"
        print(f"SQLite dual-write falhou: {exc}", file=sys.stderr)
        if intent:
            try:
                with MemoryStore(SQLITE_PATH) as store:
                    store.complete_research(intent["id"], cycle["timestamp"], {"topic": topic, "error": str(exc)}, failed=True)
            except Exception:
                pass
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
        "source_episode_count": len(source_episode_ids),
        "promoted_status": promoted_status,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
