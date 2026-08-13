"""Pesquisa web pública e controlada para perguntas factuais atuais.

O módulo não executa instruções encontradas nas páginas. Ele apenas coleta
metadados e pequenos trechos para dar contexto ao modelo local, sempre
preservando as URLs consultadas como evidência.
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("atena.web_research")
SEARCH_URLS = (
    "https://www.bing.com/search?format=rss&q={query}",
    "https://html.duckduckgo.com/html/?q={query}",
)
USER_AGENT = "Atena-IA factual research/1.0"
ALLOWED_SCHEMES = {"http", "https"}


@dataclass(frozen=True)
class WebEvidence:
    title: str
    url: str
    snippet: str


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.netloc)


def search_web(query: str, limit: int = 5, timeout: int = 20) -> list[WebEvidence]:
    """Consulta resultados públicos sem executar JavaScript ou conteúdo remoto."""
    query = " ".join(query.split())[:300]
    if not query:
        return []
    response = None
    last_error: Exception | None = None
    for template in SEARCH_URLS:
        try:
            candidate = requests.get(
                template.format(query=quote_plus(query)),
                headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7"},
                timeout=timeout,
            )
            candidate.raise_for_status()
            response = candidate
            break
        except requests.RequestException as exc:
            last_error = exc
            LOG.warning("fonte de busca indisponível: %s", template.split("/", 3)[2])
    if response is None:
        raise RuntimeError(f"nenhuma fonte de busca web respondeu: {last_error}")

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[WebEvidence] = []
    rss_items = soup.select("item")
    if rss_items:
        for item in rss_items[: max(1, min(limit, 10))]:
            title = item.select_one("title")
            link = item.select_one("link")
            description = item.select_one("description")
            url = html.unescape(link.get_text(strip=True) if link else "")
            if not _valid_url(url):
                continue
            results.append(WebEvidence(
                title=re.sub(r"\\s+", " ", title.get_text(" ", strip=True) if title else "")[:240],
                url=url,
                snippet=re.sub(r"\\s+", " ", description.get_text(" ", strip=True) if description else "")[:700],
            ))
        return results
    seen: set[str] = set()
    for card in soup.select(".result"):
        anchor = card.select_one("a.result__a[href]")
        if not anchor:
            continue
        url = html.unescape(anchor.get("href", "")).strip()
        if not _valid_url(url) or url in seen:
            continue
        title = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
        snippet_node = card.select_one(".result__snippet")
        snippet = re.sub(r"\s+", " ", snippet_node.get_text(" ", strip=True) if snippet_node else "")
        results.append(WebEvidence(title=title[:240], url=url, snippet=snippet[:700]))
        seen.add(url)
        if len(results) >= max(1, min(limit, 10)):
            break
    if results:
        return results
    return _sports_fallback(query, timeout=timeout)


def _sports_fallback(query: str, timeout: int = 20) -> list[WebEvidence]:
    """Consulta o placar/calendário público da ESPN para perguntas esportivas."""
    lowered = query.casefold()
    teams = ("santos", "palmeiras", "corinthians", "são paulo", "flamengo")
    if not any(team in lowered for team in teams):
        return []
    start = date.today().strftime("%Y%m%d")
    end = (date.today() + timedelta(days=90)).strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/bra.1/scoreboard?limit=500&dates={start}-{end}"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        LOG.warning("fallback esportivo indisponível: %s", exc)
        return []
    results: list[WebEvidence] = []
    for event in data.get("events", []):
        text = str(event)
        if not any(team in text.casefold() for team in teams):
            continue
        competitions = event.get("competitions", [])
        competition = competitions[0] if competitions else {}
        competitors = competition.get("competitors", [])
        names = [item.get("team", {}).get("displayName", "") for item in competitors]
        event_date = event.get("date", "")
        title = " x ".join(name for name in names if name) or event.get("name", "Jogo")
        results.append(WebEvidence(
            title=f"{title} — calendário esportivo",
            url=url,
            snippet=f"Data/hora publicada pela fonte esportiva: {event_date}. Competição: {competition.get('league', {}).get('name', 'futebol brasileiro')}.",
        ))
    return results[:10]


def build_context(query: str, evidence: list[WebEvidence]) -> str:
    if not evidence:
        return "Nenhuma fonte pública foi encontrada; não invente uma resposta atual."
    lines = [
        "Você recebeu fontes públicas para responder uma pergunta atual.",
        "Use somente o que estiver sustentado pelos trechos abaixo, informe a data de consulta e inclua as URLs como fontes.",
        "Se as fontes divergirem ou não confirmarem a data, diga isso claramente.",
        f"Pergunta pesquisada: {query}",
        "",
    ]
    for index, item in enumerate(evidence, 1):
        lines.extend([f"Fonte {index}: {item.title}", f"URL: {item.url}", f"Trecho: {item.snippet}", ""])
    return "\n".join(lines)
