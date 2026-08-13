from scripts.daily_news_digest import NewsItem, format_digest


def test_format_digest_has_categories_links_and_disclaimer():
    message = format_digest(
        [NewsItem("Futebol", "Santos vence", "https://example.com/santos", "Fonte")],
        [],
        include_x=True,
    )
    assert "ATENA — principais notícias do dia" in message
    assert "<b>Futebol</b>" in message
    assert "https://example.com/santos" in message
    assert "fonte original" in message


def test_format_digest_reports_unavailable_sources():
    message = format_digest([], ["Fonte: Timeout"], include_x=False)
    assert "Fontes indisponíveis neste ciclo: 1" in message
