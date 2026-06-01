#!/usr/bin/env python3
"""Escaneia GitHub por repositórios de IA com muitas estrelas e gera snapshot local."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

API_URL = "https://api.github.com/search/repositories"
DEFAULT_QUERIES = [
    "topic:artificial-intelligence stars:>5000 archived:false",
    "topic:machine-learning stars:>5000 archived:false",
    '"llm" stars:>3000 archived:false',
]
WATCHLIST_PATH = Path("docs/ai_repo_watchlist.json")
ABSORPTION_REPORT_PATH = Path("analysis_reports/EXECUCAO_GITHUB_TOP_STARS_ABSORPTION_2026-06-01.md")


@dataclass
class RepoSnapshot:
    full_name: str
    html_url: str
    description: str
    stargazers_count: int
    language: str | None
    updated_at: str


def _github_request(url: str) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "atena-ai-repo-scanner",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_repos(query: str, per_page: int = 20) -> List[RepoSnapshot]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(per_page),
            "page": "1",
        }
    )
    payload = _github_request(f"{API_URL}?{params}")
    items = payload.get("items", [])
    return [
        RepoSnapshot(
            full_name=item.get("full_name", ""),
            html_url=item.get("html_url", ""),
            description=(item.get("description") or "").strip(),
            stargazers_count=int(item.get("stargazers_count", 0)),
            language=item.get("language"),
            updated_at=item.get("updated_at", ""),
        )
        for item in items
    ]


def dedupe_rank(repos: List[RepoSnapshot], top_n: int = 50) -> List[RepoSnapshot]:
    by_name: dict[str, RepoSnapshot] = {}
    for repo in repos:
        prev = by_name.get(repo.full_name)
        if not prev or repo.stargazers_count > prev.stargazers_count:
            by_name[repo.full_name] = repo
    return sorted(by_name.values(), key=lambda r: r.stargazers_count, reverse=True)[:top_n]


def _repo_from_dict(item: dict) -> RepoSnapshot:
    return RepoSnapshot(
        full_name=str(item.get("full_name", "")),
        html_url=str(item.get("html_url", "")),
        description=str(item.get("description") or "").strip(),
        stargazers_count=int(item.get("stargazers_count", 0)),
        language=item.get("language"),
        updated_at=str(item.get("updated_at", "")),
    )


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[RepoSnapshot]:
    """Load the latest local watchlist for offline/proxy-limited absorption tests."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    repos = payload.get("repos", [])
    if not isinstance(repos, list):
        return []
    return [_repo_from_dict(item) for item in repos if isinstance(item, dict)]


def _language_distribution(repos: Iterable[RepoSnapshot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for repo in repos:
        language = repo.language or "Unknown"
        counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def infer_absorption_patterns(repos: list[RepoSnapshot]) -> list[str]:
    """Extract practical patterns Atena can absorb from high-star AI repositories."""
    text = "\n".join(f"{repo.full_name} {repo.description}".lower() for repo in repos)
    patterns: list[str] = []
    if any(term in text for term in ("framework", "langchain", "dify", "flowise")):
        patterns.append("Arquitetura modular e pluginável para compor agentes, ferramentas e fluxos.")
    if any(term in text for term in ("llm", "transformers", "llama", "ollama", "gpt")):
        patterns.append("Camada multi-modelo/LLM com provedores intercambiáveis e fallback local.")
    if any(term in text for term in ("rag", "retrieval", "open-webui", "document")):
        patterns.append("RAG, indexação e memória operacional como base de conhecimento persistente.")
    if any(term in text for term in ("agent", "autogpt", "openhands", "browser-use")):
        patterns.append("Agentes com uso de ferramentas, navegador, execução de tarefas e auditoria.")
    if any(term in text for term in ("monitor", "observability", "netdata", "metrics")):
        patterns.append("Observabilidade, métricas e feedback loop para melhorar execução continuamente.")
    if any(term in text for term in ("course", "beginners", "roadmap", "from-scratch")):
        patterns.append("Material educacional e exemplos reproduzíveis para treinar e validar capacidades.")
    if not patterns:
        patterns.append("Priorizar projetos populares, ativos e bem documentados como referência de evolução.")
    return patterns


def write_watchlist(repos: list[RepoSnapshot], *, source: str, queries: list[str]) -> dict:
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "queries": queries,
        "count": len(repos),
        "repos": [asdict(repo) for repo in repos],
    }
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def write_absorption_report(repos: list[RepoSnapshot], *, source: str, warnings: list[str]) -> Path:
    top = repos[:10]
    languages = _language_distribution(repos)
    patterns = infer_absorption_patterns(repos)
    lines = [
        "# Execução — Absorção GitHub Top Stars pela ATENA",
        "",
        f"**Data UTC:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Resultado",
        "",
        f"- Fonte usada: `{source}`.",
        f"- Repositórios analisados: `{len(repos)}`.",
        f"- Top 1 por estrelas: `{top[0].full_name}` com `{top[0].stargazers_count}` stars." if top else "- Nenhum repositório disponível.",
        f"- Linguagens predominantes: `{languages}`.",
        "",
    ]
    if warnings:
        lines.extend(["## Avisos", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    lines.extend(["## Top repositórios absorvidos", ""])
    for idx, repo in enumerate(top, 1):
        lines.append(
            f"{idx}. `{repo.full_name}` — {repo.stargazers_count} stars — {repo.language or 'Unknown'} — {repo.description}"
        )

    lines.extend(["", "## Padrões absorvidos", ""])
    lines.extend(f"- {pattern}" for pattern in patterns)
    lines.extend([
        "",
        "## Interpretação",
        "",
        "A Atena demonstrou capacidade de ranquear repositórios por estrelas, deduplicar resultados, "
        "extrair sinais de arquitetura e transformar a watchlist em recomendações operacionais. "
        "Quando a API ao vivo está bloqueada pelo ambiente, o teste usa a última watchlist local para "
        "manter a absorção auditável e reprodutível.",
        "",
    ])

    ABSORPTION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ABSORPTION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return ABSORPTION_REPORT_PATH


def main() -> int:
    collected: List[RepoSnapshot] = []
    warnings: list[str] = []
    source = "GitHub Search API"
    for q in DEFAULT_QUERIES:
        try:
            collected.extend(search_repos(q))
            time.sleep(0.4)
        except Exception as exc:
            warning = f"Falha na query '{q}': {exc}"
            warnings.append(warning)
            print(f"[WARN] {warning}")

    used_fallback = False
    if not collected:
        fallback = load_watchlist()
        if fallback:
            collected = fallback
            source = "local fallback docs/ai_repo_watchlist.json"
            used_fallback = True
            print(f"[WARN] Usando fallback local com {len(fallback)} repositórios.")
        else:
            print("[ERROR] Nenhum repositório coletado do GitHub e fallback local ausente.")
            return 1

    top = dedupe_rank(collected, top_n=50)
    if not used_fallback:
        write_watchlist(top, source=source, queries=DEFAULT_QUERIES)
        print(f"[OK] Watchlist gerada em: {WATCHLIST_PATH} ({len(top)} repositórios)")
    else:
        print(f"[OK] Watchlist local preservada em: {WATCHLIST_PATH} ({len(top)} repositórios)")
    report_path = write_absorption_report(top, source=source, warnings=warnings)
    print(f"[OK] Relatório de absorção gerado em: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
