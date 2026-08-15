from scripts.notify_telegram_learning import build_message, source_label


def test_source_label_uses_editorial_name():
    assert source_label("https://olhardigital.com.br/2026/08/15/ciencia-e-espaco/teste/") == "Olhar Digital"
    assert source_label("https://agenciabrasil.ebc.com.br/rss.xml") == "Agência Brasil"
    assert source_label("https://www.gazetaesportiva.com/times/santos/teste/") == "Gazeta Esportiva"
    assert source_label("https://example.org/news") == "example.org"


def test_source_label_internal_reference_is_not_called_source_1():
    assert source_label("mem-20260815102124-abc") == "Referência interna"
    assert source_label("") == "Fonte não identificada"


def test_build_message_shows_real_source_name_and_keeps_link():
    url = "https://olhardigital.com.br/2026/08/15/ciencia-e-espaco/teste/"
    proposal = {
        "model": "qwen2.5:3b-instruct",
        "provider": "local",
        "timestamp": "2026-08-15T10:21:24Z",
        "observations": {
            "insights": [{
                "text": "Resumo de ciência",
                "type": "news_summary",
                "confidence": 0.9,
                "evidence_refs": [url],
            }],
            "risks": [],
            "proposed_changes": [],
            "next_cycle": [],
            "research_plan": {"topic": "fontes externas"},
        },
        "research": {},
    }
    message = build_message(proposal, None)
    assert "Olhar Digital" in message
    assert url in message
    assert "Fonte 1" not in message
