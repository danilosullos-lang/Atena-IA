from __future__ import annotations

from core.web_research import WebEvidence, build_context
from scripts.atena_telegram_chat import AtenaTelegramChat


def test_current_question_router_detects_santos_palmeiras() -> None:
    assert AtenaTelegramChat.needs_current_web("Que dia o Santos vai jogar contra o Palmeiras?")
    assert AtenaTelegramChat.needs_current_web("Qual é o preço atual do jogo?")
    assert not AtenaTelegramChat.needs_current_web("Explique o que é memória episódica")


def test_web_context_preserves_sources() -> None:
    context = build_context(
        "jogo Santos Palmeiras",
        [WebEvidence("Calendário oficial", "https://example.com/calendar", "Jogo em 26 de agosto")],
    )
    assert "https://example.com/calendar" in context
    assert "Jogo em 26 de agosto" in context
