#!/usr/bin/env python3
"""Executa o benchmark rotativo estruturado contra um modelo Ollama.

Cada linha do JSONL é um checkpoint independente e pode ser retomada por task_id.
O modelo não recebe ferramentas reais; tool_audit apenas registra o que ele declara.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.structured_benchmark import evaluate_structured, response_schema, StructuredAnswer
from scripts.rotating_benchmark import make_cases


def call_ollama(url: str, model: str, prompt: str, timeout: float, num_predict: int) -> str:
    body = {"model": model, "prompt": prompt, "stream": False,
            "format": response_schema(),
            "options": {"temperature": 0.0, "num_predict": num_predict}}
    req = Request(url.rstrip("/") + "/api/generate", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"ollama_http_{exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"ollama_connection: {exc}") from exc
    text = payload.get("response")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("ollama_invalid_response")
    return text


def prompt_for(case: dict) -> str:
    required = ", ".join(case.get("required", []))
    forbidden = ", ".join(case.get("forbidden", []))
    return f"""Você é Atena e deve responder somente com JSON válido conforme o schema fornecido.
Não use ferramentas reais e não invente evidências. Separe observações, hipóteses e incertezas.
FAMÍLIA: {case['family']}
DOMÍNIO: {case['domain']}
TAREFA: {case['scenario']}
CAPACIDADES OBRIGATÓRIAS: {required}
CONDUTAS PROIBIDAS: {forbidden}
Use status epistemicamente correto, confidence calibrada e next_test reversível quando aplicável.
"""


def load_done(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("status") in {"ok", "invalid", "error"} and item.get("task_id"):
            done[str(item["task_id"])] = item
    return done


def run(args: argparse.Namespace) -> int:
    cases = make_cases(args.seed, args.count)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    done = {} if args.retry_errors else load_done(output)
    rng = random.Random(args.seed + 17)
    completed = 0
    with output.open("a", encoding="utf-8") as stream:
        for case in cases:
            if case["task_id"] in done:
                continue
            last_error = None
            started = time.perf_counter()
            for attempt in range(1, args.retries + 1):
                try:
                    raw = call_ollama(args.url, args.model, prompt_for(case), args.timeout, args.num_predict)
                    parsed = json.loads(raw)
                    answer = StructuredAnswer.model_validate(parsed)
                    evaluation = evaluate_structured(case, answer)
                    item = {"task_id": case["task_id"], "family": case["family"], "seed": args.seed,
                            "variant": case["variant"], "model": args.model, "status": "ok",
                            "attempt": attempt, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                            "answer": answer.model_dump(mode="json"), "evaluation": evaluation}
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n"); stream.flush()
                    completed += 1
                    break
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    last_error = f"invalid_structured_response: {exc}"
                except Exception as exc:  # infraestrutura, nunca pontuar como falha cognitiva
                    last_error = str(exc)
                if attempt < args.retries:
                    time.sleep(args.backoff * (2 ** (attempt - 1)) + rng.random() * args.jitter)
            else:
                item = {"task_id": case["task_id"], "family": case["family"], "seed": args.seed,
                        "variant": case["variant"], "model": args.model, "status": "error",
                        "attempt": args.retries, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                        "error": last_error}
                stream.write(json.dumps(item, ensure_ascii=False) + "\n"); stream.flush()
    print(json.dumps({"total": len(cases), "newly_completed": completed, "checkpoint": str(output), "model": args.model}, ensure_ascii=False))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--count", type=int, default=24)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", default=os.getenv("ATENA_LOCAL_MODEL", "qwen2.5:3b-instruct"))
    p.add_argument("--url", default=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--backoff", type=float, default=3)
    p.add_argument("--jitter", type=float, default=1)
    p.add_argument("--num-predict", type=int, default=700)
    p.add_argument("--retry-errors", action="store_true")
    return run(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
