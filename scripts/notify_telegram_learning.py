#!/usr/bin/env python3
"""Envia um resumo seguro de uma nova aprendizagem via Telegram Bot API."""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def clip(value: str, limit: int = 700) -> str:
    value = " ".join(value.replace("\n", " ").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _safe_url(value: object) -> str | None:
    url = str(value or "").strip()
    return url if url.startswith(("https://", "http://")) else None


def _format_insight(item: object, index: int) -> tuple[str, list[str]]:
    if not isinstance(item, dict):
        return f"• {html.escape(clip(str(item)))}", []
    text = clip(str(item.get("text", "limitação sem descrição")), 900)
    kind = html.escape(str(item.get("type", "insight")))
    try:
        confidence = float(item.get("confidence", 0.0))
        confidence_text = f"{confidence:.2f}"
    except (TypeError, ValueError):
        confidence_text = "0.00"
    refs = [_safe_url(ref) for ref in item.get("evidence_refs", []) or []]
    refs = list(dict.fromkeys(ref for ref in refs if ref))
    lines = [
        f"<b>{index}. {html.escape(kind)}</b> · confiança: <code>{confidence_text}</code>",
        html.escape(text),
    ]
    for ref_index, ref in enumerate(refs[:5], 1):
        lines.append(f"<a href=\"{html.escape(ref, quote=True)}\">Fonte {ref_index}</a>")
    return "\n".join(f"• {line}" if line == lines[0] else f"  {line}" for line in lines), refs


def build_message(proposal: dict, run_url: str | None) -> str:
    observations = proposal.get("observations", {})
    insights = observations.get("insights", [])
    risks = observations.get("risks", [])
    changes = observations.get("proposed_changes", [])
    next_cycle = observations.get("next_cycle", [])
    research_plan = observations.get("research_plan", {})
    research = proposal.get("research", {})
    model = html.escape(str(proposal.get("model", "modelo local")))
    requested_by = research.get("requested_by", "rotation")
    timestamp = html.escape(str(proposal.get("timestamp", "agora")))
    lines = [
        "<b>ATENA — nova aprendizagem</b>",
        f"Modelo: <code>{model}</code>",
        f"Ciclo: <code>{timestamp}</code>",
        "",
        "<b>Insights</b>",
    ]
    all_refs: list[str] = []
    for index, item in enumerate(insights[:5], 1):
        formatted, refs = _format_insight(item, index)
        lines.append(formatted)
        all_refs.extend(refs)
    all_refs = list(dict.fromkeys(all_refs))
    lines.append("\n<b>Riscos</b>")
    lines.extend(f"• {html.escape(clip(str(item)))}" for item in risks[:5])
    lines.append("\n<b>Propostas geradas</b>")
    for change in changes[:5]:
        if isinstance(change, dict):
            lines.append(f"• <code>{html.escape(clip(str(change.get('file', 'arquivo desconhecido')), 180))}</code>")
    lines.append("\n<b>Próximo ciclo</b>")
    lines.extend(f"• {html.escape(clip(str(item)))}" for item in next_cycle[:3])
    lines.append("\n<b>Pesquisa realizada</b>")
    lines.append(f"• Origem: {html.escape(str(requested_by))}")
    if research_plan.get("topic"):
        lines.append(f"• Tema: {html.escape(clip(str(research_plan['topic']), 180))}")
    consulted = research_plan.get("sources_to_consult", []) or [item.get("source") for item in research.get("sources", []) if item.get("ok")]
    rss_consulted = [item.get("source") for item in research.get("rss_sources", []) if item.get("ok")]
    consulted = list(dict.fromkeys([*consulted, *rss_consulted]))
    if consulted:
        lines.append(f"• Fontes consultadas: {html.escape(clip(', '.join(map(str, consulted)), 300))}")
    if all_refs:
        lines.append("\n<b>Referências dos insights</b>")
        for index, ref in enumerate(all_refs[:10], 1):
            lines.append(f"{index}. <a href=\"{html.escape(ref, quote=True)}\">{html.escape(clip(ref, 180))}</a>")
    if research_plan.get("question"):
        lines.append(f"• Pergunta: {html.escape(clip(str(research_plan['question']), 360))}")
    if research_plan.get("next_test"):
        lines.append(f"• Próximo teste: {html.escape(clip(str(research_plan['next_test']), 360))}")
    if run_url:
        lines.append(f"\n<a href=\"{html.escape(run_url, quote=True)}\">Ver execução no GitHub Actions</a>")
    return "\n".join(lines)[:3900]


def send(token: str, chat_id: str, message: str, timeout: int = 15) -> None:
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError("Telegram recusou a mensagem")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--run-url", default=os.getenv("GITHUB_SERVER_URL", "") + "/" + os.getenv("GITHUB_REPOSITORY", "") + "/actions/runs/" + os.getenv("GITHUB_RUN_ID", ""))
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    token = os.getenv("ATENA_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("ATENA_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        message = "Telegram não configurado: defina ATENA_TELEGRAM_BOT_TOKEN e ATENA_TELEGRAM_CHAT_ID."
        if args.allow_missing:
            print(f"::warning::{message}")
            return 0
        print(f"::error::{message}")
        return 2

    try:
        proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
        message = build_message(proposal, args.run_url or None)
        send(token, chat_id, message)
    except Exception as exc:
        print(f"::error::Falha ao enviar notificação Telegram: {type(exc).__name__}: {exc}")
        return 1
    print("Notificação Telegram enviada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
