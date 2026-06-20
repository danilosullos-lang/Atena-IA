#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATENA Ω Vercel Dashboard and Chat API - Enterprise Edition
Version: 10.2.0 - OMNI-PREDATOR Core+
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

# --- CONFIGURAÇÃO DE LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- ACÚMULO DE INTERAÇÕES (memória de conversas) ---
# ATENÇÃO: no plano Free do Render o filesystem é efêmero — esse arquivo
# é apagado a cada redeploy/restart/spin-down. Pra persistir de verdade
# entre reinicios, configure ATENA_CHAT_DB_PATH apontando pra um disco
# persistente (plano pago) ou troque por um Render Postgres.
ATENA_CHAT_DB_PATH = os.getenv("ATENA_CHAT_DB_PATH", "atena_chat_history.db")

def _init_chat_db() -> None:
    try:
        conn = sqlite3.connect(ATENA_CHAT_DB_PATH)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                latency_ms REAL
            )
            """
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Falha ao inicializar banco de interacoes: {e}")

_init_chat_db()

def _log_interaction(message: str, response: str, provider: str | None, model: str | None, latency_ms: float | None) -> None:
    try:
        conn = sqlite3.connect(ATENA_CHAT_DB_PATH)
        conn.execute(
            "INSERT INTO interactions (timestamp, message, response, provider, model, latency_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), message, response, provider, model, latency_ms),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Falha ao logar interacao: {e}")

# --- IMPORTAÇÕES SEGURAS (Evita que o deploy quebre se um módulo faltar) ---
try:
    from core.atena_llm_router import AtenaLLMRouterAdvanced as AtenaLLMRouter, get_router
except Exception as e:
    logger.error(f"Erro ao importar AtenaLLMRouter: {e}")
    AtenaLLMRouter = None
    get_router = None

# --- LIFESPAN DEFINIDO ANTES DA CRIAÇÃO DO APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando ATENA Ω...")
    yield
    logger.info("🛑 Encerrando ATENA Ω...")

# --- CRIAÇÃO DO APP (O Uvicorn busca 'app' aqui) ---
from fastapi import FastAPI
app = FastAPI(
    title="ATENA Ω API",
    version="10.2.0",
    lifespan=lifespan
)

# --- IMPORTAÇÕES RESTANTES ---
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from api.dashboard_html import get_dashboard_html
from core.atena_evolution_v5_singularity import SingularityProtocol
from api.connectors_api import router as connectors_router

# --- SCANNER DE APIs (importação segura, igual ao padrão do AtenaLLMRouter) ---
try:
    from core.internet_challenge import (
        recommend_public_apis,
        discover_any_apis,
        rank_api_candidates,
    )
except Exception as e:
    logger.error(f"Erro ao importar internet_challenge (scanner de APIs): {e}")
    recommend_public_apis = None
    discover_any_apis = None
    rank_api_candidates = None

# Configuração CORS (Mantida)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir router de conectores
app.include_router(connectors_router)

# --- ENDPOINTS ---
@app.get("/healthz")
async def healthz():
    return {"status": "online", "version": "10.2.0"}

@app.get("/api/metrics")
async def get_metrics():
    try:
        metrics_path = "/home/ubuntu/Atena-IA/analysis_reports/consciousness_cycle_metrics.json"
        if os.path.exists(metrics_path):
            with open(metrics_path, "r") as f:
                return json.load(f)
        return {"error": "Métricas não encontradas"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/status")
async def get_status():
    return {
        "name": "ATENA Ω",
        "status": "online",
        "mode": "Autonomous Evolution",
        "uptime": "99.9%",
        "version": "10.2.0",
        "last_evolution": datetime.now().isoformat()
    }

@app.get("/api/scan-apis")
async def scan_apis(query: str = "", limit: int = 8):
    """
    Scanner de APIs da ATENA, exposto no servidor de verdade.
    - Combina o catálogo interno (sem rede) com descoberta externa
      (GitHub public-apis, apis.guru), quando GITHUB_TOKEN está configurado.
    - Sem GITHUB_TOKEN nas env vars do Render, a parte de descoberta no
      GitHub fica sujeita ao limite de 60 req/h e pode vir vazia.
    """
    if rank_api_candidates is None:
        return {"error": "Scanner de APIs indisponível (falha de import). Veja os logs do servidor."}
    try:
        ranked = rank_api_candidates(query, limit=limit)
        discovered = discover_any_apis(query, limit=limit) if query else []
        return {
            "query": query,
            "ranked_internal": ranked,
            "discovered_external": discovered,
            "github_token_configured": bool(
                os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
            ),
        }
    except Exception as e:
        logger.error(f"Erro no /api/scan-apis: {e}")
        return {"error": str(e)}

@app.get("/api/learning-stats")
async def learning_stats():
    """
    Mostra o que a ATENA acumulou de conversas reais nesta instância.
    AVISO: no plano Free do Render, esse contador zera a cada
    redeploy/restart/spin-down (filesystem efêmero). Enquanto a
    instância atual estiver no ar, ele só cresce.
    """
    try:
        conn = sqlite3.connect(ATENA_CHAT_DB_PATH)
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) AS c FROM interactions").fetchone()["c"]
        by_provider_rows = conn.execute(
            "SELECT COALESCE(provider, 'desconhecido') AS provider, COUNT(*) AS c FROM interactions GROUP BY provider"
        ).fetchall()
        last_rows = conn.execute(
            "SELECT timestamp, message, provider, model FROM interactions ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()
        return {
            "total_interacoes_acumuladas": total,
            "por_provider": {row["provider"]: row["c"] for row in by_provider_rows},
            "ultimas_10": [dict(row) for row in last_rows],
            "db_path": ATENA_CHAT_DB_PATH,
            "aviso": (
                "No plano Free do Render o filesystem e efemero: esses dados "
                "somem a cada redeploy/restart/spin-down. Pra persistir entre "
                "reinicios, configure ATENA_CHAT_DB_PATH para um disco "
                "persistente (plano pago) ou migre para Render Postgres."
            ),
        }
    except Exception as e:
        logger.error(f"Erro no /api/learning-stats: {e}")
        return {"error": str(e)}

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Chat real da ATENA: usa o AtenaLLMRouterAdvanced em modo automatico.
    O proprio roteador decide qual provider usar (openai/deepseek/anthropic/gemini/local)
    com base em saude, circuit breaker e menor carga pendente.
    Requer DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY ou GEMINI_API_KEY no Render.
    """
    if get_router is None:
        return {
            "response": "Roteador de LLM indisponivel (falha de import). Veja os logs do servidor.",
            "error": True,
            "timestamp": datetime.now().isoformat(),
        }
    try:
        router = await get_router()
        if not router._providers:
            return {
                "response": (
                    "Nenhuma API de LLM configurada ainda. Adiciona DEEPSEEK_API_KEY, "
                    "OPENAI_API_KEY, ANTHROPIC_API_KEY ou GEMINI_API_KEY nas variaveis "
                    "de ambiente do Render."
                ),
                "provider": None,
                "providers_disponiveis": [],
                "timestamp": datetime.now().isoformat(),
            }
        result = await router.generate(prompt=request.message)
        _log_interaction(request.message, result.content, result.provider, result.model, result.latency_ms)
        return {
            "response": result.content,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": round(result.latency_ms, 1),
            "cached": result.cached,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Erro no /api/chat: {e}")
        return {
            "response": "Nao consegui gerar uma resposta agora (todos os providers falharam ou estao indisponiveis).",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }

# --- DASHBOARD ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard principal da ATENA Ω"""
    return get_dashboard_html()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_redirect():
    """Redireciona para o dashboard"""
    return get_dashboard_html()

# Servir arquivos estáticos do dashboard
dashboard_static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "dist", "public")
if os.path.exists(dashboard_static_path):
    app.mount("/dashboard", StaticFiles(directory=dashboard_static_path, html=True), name="dashboard")

# --- EXECUÇÃO ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
