"""Recuperação lexical e epistemológica de episódios SQLite para os ciclos da Atena."""
from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Any
from core.memory_store import MemoryStore

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]{3,}", re.UNICODE)
_STOP = {"para", "com", "sem", "sobre", "como", "uma", "que", "dos", "das", "por", "não", "na", "no", "nos", "nas"}

def _tokens(text: str) -> set[str]:
    return {t.casefold() for t in _TOKEN_RE.findall(text) if t.casefold() not in _STOP}

def _episode_text(record: dict[str, Any]) -> str:
    event = record.get("event", {})
    output = event.get("output", "") if isinstance(event, dict) else ""
    return " ".join([str(record.get("subject", {}).get("domain", "")), str(record.get("subject", {}).get("task_id", "")), str(output)])

def retrieve_context(db_path: str | Path, query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Retorna episódios relevantes sem modificar a memória append-only."""
    wanted = _tokens(query)
    if not wanted:
        return []
    with MemoryStore(db_path) as store:
        rows = store.connection.execute(
            "SELECT id, record_json, created_at, status, confidence, lifecycle_state FROM episodes "
            "WHERE lifecycle_state NOT IN ('superseded','expired') ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
        scored = []
        for row in rows:
            record = json.loads(row[1]); tokens = _tokens(_episode_text(record)); overlap = len(wanted & tokens)
            if overlap == 0: continue
            score = overlap / math.sqrt(max(1, len(wanted) * len(tokens)))
            item = {"episode_id": row[0], "created_at": row[2], "status": row[3], "confidence": row[4], "score": round(score, 5), "record": record}
            try: item["evidence"] = store.evidence_summary(row[0])
            except Exception: item["evidence"] = {"status": "unverified"}
            scored.append(item)
        scored.sort(key=lambda x: (x["score"], x["created_at"]), reverse=True)
        return scored[:max(1, min(int(limit), 50))]

def format_context(items: list[dict[str, Any]], max_chars: int = 9000) -> str:
    """Formata contexto com IDs, status e evidência para o prompt do modelo."""
    chunks=[]; used=0
    for item in items:
        record=item["record"]; output=record.get("event", {}).get("output", "")
        chunk = json.dumps({"episode_id": item["episode_id"], "created_at": item["created_at"], "status": item["status"], "confidence": item["confidence"], "evidence": item.get("evidence", {}), "output": output[:1800]}, ensure_ascii=False)
        if used + len(chunk) > max_chars: break
        chunks.append(chunk); used += len(chunk)
    return "\n".join(chunks) if chunks else "(nenhum episódio SQLite relevante recuperado)"
