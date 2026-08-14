#!/usr/bin/env python3
"""Gera um briefing diário de notícias, sem escrever na memória autônoma."""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
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
    summary: str = ""


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

SOURCE_WEIGHT = {
    "Agência Brasil": 1.00,
    "BBC Brasil": 0.98,
    "MIT Technology Review": 0.96,
    "ge": 0.92,
    "Tecnoblog": 0.88,
    "Canaltech": 0.86,
    "X": 0.55,
}


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    raw = " ".join("".join(element.itertext()).split())
    return re.sub(r"<[^>]+>", " ", html.unescape(raw)).strip()


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", text.lower()) if len(x) > 2}


def _published_score(value: str) -> float:
    if not value:
        return 0.0
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        age_hours = max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed.astimezone(dt.timezone.utc)).total_seconds() / 3600)
        return max(0.0, 1.0 - min(age_hours, 72.0) / 72.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _clean_summary(value: str, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", html.unescape(value or "")).strip()
    return value[:limit].rstrip(" .") + ("…" if len(value) > limit else "")


def fetch_feed(category: str, source: str, url: str, timeout: int = 18) -> list[NewsItem]:
    response = requests.get(url, headers={"User-Agent": "Atena-IA daily briefing/2.0"}, timeout=timeout)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    nodes = list(root.findall(".//item")) or list(root.findall(".//{*}entry"))
    items: list[NewsItem] = []
    for node in nodes[:30]:
        title = _text(node.find("title"))
        link = _text(node.find("link"))
        if not link:
            link_node = node.find("{*}link")
            link = str(link_node.attrib.get("href", "")) if link_node is not None else ""
        published = _text(node.find("pubDate")) or _text(node.find("{*}published")) or _text(node.find("{*}updated"))
        summary = _text(node.find("description")) or _text(node.find("{*}summary")) or _text(node.find("{*}content"))
        if title and link.startswith(("http://", "https://")):
            items.append(NewsItem(category, title, link, source, published, _clean_summary(summary)))
    return items


def _deduplicate(items: Iterable[NewsItem]) -> list[NewsItem]:
    result: list[NewsItem] = []
    for item in items:
        title_tokens = _tokens(item.title)
        duplicate = False
        for previous in result:
            if item.url == previous.url:
                duplicate = True
                break
            similarity = SequenceMatcher(None, item.title.lower(), previous.title.lower()).ratio()
            overlap = len(title_tokens & _tokens(previous.title)) / max(1, len(title_tokens | _tokens(previous.title)))
            if similarity >= 0.82 or overlap >= 0.72:
                duplicate = True
                break
        if not duplicate:
            result.append(item)
    return result


def _rank(item: NewsItem, query_terms: set[str] | None = None) -> float:
    terms = query_terms or set()
    relevance = len(_tokens(item.title) & terms) / max(1, len(terms)) if terms else 0.5
    source = SOURCE_WEIGHT.get(item.source, 0.70)
    freshness = _published_score(item.published)
    substance = min(1.0, len(item.summary) / 220.0)
    return 0.42 * freshness + 0.28 * source + 0.20 * relevance + 0.10 * substance


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
        category_items = _deduplicate(category_items)
        category_items.sort(key=lambda item: _rank(item), reverse=True)
        all_items.extend(category_items[: max(1, min(limit_per_category, 8))])
    return all_items, errors


def collect_x(query: str = "(futebol OR política OR jogos OR tecnologia) lang:pt", limit: int = 10) -> list[NewsItem]:
    try:
        posts = XNewsResearch().search(query, limit)
    except XNotConfigured:
        return []

    def score(post) -> int:
        metrics = post.public_metrics or {}
        return int(metrics.get("like_count", 0)) + 2 * int(metrics.get("retweet_count", 0)) + int(metrics.get("reply_count", 0))

    return [
        NewsItem("Em alta no X", " ".join(post.text.split())[:220], post.url, "X", post.created_at or "", "Sinal de interesse público; confirme na fonte original.")
        for post in sorted(posts, key=score, reverse=True)[:limit]
    ]


def _why_it_matters(category: str) -> str:
    return {
        "Futebol": "impacto esportivo",
        "Jogos e tecnologia": "produto, mercado ou tecnologia",
        "Política e Brasil": "impacto público no Brasil",
        "Mundo": "repercussão internacional",
        "Ciência e IA": "avanço científico ou tecnológico",
        "Em alta no X": "sinal de interesse; requer confirmação",
    }.get(category, "relevância geral")


def format_digest(items: Iterable[NewsItem], errors: list[str], *, include_x: bool, max_items_per_category: int = 3) -> str:
    now = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-3)))
    grouped: dict[str, list[NewsItem]] = {}
    for item in _deduplicate(items):
        grouped.setdefault(item.category, []).append(item)
    for category in grouped:
        grouped[category] = sorted(grouped[category], key=lambda item: _rank(item), reverse=True)[:max_items_per_category]

    lines = [
        "ATENA — principais notícias do dia | briefing essencial",
        f"Atualizado: {now.strftime('%d/%m/%Y às %H:%M')} (horário de Brasília)",
        "",
        "Critérios: novidade, relevância, confiabilidade da fonte e deduplicação.",
        "Resumo informativo; notícias importantes devem ser confirmadas na fonte original.",
        "",
    ]
    for category, category_items in grouped.items():
        lines.append(f"<b>{html.escape(category)}</b>")
        for item in category_items:
            title = html.escape(item.title[:210])
            source = html.escape(item.source)
            lines.append(f"• <a href=\"{html.escape(item.url, quote=True)}\">{title}</a> — {source}")
            if item.summary:
                lines.append(f"  <i>{html.escape(item.summary[:230])}</i>")
            lines.append(f"  <u>Por que importa:</u> {html.escape(_why_it_matters(category))}.")
        lines.append("")
    if include_x and not grouped.get("Em alta no X"):
        lines.extend(["<b>Em alta no X</b>", "Nenhum resultado disponível; o token pode não estar configurado.", ""])
    if errors:
        lines.extend([f"Fontes indisponíveis neste ciclo: {len(errors)}; serão tentadas novamente.", ""])
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
    parser.add_argument("--items-per-category", type=int, default=3)
    args = parser.parse_args()
    items, errors = collect_rss(limit_per_category=max(1, min(args.items_per_category, 8)))
    if args.include_x:
        items.extend(collect_x())
    message = format_digest(items, errors, include_x=args.include_x, max_items_per_category=args.items_per_category)
    if args.dry_run:
        print(message)
    else:
        send_telegram(message)
        print(f"Briefing diário enviado com {len(items)} itens e {len(errors)} erros de fonte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
