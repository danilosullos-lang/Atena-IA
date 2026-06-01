from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "scan_github_ai_repos.py"
    spec = importlib.util.spec_from_file_location("scan_github_ai_repos", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dedupe_rank_keeps_highest_star_entry():
    mod = _load_module()
    repos = [
        mod.RepoSnapshot("org/a", "u", "d", 10, "Python", "2026-01-01"),
        mod.RepoSnapshot("org/a", "u", "d", 100, "Python", "2026-01-02"),
        mod.RepoSnapshot("org/b", "u", "d", 50, "Go", "2026-01-03"),
    ]

    ranked = mod.dedupe_rank(repos, top_n=10)

    assert [r.full_name for r in ranked] == ["org/a", "org/b"]
    assert ranked[0].stargazers_count == 100


def test_main_writes_watchlist(monkeypatch, tmp_path):
    mod = _load_module()

    def fake_search(_query: str, per_page: int = 20):
        return [
            mod.RepoSnapshot("org/x", "https://example/x", "desc", 999, "Python", "2026-01-01"),
            mod.RepoSnapshot("org/y", "https://example/y", "desc", 500, "Go", "2026-01-02"),
        ]

    monkeypatch.setattr(mod, "search_repos", fake_search)
    monkeypatch.chdir(tmp_path)

    rc = mod.main()
    assert rc == 0

    out_file = tmp_path / "docs" / "ai_repo_watchlist.json"
    assert out_file.exists()

    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["count"] >= 2
    assert payload["repos"][0]["full_name"] == "org/x"

    report_file = tmp_path / "analysis_reports" / "EXECUCAO_GITHUB_TOP_STARS_ABSORPTION_2026-06-01.md"
    assert report_file.exists()
    assert "Padrões absorvidos" in report_file.read_text(encoding="utf-8")


def test_main_uses_local_watchlist_fallback(monkeypatch, tmp_path):
    mod = _load_module()

    def failing_search(_query: str, per_page: int = 20):
        raise OSError("network blocked")

    monkeypatch.setattr(mod, "search_repos", failing_search)
    monkeypatch.chdir(tmp_path)

    fallback = {
        "repos": [
            {
                "full_name": "big/ai",
                "html_url": "https://example/big-ai",
                "description": "LLM agent framework with RAG and observability",
                "stargazers_count": 123456,
                "language": "Python",
                "updated_at": "2026-01-01",
            }
        ]
    }
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ai_repo_watchlist.json").write_text(json.dumps(fallback), encoding="utf-8")

    rc = mod.main()

    assert rc == 0
    payload = json.loads((docs / "ai_repo_watchlist.json").read_text(encoding="utf-8"))
    assert payload == fallback
    report = (tmp_path / "analysis_reports" / "EXECUCAO_GITHUB_TOP_STARS_ABSORPTION_2026-06-01.md").read_text(encoding="utf-8")
    assert "big/ai" in report
    assert "API ao vivo" in report
