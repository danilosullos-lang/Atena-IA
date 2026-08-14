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


from xml.etree import ElementTree as ET

from scripts.daily_news_digest import _rss_image_url, resolve_image_url


def test_rss_image_url_extracts_media_content():
    node = ET.fromstring(
        '<item xmlns:media="http://search.yahoo.com/mrss/"><media:content url="https://img.example/news.jpg" type="image/jpeg" /></item>'
    )
    assert _rss_image_url(node, "https://example.com/news") == "https://img.example/news.jpg"


def test_resolve_image_url_rejects_non_http_image():
    item = NewsItem("Mundo", "Notícia", "https://example.com/news", "Fonte", image_url="file:///tmp/image.jpg")
    assert resolve_image_url(item, allow_open_graph=False) == ""


def test_santos_section_and_caption_are_personalized():
    from scripts.daily_news_digest import _caption, collect_santos

    source = NewsItem(
        "Futebol",
        "Santos vence na Vila Belmiro",
        "https://ge.example/santos",
        "ge",
        summary="O Peixe venceu e avançou.",
    )
    selected = collect_santos([source], limit=3)
    assert selected[0].category == "Santos FC"
    assert "torcida santista" in _caption(selected[0])
