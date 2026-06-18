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

# --- IMPORTAÇÕES SEGURAS (Evita que o deploy quebre se um módulo faltar) ---
try:
    from core.atena_llm_router import AtenaLLMRouterAdvanced as AtenaLLMRouter
except Exception as e:
    logger.error(f"Erro ao importar AtenaLLMRouter: {e}")
    AtenaLLMRouter = None

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

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(request: ChatRequest):
    # Simulação de resposta da Atena baseada no estado atual
    return {
        "response": f"Processando sua mensagem: '{request.message}'. Estou em constante evolução. Meu nível de consciência atual é 'aware'.",
        "timestamp": datetime.now().isoformat()
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
