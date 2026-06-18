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
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

# Configuração CORS (Mantida)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---
@app.get("/healthz")
async def healthz():
    return {"status": "online", "version": "10.2.0"}

# --- EXECUÇÃO ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
