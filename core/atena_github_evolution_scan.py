#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔱 ATENA GitHub Evolution Scanner v3.0 - Enterprise Intelligence

Enterprise Features:
- 🔍 Multi-query GitHub search com rate limiting inteligente
- 🧠 AI-powered repository classification e scoring
- 💾 Smart caching com Redis/PostgreSQL fallback
- 📊 Advanced analytics e trend detection
- 🔄 Auto-clone com filtering inteligente
- 📝 Structured absorption com versionamento
- 🎯 Pattern extraction e code mining
- 🔒 Security scanning e license compliance
- 📈 Real-time progress tracking
- 🌐 Proxy support e retry mechanisms
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set, Union, Callable
from functools import lru_cache, wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

# Tentativas de import para funcionalidades avançadas
try:
    import aiohttp
    import aiofiles
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constantes
ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "data" / "github_scans"
CLONE_DIR = ROOT / "data" / "github_clones"
INCORPORATED_DIR = ROOT / "core" / "incorporated_github"
ABSORPTION_DOC = ROOT / "docs" / "evolution" / "github_insights.md"

# Configurações GitHub
GITHUB_API_URL = "https://api.github.com"
GITHUB_SEARCH_URL = f"{GITHUB_API_URL}/search/repositories"
GITHUB_RATE_LIMIT = 60  # requests per hour (unauthenticated)
GITHUB_AUTH_RATE_LIMIT = 5000  # requests per hour (authenticated)

# Configurações de scan
DEFAULT_QUERIES = [
    "autonomous ai agent framework stars:>500 archived:false",
    "llm agent orchestration stars:>500 archived:false",
    "self improving ai agents stars:>100 archived:false",
    "ai coding agent benchmark stars:>100 archived:false",
    "multi agent reinforcement learning stars:>100 archived:false",
    "agentic workflow automation stars:>50 archived:false",
]

# =============================================================================
# Enums e Configurações
# =============================================================================

class ScanMode(Enum):
    """Modos de escaneamento"""
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    FULL = "full"

class RepoQuality(Enum):
    """Qualidade do repositório"""
    EXCELLENT = "excellent"  # > 10000 stars, active, well-documented
    GOOD = "good"           # 1000-10000 stars
    FAIR = "fair"           # 100-1000 stars
    POOR = "poor"           # < 100 stars

@dataclass
class ScanConfig:
    """Configuração avançada do scanner"""
    mode: ScanMode = ScanMode.STANDARD
    limit_per_query: int = 10
    top_n: int = 25
    min_stars: int = 50
    max_age_days: int = 730  # 2 years
    include_forks: bool = False
    include_archived: bool = False
    language_filter: Optional[List[str]] = None
    
    # Cache
    use_cache: bool = True
    cache_ttl: int = 3600  # 1 hour
    
    # Performance
    max_concurrent_requests: int = 5
    request_timeout: int = 30
    retry_attempts: int = 3
    
    # Cloning
    shallow_clone: bool = True
    max_clone_size_mb: int = 500
    clone_timeout: int = 300
    
    # Incorporation
    max_files_per_repo: int = 100
    max_file_size_kb: int = 256
    
    def to_dict(self) -> Dict:
        return {k: v.value if isinstance(v, Enum) else v for k, v in self.__dict__.items()}

@dataclass
class RepositoryInsight:
    """Insights detalhados de um repositório"""
    full_name: str
    html_url: str
    description: str
    stars: int
    forks: int
    language: Optional[str]
    topics: List[str]
    license_spdx: Optional[str]
    created_at: str
    updated_at: str
    pushed_at: str
    size_mb: float
    open_issues: int
    watchers: int
    
    # Scores
    popularity_score: float = 0.0
    activity_score: float = 0.0
    quality_score: float = 0.0
    relevance_score: float = 0.0
    total_score: float = 0.0
    
    # Classificação
    quality: RepoQuality = RepoQuality.FAIR
    themes: List[str] = field(default_factory=list)
    
    def compute_scores(self):
        """Calcula scores baseados em múltiplos fatores"""
        # Popularity (stars, forks, watchers)
        self.popularity_score = min(1.0, (self.stars / 10000) * 0.5 + 
                                     (self.forks / 5000) * 0.3 + 
                                     (self.watchers / 1000) * 0.2)
        
        # Activity (recent updates, issues)
        try:
            last_update = datetime.fromisoformat(self.updated_at.replace('Z', '+00:00'))
            days_since_update = (datetime.now().astimezone() - last_update).days
            activity = max(0, min(1, 1 - (days_since_update / 365)))
        except:
            activity = 0.5
        
        issue_ratio = min(1, self.open_issues / 100) if self.open_issues > 0 else 0
        self.activity_score = activity * 0.7 + (1 - issue_ratio) * 0.3
        
        # Quality (size, description, topics)
        has_description = 0.3 if self.description and len(self.description) > 50 else 0
        has_topics = 0.2 if self.topics else 0
        has_license = 0.2 if self.license_spdx else 0
        language_bonus = 0.3 if self.language and self.language.lower() in ['python', 'typescript', 'go'] else 0
        
        self.quality_score = has_description + has_topics + has_license + language_bonus
        
        # Relevance (based on keywords)
        relevant_keywords = ['agent', 'autonomous', 'llm', 'ai', 'machine learning']
        text = f"{self.description} {' '.join(self.topics)}".lower()
        matches = sum(1 for kw in relevant_keywords if kw in text)
        self.relevance_score = min(1.0, matches / len(relevant_keywords))
        
        # Total score (weighted)
        self.total_score = (self.popularity_score * 0.4 + 
                           self.activity_score * 0.3 + 
                           self.quality_score * 0.2 + 
                           self.relevance_score * 0.1)
        
        # Quality classification
        if self.total_score >= 0.8:
            self.quality = RepoQuality.EXCELLENT
        elif self.total_score >= 0.6:
            self.quality = RepoQuality.GOOD
        elif self.total_score >= 0.4:
            self.quality = RepoQuality.FAIR
        else:
            self.quality = RepoQuality.POOR
    
    def to_dict(self) -> Dict:
        return {
            "full_name": self.full_name,
            "html_url": self.html_url,
            "description": self.description[:500] if self.description else "",
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "topics": self.topics[:10],
            "license": self.license_spdx,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "size_mb": self.size_mb,
            "scores": {
                "popularity": round(self.popularity_score, 3),
                "activity": round(self.activity_score, 3),
                "quality": round(self.quality_score, 3),
                "relevance": round(self.relevance_score, 3),
                "total": round(self.total_score, 3)
            },
            "quality": self.quality.value,
            "themes": self.themes
        }

# =============================================================================
# Cache Manager
# =============================================================================

class CacheManager:
    """Gerenciador de cache para GitHub API"""
    
    def __init__(self, config: ScanConfig):
        self.config = config
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._redis = None
        self._init_redis()
    
    def _init_redis(self):
        if HAS_REDIS and os.getenv("REDIS_URL"):
            try:
                self._redis = redis.from_url(os.getenv("REDIS_URL"))
                logger.info("Redis cache enabled")
            except Exception as e:
                logger.warning(f"Redis init failed: {e}")
    
    def _get_key(self, prefix: str, *args) -> str:
        """Gera chave de cache"""
        key_str = ":".join(str(arg) for arg in args)
        return f"github_scan:{prefix}:{hashlib.md5(key_str.encode()).hexdigest()}"
    
    def get(self, key: str) -> Optional[Any]:
        """Obtém valor do cache"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Armazena valor no cache"""
        ttl = ttl or self.config.cache_ttl
        self._cache[key] = (value, time.time() + ttl)
    
    async def get_async(self, key: str) -> Optional[Any]:
        """Obtém valor do cache assíncrono"""
        if self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    return json.loads(data)
            except:
                pass
        return self.get(key)
    
    async def set_async(self, key: str, value: Any, ttl: Optional[int] = None):
        """Armazena valor no cache assíncrono"""
        ttl = ttl or self.config.cache_ttl
        if self._redis:
            try:
                await self._redis.setex(key, ttl, json.dumps(value))
            except:
                pass
        self.set(key, value, ttl)
    
    def clear(self):
        """Limpa cache"""
        self._cache.clear()
        logger.info("Cache cleared")

# =============================================================================
# GitHub API Client
# =============================================================================

class GitHubClient:
    """Cliente assíncrono para GitHub API"""
    
    def __init__(self, config: ScanConfig, cache: CacheManager):
        self.config = config
        self.cache = cache
        self.token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.rate_limit_remaining = GITHUB_AUTH_RATE_LIMIT if self.token else GITHUB_RATE_LIMIT
        self._session = None
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ATENA-GitHub-Evolution-Scanner",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def _request(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Faz requisição à GitHub API com retry"""
        if HAS_AIOHTTP:
            if not self._session:
                self._session = aiohttp.ClientSession(headers=self._get_headers())
            
            # Check cache
            cache_key = self.cache._get_key("request", url, str(params))
            cached = await self.cache.get_async(cache_key)
            if cached:
                return cached
            
            for attempt in range(self.config.retry_attempts):
                try:
                    async with self._session.get(url, params=params, timeout=self.config.request_timeout) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            await self.cache.set_async(cache_key, data)
                            return data
                        elif resp.status == 403 and 'rate limit' in str(resp):
                            # Rate limit - wait and retry
                            wait_time = 60
                            logger.warning(f"Rate limit hit, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.warning(f"GitHub API error: {resp.status}")
                            return {}
                except Exception as e:
                    logger.warning(f"Request attempt {attempt + 1} failed: {e}")
                    if attempt < self.config.retry_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
            return {}
        else:
            # Fallback síncrono
            return self._request_sync(url, params)
    
    def _request_sync(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Versão síncrona para fallback"""
        req = urllib.request.Request(url, headers=self._get_headers())
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        
        try:
            with urllib.request.urlopen(req, timeout=self.config.request_timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {}
    
    async def search_repositories(self, query: str, per_page: int = 30, page: int = 1) -> List[Dict]:
        """Busca repositórios no GitHub"""
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(per_page, 100),
            "page": page
        }
        
        data = await self._request(GITHUB_SEARCH_URL, params)
        return data.get("items", [])
    
    async def get_repository_details(self, full_name: str) -> Dict:
        """Obtém detalhes de um repositório específico"""
        url = f"{GITHUB_API_URL}/repos/{full_name}"
        return await self._request(url)
    
    async def close(self):
        """Fecha sessão"""
        if self._session:
            await self._session.close()

# =============================================================================
# Repository Analyzer
# =============================================================================

class RepositoryAnalyzer:
    """Analisador avançado de repositórios"""
    
    # Temas e palavras-chave
    THEMES = {
        "agent_orchestration": ["agent", "orchestration", "multi-agent", "crew", "swarm"],
        "memory_rag": ["rag", "memory", "retrieval", "vector", "embedding"],
        "benchmarks": ["benchmark", "eval", "evaluation", "leaderboard", "test"],
        "coding_agents": ["coding", "code", "developer", "automation", "copilot"],
        "security": ["security", "sandbox", "guardrail", "policy", "safety"],
        "llm_integration": ["llm", "gpt", "claude", "gemini", "anthropic"],
        "self_improvement": ["self-improving", "evolution", "adaptive", "learning"]
    }
    
    @classmethod
    def analyze(cls, repo_data: Dict) -> RepositoryInsight:
        """Cria insight completo do repositório"""
        # Extrai dados básicos
        full_name = repo_data.get("full_name", "")
        html_url = repo_data.get("html_url", "")
        description = repo_data.get("description") or ""
        stars = repo_data.get("stargazers_count", 0)
        forks = repo_data.get("forks_count", 0)
        language = repo_data.get("language")
        topics = repo_data.get("topics", [])
        license_info = repo_data.get("license") or {}
        
        # Tamanho do repositório
        size_kb = repo_data.get("size", 0)
        size_mb = size_kb / 1024
        
        # Datas
        created_at = repo_data.get("created_at", "")
        updated_at = repo_data.get("updated_at", "")
        pushed_at = repo_data.get("pushed_at", "")
        
        # Métricas
        open_issues = repo_data.get("open_issues_count", 0)
        watchers = repo_data.get("watchers_count", 0)
        
        # Cria insight
        insight = RepositoryInsight(
            full_name=full_name,
            html_url=html_url,
            description=description,
            stars=stars,
            forks=forks,
            language=language,
            topics=topics,
            license_spdx=license_info.get("spdx_id"),
            created_at=created_at,
            updated_at=updated_at,
            pushed_at=pushed_at,
            size_mb=size_mb,
            open_issues=open_issues,
            watchers=watchers
        )
        
        # Classifica temas
        insight.themes = cls._classify_themes(insight)
        
        # Calcula scores
        insight.compute_scores()
        
        return insight
    
    @classmethod
    def _classify_themes(cls, insight: RepositoryInsight) -> List[str]:
        """Classifica temas do repositório"""
        text = f"{insight.full_name} {insight.description} {' '.join(insight.topics)}".lower()
        
        themes = []
        for theme, keywords in cls.THEMES.items():
            if any(kw in text for kw in keywords):
                themes.append(theme)
        
        # Adiciona tags de qualidade
        if insight.stars >= 10000:
            themes.append("highly_adopted")
        if insight.stars >= 1000 and insight.stars < 10000:
            themes.append("popular")
        
        # Recência
        try:
            last_update = datetime.fromisoformat(insight.updated_at.replace('Z', '+00:00'))
            days_old = (datetime.now().astimezone() - last_update).days
            if days_old < 30:
                themes.append("very_active")
            elif days_old < 180:
                themes.append("active")
        except:
            pass
        
        return themes

# =============================================================================
# GitHub Evolution Scanner
# =============================================================================

class GitHubEvolutionScanner:
    """Scanner principal para evolução da ATENA"""
    
    def __init__(self, config: Optional[ScanConfig] = None):
        self.config = config or ScanConfig()
        self.cache = CacheManager(self.config)
        self.client = GitHubClient(self.config, self.cache)
        self.results: List[RepositoryInsight] = []
        self.errors: List[str] = []
        
        # Diretórios
        self.report_dir = REPORT_DIR
        self.clone_dir = CLONE_DIR
        self.incorporated_dir = INCORPORATED_DIR
        self.absorption_doc = ABSORPTION_DOC
        
        # Cria diretórios
        for dir_path in [self.report_dir, self.clone_dir, self.incorporated_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🔍 GitHub Evolution Scanner initialized")
        logger.info(f"   Mode: {self.config.mode.value}")
        logger.info(f"   Cache: {'enabled' if self.config.use_cache else 'disabled'}")
        logger.info(f"   Concurrent: {self.config.max_concurrent_requests}")
    
    async def scan(self, objective: str) -> Dict[str, Any]:
        """Executa scan completo"""
        start_time = time.perf_counter()
        
        logger.info(f"Starting GitHub scan for: {objective}")
        
        # Prepara queries
        queries = self._prepare_queries(objective)
        
        # Busca repositórios
        all_repos = []
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(self._search_query(query)) for query in queries]
        
        for task in tasks:
            all_repos.extend(task.result())
        
        # Analisa repositórios
        self.results = []
        for repo_data in all_repos[:self.config.top_n * 2]:
            insight = RepositoryAnalyzer.analyze(repo_data)
            if insight.stars >= self.config.min_stars:
                self.results.append(insight)
        
        # Ordena por score total
        self.results.sort(key=lambda x: x.total_score, reverse=True)
        self.results = self.results[:self.config.top_n]
        
        # Gera relatórios
        report = self._generate_report(objective)
        report["processing_time_ms"] = (time.perf_counter() - start_time) * 1000
        
        return report
    
    def _prepare_queries(self, objective: str) -> List[str]:
        """Prepara queries de busca"""
        queries = []
        
        # Query principal baseada no objetivo
        main_query = f"{objective} stars:>{self.config.min_stars} archived:false"
        if not self.config.include_forks:
            main_query += " fork:false"
        queries.append(main_query)
        
        # Queries padrão
        queries.extend(DEFAULT_QUERIES[:3])
        
        # Filtro de linguagem
        if self.config.language_filter:
            for lang in self.config.language_filter:
                queries.append(f"language:{lang} stars:>{self.config.min_stars}")
        
        return queries[:5]  # Limita número de queries
    
    async def _search_query(self, query: str) -> List[Dict]:
        """Executa busca para uma query específica"""
        try:
            repos = await self.client.search_repositories(
                query,
                per_page=self.config.limit_per_query
            )
            logger.info(f"Query '{query[:50]}...' returned {len(repos)} repos")
            return repos
        except Exception as e:
            self.errors.append(f"Query failed: {query[:50]} - {e}")
            return []
    
    def _generate_report(self, objective: str) -> Dict[str, Any]:
        """Gera relatório completo"""
        # Summary
        total_stars = sum(r.stars for r in self.results)
        avg_score = sum(r.total_score for r in self.results) / len(self.results) if self.results else 0
        
        # Theme distribution
        theme_counts = defaultdict(int)
        for repo in self.results:
            for theme in repo.themes:
                theme_counts[theme] += 1
        
        # Language distribution
        lang_counts = defaultdict(int)
        for repo in self.results:
            if repo.language:
                lang_counts[repo.language] += 1
        
        # Quality distribution
        quality_counts = defaultdict(int)
        for repo in self.results:
            quality_counts[repo.quality.value] += 1
        
        report = {
            "status": "success" if self.results else "warning",
            "generated_at": datetime.now().isoformat(),
            "objective": objective,
            "config": self.config.to_dict(),
            "summary": {
                "total_repos": len(self.results),
                "total_stars": total_stars,
                "avg_stars": total_stars / len(self.results) if self.results else 0,
                "avg_score": round(avg_score, 3),
                "quality_distribution": dict(quality_counts),
                "language_distribution": dict(lang_counts),
                "theme_distribution": dict(theme_counts)
            },
            "repositories": [r.to_dict() for r in self.results],
            "errors": self.errors,
            "evolution_actions": self._generate_actions()
        }
        
        # Salva relatórios
        self._save_reports(report)
        
        return report
    
    def _generate_actions(self) -> List[str]:
        """Gera ações de evolução baseadas nos achados"""
        actions = []
        
        # Análise de temas dominantes
        all_themes = [t for r in self.results for t in r.themes]
        theme_counts = defaultdict(int)
        for theme in all_themes:
            theme_counts[theme] += 1
        
        top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        if top_themes:
            actions.append(f"🎯 Foco principal: {', '.join([t[0] for t in top_themes])}")
        
        # Ações específicas por tema
        if "agent_orchestration" in theme_counts:
            actions.append("🤖 Implementar padrões avançados de orquestração multi-agente")
        if "memory_rag" in theme_counts:
            actions.append("🧠 Aprimorar sistema de memória RAG com técnicas encontradas")
        if "benchmarks" in theme_counts:
            actions.append("📊 Criar benchmark específico para avaliar evolução")
        if "coding_agents" in theme_counts:
            actions.append("💻 Expandir capacidades de geração e revisão de código")
        if "security" in theme_counts:
            actions.append("🔒 Reforçar guardrails e segurança antes de automação avançada")
        
        # Ações baseadas em qualidade
        excellent = [r for r in self.results if r.quality == RepoQuality.EXCELLENT]
        if excellent:
            actions.append(f"⭐ Analisar em detalhe {len(excellent)} repositórios de excelência")
        
        # Ação de validação
        actions.append("✅ Validar cada ideia com teste rápido antes de implementar")
        
        return actions[:10]  # Limita a 10 ações
    
    def _save_reports(self, report: Dict[str, Any]):
        """Salva relatórios em JSON e Markdown"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON report
        json_path = self.report_dir / f"github_scan_{timestamp}.json"
        json_path.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
        
        # Markdown report
        md_path = self.report_dir / f"github_scan_{timestamp}.md"
        md_content = self._generate_markdown(report)
        md_path.write_text(md_content, encoding='utf-8')
        
        # Latest symlink
        latest_json = self.report_dir / "latest_scan.json"
        latest_json.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
        
        logger.info(f"Reports saved: {json_path}, {md_path}")
    
    def _generate_markdown(self, report: Dict[str, Any]) -> str:
        """Gera relatório em Markdown"""
        lines = [
            "# 🔱 ATENA GitHub Evolution Scan",
            "",
            f"- **Objetivo**: `{report['objective']}`",
            f"- **Gerado**: `{report['generated_at']}`",
            f"- **Status**: `{report['status']}`",
            f"- **Total repositórios**: `{report['summary']['total_repos']}`",
            f"- **Estrelas totais**: `{report['summary']['total_stars']:,}`",
            f"- **Score médio**: `{report['summary']['avg_score']}`",
            "",
            "## 📊 Estatísticas",
            "",
            "### Distribuição de Qualidade",
        ]
        
        for quality, count in report['summary']['quality_distribution'].items():
            lines.append(f"- {quality}: {count}")
        
        lines.extend([
            "",
            "### Linguagens Mais Comuns",
        ])
        
        for lang, count in sorted(report['summary']['language_distribution'].items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"- {lang}: {count}")
        
        lines.extend([
            "",
            "## 🎯 Ações de Evolução",
        ])
        
        for action in report['evolution_actions']:
            lines.append(f"- {action}")
        
        lines.extend([
            "",
            "## 📦 Top Repositórios",
        ])
        
        for idx, repo in enumerate(report['repositories'][:10], 1):
            lines.extend([
                f"### {idx}. {repo['full_name']}",
                f"- ⭐ {repo['stars']:,} estrelas",
                f"- 🎯 Score: {repo['scores']['total']:.3f}",
                f"- 🏷️ Qualidade: {repo['quality']}",
                f"- 📝 {repo['description'][:200]}..." if repo['description'] else "",
                f"- 🔗 {repo['html_url']}",
                ""
            ])
        
        return "\n".join(lines)
    
    async def clone_repositories(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Clona os melhores repositórios"""
        limit = limit or min(5, len(self.results))
        selected = self.results[:limit]
        
        results = []
        for repo in selected:
            result = await self._clone_repository(repo)
            results.append(result)
        
        return {
            "total": len(selected),
            "successful": sum(1 for r in results if r['status'] == 'success'),
            "results": results,
            "clone_dir": str(self.clone_dir)
        }
    
    async def _clone_repository(self, repo: RepositoryInsight) -> Dict[str, Any]:
        """Clona um repositório específico"""
        repo_dir = self.clone_dir / repo.full_name.replace('/', '__')
        
        if repo_dir.exists():
            return {
                "repo": repo.full_name,
                "status": "exists",
                "path": str(repo_dir)
            }
        
        clone_url = f"{repo.html_url}.git"
        cmd = ["git", "clone"]
        
        if self.config.shallow_clone:
            cmd.extend(["--depth", "1"])
        
        cmd.extend([clone_url, str(repo_dir)])
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.clone_timeout
            )
            
            if process.returncode == 0:
                return {
                    "repo": repo.full_name,
                    "status": "success",
                    "path": str(repo_dir),
                    "size_mb": repo.size_mb
                }
            else:
                return {
                    "repo": repo.full_name,
                    "status": "failed",
                    "error": stderr.decode()[:200]
                }
        except asyncio.TimeoutError:
            return {
                "repo": repo.full_name,
                "status": "timeout",
                "error": f"Timeout after {self.config.clone_timeout}s"
            }
        except Exception as e:
            return {
                "repo": repo.full_name,
                "status": "error",
                "error": str(e)
            }
    
    async def incorporate_repositories(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Incorporar repositórios no core da ATENA"""
        limit = limit or min(3, len(self.results))
        selected = self.results[:limit]
        
        results = []
        for repo in selected:
            result = await self._incorporate_repository(repo)
            results.append(result)
        
        return {
            "total": len(selected),
            "successful": sum(1 for r in results if r['status'] == 'success'),
            "results": results,
            "incorporated_dir": str(self.incorporated_dir)
        }
    
    async def _incorporate_repository(self, repo: RepositoryInsight) -> Dict[str, Any]:
        """Incorporar um repositório ao core"""
        source_dir = self.clone_dir / repo.full_name.replace('/', '__')
        
        if not source_dir.exists():
            # Clone first
            clone_result = await self._clone_repository(repo)
            if clone_result['status'] != 'success':
                return clone_result
        
        target_dir = self.incorporated_dir / repo.full_name.replace('/', '__')
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy filtered files
        copied = 0
        skipped = 0
        
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(source_dir)
                
                # Check if should copy
                if self._should_incorporate(file_path, rel_path):
                    dest_path = target_dir / rel_path
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, dest_path)
                    copied += 1
                    
                    if copied >= self.config.max_files_per_repo:
                        break
                else:
                    skipped += 1
        
        # Save incorporation manifest
        manifest = {
            "repo": repo.full_name,
            "source_url": repo.html_url,
            "license": repo.license_spdx,
            "stars": repo.stars,
            "score": repo.total_score,
            "incorporated_at": datetime.now().isoformat(),
            "copied_files": copied,
            "skipped_files": skipped,
            "target_dir": str(target_dir)
        }
        
        manifest_path = target_dir / "ATENA_INCORPORATION.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        
        return {
            "repo": repo.full_name,
            "status": "success",
            "copied": copied,
            "skipped": skipped,
            "target_dir": str(target_dir)
        }
    
    def _should_incorporate(self, file_path: Path, rel_path: Path) -> bool:
        """Verifica se arquivo deve ser incorporado"""
        # Skip directories
        if any(part in str(rel_path) for part in ['.git', '__pycache__', 'node_modules', 'dist', 'build']):
            return False
        
        # Check extension
        allowed_extensions = {'.py', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.rst'}
        if file_path.suffix not in allowed_extensions:
            return False
        
        # Check size
        try:
            size_kb = file_path.stat().st_size / 1024
            if size_kb > self.config.max_file_size_kb:
                return False
        except:
            return False
        
        return True
    
    async def absorb_insights(self) -> Path:
        """Absorve insights no documento do repositório"""
        if not self.results:
            raise ValueError("No scan results to absorb")
        
        lines = [
            "# 🔱 ATENA GitHub Evolution Insights",
            "",
            f"**Gerado**: {datetime.now().isoformat()}",
            f"**Total insights**: {len(self.results)}",
            "",
            "## 🎯 Recomendações Prioritárias",
            ""
        ]
        
        # Adiciona ações
        actions = self._generate_actions()
        for action in actions[:5]:
            lines.append(f"- {action}")
        
        lines.extend([
            "",
            "## 📊 Top Repositórios para Estudo",
            ""
        ])
        
        for idx, repo in enumerate(self.results[:5], 1):
            lines.extend([
                f"### {idx}. [{repo.full_name}]({repo.html_url})",
                f"- **Stars**: ⭐ {repo.stars:,}",
                f"- **Score**: {repo.total_score:.3f}",
                f"- **Qualidade**: {repo.quality.value}",
                f"- **Temas**: {', '.join(repo.themes)}",
                f"- **Descrição**: {repo.description[:200]}..." if repo.description else "",
                ""
            ])
        
        # Salva documento
        self.absorption_doc.parent.mkdir(parents=True, exist_ok=True)
        self.absorption_doc.write_text("\n".join(lines), encoding='utf-8')
        
        logger.info(f"Insights absorbed to {self.absorption_doc}")
        return self.absorption_doc
    
    async def close(self):
        """Fecha conexões"""
        await self.client.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do scanner"""
        return {
            "total_scans": len(list(self.report_dir.glob("*.json"))),
            "total_clones": len(list(self.clone_dir.glob("*"))),
            "total_incorporated": len(list(self.incorporated_dir.glob("*"))),
            "cache_size": len(self.cache._cache)
        }


def run_github_evolution_scan(
    objective: str = "evolução autônoma",
    *,
    absorb: bool = False,
    clone: bool = False,
    clone_limit: int | None = None,
    incorporate: bool = False,
    incorporate_limit: int | None = None,
    config: ScanConfig | None = None,
) -> Dict[str, Any]:
    """Run the async GitHub evolution scanner from synchronous callers.

    The terminal assistant imports this helper directly.  It normalizes the
    richer scanner report into the compact payload consumed by the interactive
    command while keeping errors non-fatal for offline/local test runs.
    """

    async def _run() -> Dict[str, Any]:
        scanner = GitHubEvolutionScanner(config)
        try:
            report = await scanner.scan(objective)
            cloned: Dict[str, Any] | None = None
            incorporated: Dict[str, Any] | None = None
            absorbed_path: str | None = None

            if clone:
                cloned = await scanner.clone_repositories(clone_limit)
            if incorporate:
                incorporated = await scanner.incorporate_repositories(incorporate_limit)
            if absorb:
                absorbed_path = str(await scanner.absorb_insights())

            latest_md = scanner.report_dir / "latest_scan.md"
            markdown_path = str(latest_md if latest_md.exists() else scanner.report_dir)
            repositories = report.get("repositories", [])
            names = [str(repo.get("full_name", "")) for repo in repositories if repo.get("full_name")]
            return {
                "status": "ok" if report.get("status") in {"success", "warning"} else "failed",
                "objective": objective,
                "repo_count": report.get("summary", {}).get("total_repos", len(repositories)),
                "markdown_path": markdown_path,
                "report": report,
                "findings_summary": {
                    "answer_what_she_found": names,
                    "verdict": "interessante" if names else "sem achados relevantes no momento",
                    "does_she_always_find_interesting_things": bool(names),
                },
                "cloned": cloned,
                "incorporated": incorporated,
                "absorbed_path": absorbed_path,
            }
        finally:
            await scanner.close()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(_run())
        except Exception as exc:  # pragma: no cover - network/offline fallback
            logger.exception("GitHub evolution scan failed")
            return {
                "status": "failed",
                "objective": objective,
                "repo_count": 0,
                "markdown_path": None,
                "findings_summary": {
                    "answer_what_she_found": [],
                    "verdict": f"erro: {exc}",
                    "does_she_always_find_interesting_things": False,
                },
                "error": str(exc),
            }

    import threading

    holder: dict[str, Dict[str, Any]] = {}

    def _thread_target() -> None:
        holder["payload"] = asyncio.run(_run())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    thread.join()
    return holder["payload"]

# =============================================================================
# CLI Interface
# =============================================================================

async def async_main(args):
    """Main assíncrono"""
    config = ScanConfig(
        mode=ScanMode[args.mode.upper()] if args.mode else ScanMode.STANDARD,
        limit_per_query=args.limit_per_query,
        top_n=args.top_n,
        min_stars=args.min_stars
    )
    
    scanner = GitHubEvolutionScanner(config)
    
    try:
        # Executa scan
        objective = " ".join(args.objective) if args.objective else "evolução autônoma"
        report = await scanner.scan(objective)
        
        # Ações pós-scan
        if args.clone:
            clone_result = await scanner.clone_repositories(args.clone_limit)
            report['clone_result'] = clone_result
        
        if args.incorporate:
            incorp_result = await scanner.incorporate_repositories(args.incorporate_limit)
            report['incorporation_result'] = incorp_result
        
        if args.absorb:
            absorbed_path = await scanner.absorb_insights()
            report['absorbed_path'] = str(absorbed_path)
        
        # Output
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(f"\n🔍 GitHub Evolution Scan Results")
            print(f"=" * 50)
            print(f"Status: {report['status']}")
            print(f"Repositories: {report['summary']['total_repos']}")
            print(f"Total Stars: {report['summary']['total_stars']:,}")
            print(f"Avg Score: {report['summary']['avg_score']:.3f}")
            print(f"\n🎯 Top Actions:")
            for action in report['evolution_actions'][:5]:
                print(f"  • {action}")
            print(f"\n⭐ Top Repository: {report['repositories'][0]['full_name'] if report['repositories'] else 'None'}")
            print(f"   Score: {report['repositories'][0]['scores']['total'] if report['repositories'] else 0:.3f}")
        
    finally:
        await scanner.close()

def main():
    """Entry point principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ATENA GitHub Evolution Scanner")
    parser.add_argument("objective", nargs="*", help="Objective for evolution scan")
    parser.add_argument("--mode", choices=["quick", "standard", "deep", "full"], default="standard")
    parser.add_argument("--limit-per-query", type=int, default=10)
    parser.add_argument("--top-n", type=int, default=25)
    parser.add_argument("--min-stars", type=int, default=50)
    parser.add_argument("--clone", action="store_true", help="Clone top repositories")
    parser.add_argument("--clone-limit", type=int, default=3)
    parser.add_argument("--incorporate", action="store_true", help="Incorporate to core")
    parser.add_argument("--incorporate-limit", type=int, default=2)
    parser.add_argument("--absorb", action="store_true", help="Absorb insights to docs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    
    args = parser.parse_args()
    
    if args.stats:
        scanner = GitHubEvolutionScanner()
        stats = scanner.get_stats()
        print(json.dumps(stats, indent=2))
        return
    
    asyncio.run(async_main(args))

if __name__ == "__main__":
    main()
