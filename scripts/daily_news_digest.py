"""Resumo diário de notícias para o Telegram da Atena.

Executa uma vez por dia, sem alterar a memória autônoma. Usa RSS público por
categoria e, opcionalmente, a API oficial do X para sinais de assuntos em alta.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

import requests

from core.x_news_research import XNewsResearch, XNotConfigured


@dataclass(frozen=True)
class NewsItem:
    category: str
    title: str
    url: str
    source: str
    published: str = ""


FEEDS: dict[str, list[tuple[str, str]]] = {
    "Futebol": [
        ("ge", "https://ge.globo.com/rss/ge/"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/esportes/feed.xml"),
    ],
    "Jogos e tecnologia": [
        ("Tecnoblog", "https://tecnoblog.net/feed/"),
        ("Canaltech", "https://canaltech.com.br/rss/"),
    ],
    "Política e Brasil": [
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"),
        ("BBC Brasil", "https://feeds.bbci.co.uk/portuguese/rss.xml"),
    ],
    "Mundo": [
        ("BBC Brasil", "https://feeds.bbci.co.uk/portuguese/rss.xml"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"),
    ],
    "Ciência e IA": [
        ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ciencia-e-tecnologia/feed.xml"),
    ],
}


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def fetch_feed(category: str, source: str, url: str, timeout: int = 18) -> list[NewsItem]:
    response = requests.get(url, headers={"User-Agent": "Atena-IA daily news/1.0"}, timeout=timeout)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[NewsItem] = []
    nodes = list(root.findall(".//item")) or list(root.findall(".//{*}entry"))
    for node in nodes[:20]:
        title = _text(node.find("title"))
        link = _text(node.find("link"))
        if not link:
            link_node = node.find("{*}link")
            link = str(link_node.attrib.get("href", "")) if link_node is not None else ""
        published = _text(node.find("pubDate")) or _text(node.find("{*}published")) or _text(node.find("{*}updated"))
        if title and link.startswith(("http://", "https://")):
            items.append(NewsItem(category, title, link, source, published))
    return items


def collect_rss(limit_per_category: int = 4) -> tuple[list[NewsItem], list[str]]:
    all_items: list[NewsItem] = []
    errors: list[str] = []
    for category, sources in FEEDS.items():
        category_items: list[NewsItem] = []
        for source, url in sources:
            try:
                category_items.extend(fetch_feed(category, source, url))
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}")
        seen: set[str] = set()
        for item in category_items:
            key = re.sub(r"\W+", " ", item.title.lower()).strip()
            if key in seen:
                continue
            seen.add(key)
            all_items.append(item)
            if len([x for x in all_items if x.category == category]) >= limit_per_category:
                break
    return all_items, errors


def collect_x(query: str = "(futebol OR política OR jogos OR tecnologia) lang:pt", limit: int = 10) -> list[NewsItem]:
    try:
        posts = XNewsResearch().search(query, limit)
    except XNotConfigured:
        return []
    return [NewsItem("Em alta no X", " ".join(post.text.split())[:220], post.url, "X", post.created_at or "") for post in posts]


def format_digest(items: Iterable[NewsItem], errors: list[str], *, include_x: bool) -> str:
    now = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-3)))
    lines = [
        "ATENA — principais notícias do dia",
        f"Atualizado: {now.strftime('%d/%m/%Y às %H:%M')} (horário de Brasília)",
        "",
        "Fontes: RSS públicos e, quando configurado, API oficial do X.",
        "",
    ]
    grouped: dict[str, list[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    for category, category_items in grouped.items():
        lines.append(f"<b>{html.escape(category)}</b>")
        for item in category_items:
            lines.append(f"• {html.escape(item.title[:220])} — <a href=\"{html.escape(item.url, quote=True)}\">{html.escape(item.source)}</a>")
        lines.append("")
    if include_x and not grouped.get("Em alta no X"):
        lines.extend(["<b>Em alta no X</b>", "Nenhum resultado do X disponível; o token pode não estar configurado.", ""])
    if errors:
        lines.extend([f"Fontes indisponíveis neste ciclo: {len(errors)}. Elas serão tentadas novamente amanhã.", ""])
    lines.append("Este resumo é informativo; notícias importantes devem ser confirmadas na fonte original.")
    return "\n".join(lines)[:3900]


def send_telegram(message: str) -> None:
    token = os.getenv("ATENA_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("ATENA_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("ATENA_TELEGRAM_BOT_TOKEN e ATENA_TELEGRAM_CHAT_ID são obrigatórios")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-x", action="store_true")
    args = parser.parse_args()
    items, errors = collect_rss()
    if args.include_x:
        items.extend(collect_x())
    message = format_digest(items, errors, include_x=args.include_x)
    if args.dry_run:
        print(message)
    else:
        send_telegram(message)
        print(f"Resumo diário enviado com {len(items)} itens e {len(errors)} erros de fonte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
